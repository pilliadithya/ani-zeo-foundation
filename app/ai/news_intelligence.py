"""Bounded, deterministic helpers for anime-news source processing.

These helpers do not decide whether a claim is true. They preserve article text,
canonicalise source identities, and group likely reports of the same story so the
answer writer and final verifier can distinguish independent publishers.
"""
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
import ipaddress
import re


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
