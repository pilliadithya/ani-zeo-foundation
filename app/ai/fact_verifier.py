"""Deterministic evidence screening for anime research results.

This layer does not claim that a source is infallible. It labels evidence strength,
rejects malformed or off-topic sources, and prevents snippets from being called
officially confirmed unless they come from a recognized primary source.
"""
from urllib.parse import urlparse
import re


PRIMARY_DOMAINS = {
    "onepiece.com",
    "mangaplus.shueisha.co.jp",
    "shonenjumpplus.com",
    "viz.com",
    "vizmedia.com",
    "shueisha.co.jp",
    "crunchyroll.com",
    "toei-animation.com",
    "pierrot.jp",
    "aniplex.co.jp",
    "kodansha.co.jp",
    "naruto-official.com",
    "bleach-anime.com",
}

REPUTABLE_NEWS_DOMAINS = {
    "animenewsnetwork.com",
    "oricon.co.jp",
    "natalie.mu",
    "animecorner.me",
    "crunchyroll.com",
    "comicbook.com",
    "ign.com",
}

ANIME_TERMS = {
    "anime", "manga", "one piece", "naruto", "boruto", "bleach",
    "shonen jump", "shueisha", "crunchyroll", "toei animation",
}


def _host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def _matches_domain(host: str, domains: set[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def _chapter_date_claims(items: list[dict]) -> dict:
    """Find conflicting explicit dates attached to the same chapter number."""
    month_date = re.compile(
        r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
        r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s+\d{4})?\b",
        re.I,
    )
    iso_date = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
    claims = {}
    for item in items:
        text = f"{item.get('title', '')} {item.get('snippet', '')}"
        chapter_matches = list(re.finditer(r"\bchapter\s*#?\s*(\d{1,4})\b", text, re.I))
        for index, chapter_match in enumerate(chapter_matches):
            chapter = chapter_match.group(1)
            end = min(len(text), chapter_match.end() + 110)
            if index + 1 < len(chapter_matches):
                end = min(end, chapter_matches[index + 1].start())
            nearby = text[chapter_match.end():end]
            sentence_end = re.search(r"[.!?](?:\\s|$)", nearby)
            if sentence_end:
                nearby = nearby[:sentence_end.end()]
            dates = {match.group(0) for match in month_date.finditer(nearby)}
            dates.update(match.group(0) for match in iso_date.finditer(nearby))
            if dates:
                claims.setdefault(chapter, set()).update(dates)
    return [
        {
            "chapter": chapter,
            "dates": sorted(dates),
            "type": "conflicting_chapter_dates",
        }
        for chapter, dates in claims.items()
        if len(dates) > 1
    ]


def verify_evidence(items: list[dict], query: str, limit: int = 5) -> dict:
    """Validate evidence shape/relevance and assign conservative provenance labels."""
    accepted = []
    rejected = []
    seen_urls = set()
    seen_domains = set()
    query_terms = {
        word.casefold() for word in re.findall(r"[a-z0-9]+", query)
        if len(word) > 2 and word.casefold() not in {
            "latest", "update", "updates", "news", "anime", "manga",
            "confirmed", "today", "recent", "about", "what", "tell", "big", "three", "give", "get",
        }
    }

    for item in items or []:
        if not isinstance(item, dict):
            rejected.append("invalid_item")
            continue
        url = str(item.get("url") or "").strip()
        title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
        snippet = re.sub(r"\s+", " ", str(item.get("snippet") or item.get("content") or "")).strip()
        host = _host(url)
        if not url.startswith("https://") or not host or not title or not snippet:
            rejected.append("missing_secure_source_or_content")
            continue
        if url in seen_urls:
            rejected.append("duplicate_url")
            continue

        haystack = f"{title} {snippet} {url}".casefold()
        anime_relevant = any(term in haystack for term in ANIME_TERMS)
        query_relevant = not query_terms or any(term in haystack or term.rstrip('s') in haystack for term in query_terms)
        if not anime_relevant or not query_relevant:
            rejected.append("off_topic")
            continue

        if _matches_domain(host, PRIMARY_DOMAINS):
            status = "primary_source"
        elif _matches_domain(host, REPUTABLE_NEWS_DOMAINS):
            status = "reputable_reporting"
        else:
            status = "unverified_publisher"

        score = item.get("score")
        if isinstance(score, (int, float)) and score < 0.35:
            rejected.append("low_search_relevance")
            continue

        accepted.append({
            "title": title[:180],
            "url": url,
            "snippet": snippet[:900],
            "domain": host,
            "published": str(item.get("published") or item.get("published_date") or "")[:32],
            "verification_status": status,
            "search_score": score if isinstance(score, (int, float)) else None,
        })
        seen_urls.add(url)
        seen_domains.add(host)
        if len(accepted) >= limit:
            break

    conflicts = _chapter_date_claims(accepted)
    primary_count = sum(x["verification_status"] == "primary_source" for x in accepted)
    reputable_count = sum(x["verification_status"] == "reputable_reporting" for x in accepted)
    if primary_count:
        overall = "primary_source_backed"
    elif reputable_count:
        overall = "reported_by_reputable_sources"
    elif accepted:
        overall = "unverified_sources_only"
    else:
        overall = "no_usable_evidence"

    return {
        "items": accepted,
        "rejected_reasons": rejected,
        "overall_status": overall,
        "primary_source_count": primary_count,
        "reputable_source_count": reputable_count,
        "independent_publishers": len(seen_domains),
        "conflicts": conflicts,
    }
