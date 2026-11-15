from app.ai.news_intelligence import canonical_url, cluster_stories, extract_article_text


def test_canonical_url_removes_tracking_and_fragment():
    assert canonical_url("https://www.example.com/news/story?utm_source=x&id=4#top") == (
        "https://example.com/news/story?id=4"
    )


def test_canonical_url_rejects_non_public_or_non_https_targets():
    assert canonical_url("http://example.com/story") == ""
    assert canonical_url("https://127.0.0.1/private") == ""
    assert canonical_url("https://localhost/admin") == ""


def test_article_extraction_ignores_script_and_navigation_text():
    html = """
    <html><head><title>Anime announcement</title>
    <meta property="og:description" content="Official episode announcement"></head>
    <body><nav>Menu noise</nav><article><h1>New anime episode</h1>
    <p>The studio announced a new episode for Friday.</p>
    <script>do_not_include_secret()</script></article><footer>Footer noise</footer></body></html>
    """
    result = extract_article_text(html)
    assert result["page_title"] == "Anime announcement"
    assert result["page_description"] == "Official episode announcement"
    assert "The studio announced a new episode" in result["page_text"]
    assert "Menu noise" not in result["page_text"]
    assert "Footer noise" not in result["page_text"]
    assert "do_not_include_secret" not in result["page_text"]


def test_plain_text_is_preserved_and_bounded():
    result = extract_article_text("A plain article excerpt. " * 100, limit=80)
    assert result["page_text"].startswith("A plain article excerpt.")
    assert len(result["page_text"]) <= 80


def test_story_clustering_counts_independent_publishers_per_story():
    items = [
        {"title": "Mashle Season 3 reveals premiere date", "domain": "news.example"},
        {"title": "Mashle Season 3 premiere date revealed", "domain": "anime.example"},
        {"title": "One Piece new chapter release schedule", "domain": "manga.example"},
    ]
    cluster_stories(items)
    assert items[0]["story_id"] == items[1]["story_id"]
    assert items[0]["story_source_count"] == 2
    assert items[0]["story_independent_publishers"] == 2
    assert items[2]["story_id"] != items[0]["story_id"]


def test_different_seasons_of_same_franchise_are_not_merged():
    items = [
        {"title": "Mashle Season 3 reveals premiere date", "domain": "news.example"},
        {"title": "Mashle Season 4 production announced", "domain": "anime.example"},
    ]
    cluster_stories(items)
    assert items[0]["story_id"] != items[1]["story_id"]


import pytest
from app.ai.news_intelligence import align_claims_to_sources, fetch_article_text


def test_claim_alignment_returns_supporting_source_span():
    evidence = [{
        "title": "Mashle Season 3 premiere date announced",
        "url": "https://www.animenewsnetwork.com/news/example",
        "snippet": "The studio announced the Mashle Season 3 premiere date.",
        "page_text": "Mashle Season 3 will premiere on January 9, 2027.",
    }]
    result = align_claims_to_sources(
        "Mashle Season 3 will premiere on January 9, 2027.",
        evidence,
    )
    assert not result["unsupported_claims"]
    assert result["aligned_claims"][0]["source_span"]
    assert result["aligned_claims"][0]["source_url"].startswith("https://")


def test_claim_alignment_flags_unmatched_episode_count():
    evidence = [{
        "title": "Mashle Season 3 announcement",
        "url": "https://www.animenewsnetwork.com/news/example",
        "snippet": "The new season was announced.",
    }]
    result = align_claims_to_sources(
        "Mashle Season 3 will contain 24 episodes.",
        evidence,
    )
    assert result["unsupported_claims"]


@pytest.mark.asyncio
async def test_article_fetch_rejects_unapproved_hosts_without_network_access():
    result = await fetch_article_text(
        "https://example.com/story",
        {"animenewsnetwork.com"},
    )
    assert result["page_text"] == ""


@pytest.mark.asyncio
async def test_article_fetch_rejects_localhost_without_network_access():
    result = await fetch_article_text(
        "https://localhost/private",
        {"localhost"},
    )
    assert result["page_text"] == ""
