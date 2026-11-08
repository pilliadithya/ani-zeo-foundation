from app.ai.providers import Provider


def test_normalize_openai_compatible_usage():
    result = Provider.normalize_usage({
        "usage": {
            "prompt_tokens": 120,
            "completion_tokens": 35,
            "total_tokens": 155,
            "prompt_tokens_details": {"cached_tokens": 40},
            "completion_tokens_details": {"reasoning_tokens": 5},
            "tool_use_prompt_tokens": 9,
        }
    })
    assert result["input_tokens"] == 120
    assert result["output_tokens"] == 35
    assert result["total_tokens"] == 155
    assert result["cached_input_tokens"] == 40
    assert result["thinking_tokens"] == 5
    assert result["tool_tokens"] == 9


def test_normalize_usage_does_not_invent_missing_token_counts():
    result = Provider.normalize_usage({})
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None
    assert result["total_tokens"] is None
    assert result["cached_input_tokens"] is None
    assert result["thinking_tokens"] is None
    assert result["tool_tokens"] is None


def test_normalize_usage_derives_total_only_when_both_counts_exist():
    result = Provider.normalize_usage({
        "usage": {"input_tokens": 20, "output_tokens": 7}
    })
    assert result["total_tokens"] == 27
    assert result["cached_input_tokens"] is None
