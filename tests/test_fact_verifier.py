from app.ai.fact_verifier import verify_evidence


def test_primary_source_is_labelled_as_primary_not_absolute_truth():
    result = verify_evidence([{
        "title": "One Piece official manga update",
        "url": "https://mangaplus.shueisha.co.jp/one-piece",
        "snippet": "One Piece manga chapter information.",
    }], "Latest One Piece manga update")
    assert result["overall_status"] == "primary_source_backed"
    assert result["items"][0]["verification_status"] == "primary_source"


def test_reputable_reporting_is_not_mislabelled_as_official_confirmation():
    result = verify_evidence([{
        "title": "Naruto anime news",
        "url": "https://www.animenewsnetwork.com/news",
        "snippet": "Naruto anime production news report.",
    }], "Latest Naruto anime news")
    assert result["overall_status"] == "reported_by_reputable_sources"
    assert result["items"][0]["verification_status"] == "reputable_reporting"


def test_insecure_and_unrelated_sources_are_rejected():
    result = verify_evidence([
        {"title": "One Piece update", "url": "http://example.com", "snippet": "One Piece manga"},
        {"title": "Crypto platform", "url": "https://example.com/crypto", "snippet": "Bitcoin and Web3"},
    ], "Latest One Piece manga update")
    assert not result["items"]
    assert "missing_secure_source_or_content" in result["rejected_reasons"]
    assert "off_topic" in result["rejected_reasons"]


def test_multiple_articles_from_same_publisher_are_not_counted_as_independent_confirmation():
    result = verify_evidence([
        {"title": "One Piece update A", "url": "https://animenewsnetwork.com/a", "snippet": "One Piece manga news"},
        {"title": "One Piece update B", "url": "https://www.animenewsnetwork.com/b", "snippet": "One Piece manga news"},
    ], "One Piece manga news")
    assert len(result["items"]) == 2
    assert result["independent_publishers"] == 1


def test_big_three_query_does_not_require_literal_big_three_in_source():
    result = verify_evidence([
        {"title": "Bleach anime news", "url": "https://oricon.co.jp/bleach", "snippet": "Bleach anime announcement."},
    ], "Latest Big Three anime updates")
    assert len(result["items"]) == 1
