from app.ai.fact_verifier import validate_generated_answer, verify_evidence


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


def test_conflicting_dates_for_same_chapter_are_flagged():
    result = verify_evidence([
        {
            "title": "One Piece Chapter 1197 release date",
            "url": "https://animenewsnetwork.com/one-piece-1197",
            "snippet": "One Piece Chapter 1197 is scheduled for November 1, 2026.",
        },
        {
            "title": "One Piece Chapter 1197 schedule update",
            "url": "https://oricon.co.jp/one-piece-1197",
            "snippet": "One Piece Chapter 1197 will be available on November 2, 2026.",
        },
    ], "One Piece Chapter 1197 release date")
    assert result["conflicts"]
    assert result["conflicts"][0]["chapter"] == "1197"
    assert len(result["conflicts"][0]["dates"]) == 2


def test_different_chapters_with_different_dates_are_not_a_conflict():
    result = verify_evidence([{
        "title": "One Piece chapter release schedule",
        "url": "https://animenewsnetwork.com/one-piece-schedule",
        "snippet": "Chapter 1196 released on October 18, 2026. Chapter 1197 releases on November 1, 2026.",
    }], "One Piece manga chapter release schedule")
    assert result["conflicts"] == []


def test_generated_answer_rejects_unsupported_chapter_and_date():
    research = {
        "evidence": [{
            "title": "One Piece chapter news",
            "snippet": "Chapter 1197 is discussed in this report.",
            "verification_status": "reputable_reporting",
        }],
        "verification": {"conflicts": []},
    }
    result = validate_generated_answer(
        "One Piece Chapter 1198 releases on December 1, 2026.",
        research,
    )
    assert not result["ok"]
    assert result["unsupported_chapters"] == ["1198"]
    assert result["unsupported_dates"] == ["2026-12-01"]


def test_generated_answer_rejects_official_confirmation_without_primary_evidence():
    research = {
        "evidence": [{
            "title": "One Piece news report",
            "snippet": "A report discusses a possible update.",
            "verification_status": "reputable_reporting",
        }],
        "verification": {},
    }
    result = validate_generated_answer(
        "The update was officially confirmed.",
        research,
    )
    assert result["unsupported_confirmation"] is True


def test_generated_answer_can_mention_conflicted_chapter_without_repeating_date():
    research = {
        "evidence": [{
            "title": "One Piece Chapter 1197",
            "snippet": "Chapter 1197 releases November 1, 2026.",
            "verification_status": "reputable_reporting",
        }],
        "verification": {
            "conflicts": [{"chapter": "1197", "dates": ["November 1, 2026", "November 2, 2026"]}],
        },
    }
    result = validate_generated_answer(
        "There are conflicting reports about the release date for Chapter 1197.",
        research,
    )
    assert result["ok"] is True


def test_generated_answer_rejects_official_sources_claim_without_primary_evidence():
    research = {
        "evidence": [{
            "title": "One Piece news report",
            "snippet": "A report discusses a possible chapter update.",
            "verification_status": "reputable_reporting",
        }],
        "verification": {},
    }
    result = validate_generated_answer(
        "According to official sources, it has been confirmed that Chapter 1197 releases soon.",
        research,
    )
    assert result["unsupported_confirmation"] is True


def test_generated_answer_rejects_date_for_conflicted_chapter():
    research = {
        "evidence": [{
            "title": "One Piece Chapter 1197 release",
            "snippet": "Chapter 1197 is listed in the report.",
            "verification_status": "reputable_reporting",
        }],
        "verification": {
            "conflicts": [{
                "chapter": "1197",
                "dates": ["November 1, 2026", "November 2, 2026"],
            }],
        },
    }
    result = validate_generated_answer(
        "Chapter 1197 releases on November 1, 2026.",
        research,
    )
    assert result["conflicted_chapters"] == ["1197"]


def test_official_anime_studio_domain_is_recognised_as_primary():
    result = verify_evidence([{
        "title": "MAPPA official studio news",
        "url": "https://www.mappa.co.jp/news/",
        "snippet": "MAPPA shared an official anime production announcement.",
    }], "Anime studio news")
    assert result["items"]
    assert result["items"][0]["verification_status"] == "primary_source"


def test_crunchyroll_is_treated_as_reputable_reporting_not_universal_primary_source():
    result = verify_evidence([{
        "title": "Anime industry news",
        "url": "https://www.crunchyroll.com/news/latest",
        "snippet": "A report about an anime industry announcement.",
    }], "Latest anime news")
    assert result["items"]
    assert result["items"][0]["verification_status"] == "reputable_reporting"


def test_historical_publication_year_can_support_query_relevance():
    result = verify_evidence([{
        "title": "Anime industry announcement archive",
        "url": "https://animenewsnetwork.com/archive/example",
        "snippet": "A report about a Japanese animation announcement.",
        "published": "2017-06-12",
    }], "anime announcements from 2017")
    assert result["items"]
    assert result["items"][0]["published"] == "2017-06-12"


def test_generated_answer_rejects_impossible_calendar_date():
    research = {
        "evidence": [{
            "title": "One Piece chapter schedule",
            "snippet": "Chapter 1197 is listed in the schedule.",
            "verification_status": "reputable_reporting",
        }],
        "verification": {"conflicts": []},
    }
    result = validate_generated_answer(
        "Chapter 1197 releases on February 30, 2026.",
        research,
    )
    assert result["ok"] is False
    assert result["invalid_dates"] == ["February 30, 2026"]


def test_valid_leap_day_is_normalized_and_checked():
    research = {
        "evidence": [{
            "title": "Anime release schedule",
            "snippet": "The event is scheduled for February 29, 2024.",
            "verification_status": "reputable_reporting",
        }],
        "verification": {"conflicts": []},
    }
    result = validate_generated_answer(
        "The event is scheduled for 2024-02-29.",
        research,
    )
    assert result["ok"] is True
