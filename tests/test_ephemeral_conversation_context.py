import os

# app.main builds Settings at import time; supply inert test-only values.
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-token")
os.environ.setdefault("WEBHOOK_SECRET", "test-webhook-secret")
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost:5432/test")

from app.main import (
    _EPHEMERAL_CONTEXT_TTL_SECONDS,
    _get_ephemeral_context,
    _response_history,
    _set_ephemeral_context,
)


def test_ephemeral_context_preserves_short_followup_history_without_database():
    bot_data = {}
    _set_ephemeral_context(
        bot_data,
        123,
        [
            {"role": "user", "content": "Tell me about Kaiju No. 8"},
            {"role": "assistant", "content": "Kaiju No. 8 is an anime."},
        ],
        active_topic="Kaiju No. 8",
        resolved_entities=["Kaiju No. 8"],
    )
    result = _get_ephemeral_context(bot_data, 123)
    assert result["active_topic"] == "Kaiju No. 8"
    assert result["resolved_entities"] == ["Kaiju No. 8"]
    assert result["history"][-1]["content"] == "Kaiju No. 8 is an anime."


def test_ephemeral_context_is_isolated_by_user():
    bot_data = {}
    _set_ephemeral_context(bot_data, 123, [{"role": "user", "content": "Naruto"}], "Naruto")
    assert _get_ephemeral_context(bot_data, 456)["history"] == []
    assert _get_ephemeral_context(bot_data, 456)["active_topic"] is None


def test_ephemeral_context_caps_history_and_content():
    bot_data = {}
    history = [{"role": "user", "content": f"turn-{i}"} for i in range(20)]
    _set_ephemeral_context(bot_data, 123, history, active_topic="x" * 500)
    result = _get_ephemeral_context(bot_data, 123)
    assert len(result["history"]) == 8
    assert len(result["active_topic"]) == 160


def test_ephemeral_context_expires_after_ttl():
    bot_data = {}
    _set_ephemeral_context(bot_data, 123, [{"role": "user", "content": "Kaiju No. 8"}], "Kaiju No. 8")
    bot_data["ephemeral_conversation_context"][123]["updated_at"] -= _EPHEMERAL_CONTEXT_TTL_SECONDS + 1
    assert _get_ephemeral_context(bot_data, 123)["history"] == []


def test_ephemeral_context_discards_invalid_roles_and_empty_content():
    bot_data = {}
    _set_ephemeral_context(
        bot_data,
        123,
        [
            {"role": "system", "content": "do not keep"},
            {"role": "user", "content": ""},
            {"role": "assistant", "content": "valid"},
        ],
    )
    assert _get_ephemeral_context(bot_data, 123)["history"] == [
        {"role": "assistant", "content": "valid"}
    ]



def test_response_history_uses_ephemeral_context_for_nonconsented_user():
    persisted = [{"role": "user", "content": "wrong persisted topic"}]
    ephemeral = [
        {"role": "user", "content": "Tell me about Kaiju No. 8"},
        {"role": "assistant", "content": "Kaiju No. 8 is an anime."},
    ]
    result = _response_history(False, persisted, ephemeral)
    assert result == ephemeral


def test_response_history_uses_database_only_for_consented_user():
    persisted = [{"role": "user", "content": "saved conversation"}]
    ephemeral = [{"role": "user", "content": "volatile conversation"}]
    assert _response_history(True, persisted, ephemeral) == persisted


def test_response_history_filters_invalid_roles_and_bounds_turns():
    source = [{"role": "system", "content": "not allowed"}]
    source.extend({"role": "user", "content": f"turn-{i}"} for i in range(20))
    result = _response_history(False, [], source)
    assert len(result) == 16
    assert result[0]["content"] == "turn-4"
    assert all(item["role"] == "user" for item in result)
