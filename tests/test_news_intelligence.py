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
