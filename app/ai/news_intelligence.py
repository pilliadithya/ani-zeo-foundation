"""Bounded, deterministic helpers for anime-news source processing.

These helpers do not decide whether a claim is true. They preserve article text,
canonicalise source identities, and group likely reports of the same story so the
answer writer and final verifier can distinguish independent publishers.
"""
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import ipaddress
import re
import httpx


TRACKING_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
TRACKING_PREFIXES = ("utm_",)


def canonical_url(url: str) -> str:
    """Remove fragments and common tracking parameters without changing article paths."""
    try:
        parts = urlsplit(str(url or "").strip())
        if parts.scheme.lower() != "https" or not parts.hostname:
            return ""
        host = parts.hostname.lower().removeprefix("www.")
        if parts.username or parts.password or parts.port not in (None, 443):
            return ""
        try:
            ipaddress.ip_address(host)
            return ""
        except ValueError:
            pass
        if host in {"localhost"} or host.endswith((".localhost", ".local", ".internal")):
            return ""
        query = [
            (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.casefold() not in TRACKING_KEYS
            and not key.casefold().startswith(TRACKING_PREFIXES)
        ]
        path = re.sub(r"/{2,}", "/", parts.path or "/")
        return urlunsplit(("https", host, path, urlencode(query, doseq=True), ""))
    except (TypeError, ValueError):
        return ""


class _ArticleTextParser(HTMLParser):
    """Extract readable article text while ignoring navigation and executable markup."""

    BLOCKED = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title_parts = []
        self.description = ""
        self.text_parts = []
        self._blocked = 0
        self._in_title = False
        self._capture_depth = 0
        self._chars = 0

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag in self.BLOCKED:
            self._blocked += 1
        if tag == "title":
            self._in_title = True
        if tag == "meta":
            key = (attrs.get("property") or attrs.get("name") or "").casefold()
            if key in {"og:description", "description", "twitter:description"} and not self.description:
                self.description = attrs.get("content", "")[:500]
        if tag in {"article", "main"}:
            self._capture_depth += 1
        if tag in {"p", "li", "h1", "h2", "h3", "blockquote"} and not self._blocked:
            self.text_parts.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in self.BLOCKED and self._blocked:
            self._blocked -= 1
        if tag == "title":
            self._in_title = False
        if tag in {"article", "main"} and self._capture_depth:
            self._capture_depth -= 1
        if tag in {"p", "li", "h1", "h2", "h3", "blockquote"} and not self._blocked:
            self.text_parts.append("\n")

    def handle_data(self, data):
        if self._blocked:
            return
        text = re.sub(r"\s+", " ", data).strip()
        if not text:
            return
        self._chars += len(text)
        if self._in_title:
            self.title_parts.append(text)
        # Prefer article/main text where present; retain a bounded fallback for
        # sites whose markup does not use semantic containers.
        self.text_parts.append(text + " ")

    def result(self, limit=6000):
        text = re.sub(r"[ \t]+", " ", " ".join(self.text_parts))
        text = re.sub(r"\s*\n\s*", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        return {
            "page_title": " ".join(self.title_parts)[:180],
            "page_description": self.description,
            "page_text": text[:limit],
        }


def extract_article_text(raw_content: str, limit: int = 6000) -> dict:
    """Extract bounded readable text from raw HTML; plain text passes through."""
    raw = str(raw_content or "")[:200_000]
    if not raw:
        return {"page_title": "", "page_description": "", "page_text": ""}
    if not re.search(r"<(?:html|body|article|main|p|title|meta)\b", raw, re.I):
        return {
            "page_title": "",
            "page_description": "",
            "page_text": re.sub(r"\s+", " ", raw).strip()[:limit],
        }
    parser = _ArticleTextParser()
    try:
        parser.feed(raw)
        return parser.result(limit=limit)
    except (ValueError, TypeError):
        return {"page_title": "", "page_description": "", "page_text": ""}


def _title_tokens(title: str) -> set[str]:
    ignored = {
        "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "at",
        "new", "latest", "news", "update", "updates", "anime", "manga",
        "announced", "announcement", "reveals", "reveal", "release", "date",
        "trailer", "visual", "official",
    }
    return {
        token.casefold() for token in re.findall(r"[a-z0-9]+", title or "")
        if len(token) > 2 and token.casefold() not in ignored
    }


def cluster_stories(items: list[dict]) -> list[dict]:
    """Attach conservative story clusters and per-story independent publisher counts."""
    clusters = []
    for item in items or []:
        title = str(item.get("title") or "")
        tokens = _title_tokens(title)
        best = None
        best_score = 0.0
        for cluster in clusters:
            if not tokens or not cluster["tokens"]:
                continue
            score = len(tokens & cluster["tokens"]) / max(1, len(tokens | cluster["tokens"]))
            if score > best_score:
                best, best_score = cluster, score
        if best is None or best_score < 0.62:
            best = {
                "story_id": f"story_{len(clusters) + 1}",
                "tokens": tokens,
                "items": [],
                "domains": set(),
            }
            clusters.append(best)
        best["items"].append(item)
        domain = str(item.get("domain") or "").lower().removeprefix("www.")
        if domain:
            best["domains"].add(domain)

    for cluster in clusters:
        for item in cluster["items"]:
            item["story_id"] = cluster["story_id"]
            item["story_source_count"] = len(cluster["items"])
            item["story_independent_publishers"] = len(cluster["domains"])
    return items



async def fetch_article_text(url: str, allowed_domains: set[str], limit: int = 6000) -> dict:
    """Fetch bounded article text only from explicitly trusted publisher domains.

    Redirects are followed manually and revalidated. Private/reserved DNS answers,
    non-HTTPS URLs, credentials, unusual ports, unsupported content types and
    oversized responses are rejected. This is a best-effort application guard;
    production egress controls should additionally block private address ranges.
    """
    current = canonical_url(url)
    for _ in range(3):
        if not current:
            return {"page_title": "", "page_description": "", "page_text": ""}
        parts = urlsplit(current)
        host = parts.hostname or ""
        if not any(host == d or host.endswith("." + d) for d in allowed_domains):
            return {"page_title": "", "page_description": "", "page_text": ""}
        try:
            addresses = await asyncio.wait_for(
                asyncio.get_running_loop().getaddrinfo(host, 443, type=socket.SOCK_STREAM),
                timeout=1.5,
            )
        except (OSError, asyncio.TimeoutError):
            return {"page_title": "", "page_description": "", "page_text": ""}
        if not addresses:
            return {"page_title": "", "page_description": "", "page_text": ""}
        for address in addresses:
            try:
                ip = ipaddress.ip_address(address[4][0])
                if not ip.is_global:
                    return {"page_title": "", "page_description": "", "page_text": ""}
            except ValueError:
                return {"page_title": "", "page_description": "", "page_text": ""}

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(4.0, connect=2.0),
                follow_redirects=False,
                headers={"User-Agent": "AniZeoNewsBot/1.0 (+https://ani-zeo-foundation.onrender.com)"},
            ) as client:
                async with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            break
                        current = canonical_url(urljoin(current, location))
                        continue
                    if response.status_code != 200:
                        break
                    content_type = response.headers.get("content-type", "").casefold()
                    if not any(kind in content_type for kind in ("text/html", "application/xhtml+xml", "text/plain")):
                        break
                    chunks = []
                    size = 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 200_000:
                            break
                        chunks.append(chunk)
                    if size > 200_000:
                        break
                    raw = b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")
                    return extract_article_text(raw, limit=limit)
        except (httpx.HTTPError, UnicodeError, ValueError):
            break
    return {"page_title": "", "page_description": "", "page_text": ""}


def align_claims_to_sources(answer: str, evidence: list[dict], min_coverage: float = 0.42) -> dict:
    """Conservatively align factual-looking sentences to source text spans.

    This lexical alignment is an explainable guardrail, not an entailment model.
    It checks named/number anchors and weighted token overlap and returns the
    closest source sentence for every checked claim.
    """
    stop = {
        "the", "a", "an", "and", "or", "but", "to", "of", "in", "on", "at",
        "for", "from", "with", "by", "as", "is", "are", "was", "were", "be",
        "been", "being", "this", "that", "these", "those", "it", "its", "they",
        "their", "he", "she", "his", "her", "has", "have", "had", "will",
        "would", "could", "may", "might", "about", "also", "more", "new",
        "latest", "according", "reported", "reports", "source", "sources",
    }

    def tokens(value):
        return {
            token.casefold() for token in re.findall(r"[A-Za-z][A-Za-z0-9'-]*|\d{1,4}(?:[.,]\d+)?%?", value or "")
            if len(token) > 2 and token.casefold() not in stop
        }

    source_sentences = []
    for item in evidence or []:
        if not isinstance(item, dict):
            continue
        source = " ".join(str(item.get(key) or "") for key in ("title", "snippet", "page_text"))
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", source):
            sentence_tokens = tokens(sentence)
            if sentence_tokens:
                source_sentences.append((item, sentence.strip()[:500], sentence_tokens))

    aligned, unsupported = [], []
    for raw_sentence in re.split(r"(?<=[.!?])\s+|\n+", str(answer or "")):
        sentence = re.sub(r"^\s*(?:[-*•]\s*)?(?:\*\*)?|(?:\*\*)?\s*$", "", raw_sentence).strip()
        claim_tokens = tokens(sentence)
        if len(claim_tokens) < 3:
            continue
        # Skip conversational framing and headings without a factual predicate.
        if len(sentence) < 28:
            continue
        best = None
        best_score = 0.0
        for item, source_sentence, source_tokens in source_sentences:
            overlap = claim_tokens & source_tokens
            coverage = len(overlap) / max(1, len(claim_tokens))
            anchor_tokens = {
                token.casefold()
                for token in re.findall(r"\b[A-Z][A-Za-z0-9'-]{2,}\b|\b\d{1,4}(?:[.,]\d+)?%?\b", sentence)
            }
            anchor_coverage = len(anchor_tokens & source_tokens) / max(1, len(anchor_tokens))
            score = coverage * 0.75 + anchor_coverage * 0.25
            if score > best_score:
                best, best_score = (item, source_sentence, coverage, anchor_coverage), score
        if best and best[2] >= min_coverage and (best[3] >= 0.5 or not any(re.search(r"\d", t) for t in claim_tokens)):
            aligned.append({
                "claim": sentence[:300],
                "source_title": str(best[0].get("title") or "")[:180],
                "source_url": str(best[0].get("url") or ""),
                "source_span": best[1],
                "coverage": round(best_score, 3),
            })
        else:
            unsupported.append(sentence[:300])
    return {"aligned_claims": aligned, "unsupported_claims": unsupported, "checked_claim_count": len(aligned) + len(unsupported)}
