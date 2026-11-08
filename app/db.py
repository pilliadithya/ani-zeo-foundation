import uuid

import asyncpg
from app.config import Settings


class Database:
    SUMMARY_MEMORY_KEY = "conversation_summary_v1"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                dsn=self.settings.database_url,
                min_size=1,
                max_size=5,
                command_timeout=15,
                ssl="require",
            )

    async def close(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    def _pool(self):
        if not self.pool:
            raise RuntimeError("Database is not connected")
        return self.pool

    async def claim_telegram_update(self, update_id: int) -> uuid.UUID | None:
        """Atomically claim an update and return its fencing token; None means duplicate."""
        claim_token = uuid.uuid4()
        row = await self._pool().fetchrow(
            """insert into public.processed_telegram_updates
                (update_id, claim_token, status, attempts, claimed_at)
            values ($1, $2, 'processing', 1, now())
            on conflict (update_id) do update set
                claim_token=excluded.claim_token,
                status='processing',
                attempts=public.processed_telegram_updates.attempts + 1,
                claimed_at=now(),
                last_error=null
            where public.processed_telegram_updates.status='failed'
               or (
                    public.processed_telegram_updates.status='processing'
                    and public.processed_telegram_updates.claimed_at
                        < now() - interval '10 minutes'
               )
            returning claim_token""",
            update_id,
            claim_token,
        )
        return row["claim_token"] if row else None

    async def complete_telegram_update(self, update_id: int, claim_token: uuid.UUID):
        """Complete only the claim still owned by this webhook attempt."""
        await self._pool().execute(
            """update public.processed_telegram_updates
            set status='completed', completed_at=now(), last_error=null
            where update_id=$1 and claim_token=$2 and status='processing'""",
            update_id,
            claim_token,
        )

    async def fail_telegram_update(
        self, update_id: int, claim_token: uuid.UUID, error_label: str
    ):
        # Store only a bounded, non-sensitive error category; never raw exception text.
        safe_label = (error_label or "processing_error")[:80]
        await self._pool().execute(
            """update public.processed_telegram_updates
            set status='failed', last_error=$3
            where update_id=$1 and claim_token=$2 and status='processing'""",
            update_id,
            claim_token,
            safe_label,
        )

    async def ensure_profile(self, user_id: int, username: str | None, display_name: str | None):
        await self._pool().execute(
            """insert into public.user_profiles (telegram_user_id, username, display_name)
            values ($1,$2,$3) on conflict (telegram_user_id) do update set
            username=excluded.username, display_name=excluded.display_name, updated_at=now()""",
            user_id, username, display_name,
        )

    async def get_profile(self, user_id: int):
        row = await self._pool().fetchrow(
            "select * from public.user_profiles where telegram_user_id=$1", user_id
        )
        return dict(row) if row else None

    async def set_consent(self, user_id: int, version="v1"):
        await self._pool().execute(
            "update public.user_profiles set consent_version=$2, consented_at=now(), updated_at=now() where telegram_user_id=$1",
            user_id, version,
        )

    async def set_language(self, user_id: int, language: str):
        if language not in {"tenglish", "hinglish", "tanglish", "english"}:
            raise ValueError("Unsupported language")
        await self._pool().execute(
            "update public.user_profiles set preferred_language=$2, updated_at=now() where telegram_user_id=$1",
            user_id, language,
        )

    async def log_ai_usage(self, user_id: int, provider: str, usage: dict, latency_ms: int | None = None):
        """Persist token telemetry only; never store prompts, answers, or credentials."""
        usage = usage if isinstance(usage, dict) else {}
        await self._pool().execute(
            """insert into public.ai_usage_events
                (telegram_user_id, provider, model, input_tokens, output_tokens,
                 total_tokens, cached_input_tokens, thinking_tokens,
                 estimated_input_tokens, latency_ms, finish_reason, estimated_cost_usd)
            values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)""",
            user_id,
            str(provider or "unknown")[:80],
            str(usage.get("model") or "")[:160] or None,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            usage.get("total_tokens"),
            usage.get("cached_input_tokens"),
            usage.get("thinking_tokens"),
            usage.get("estimated_input_tokens"),
            latency_ms,
            str(usage.get("finish_reason") or "")[:80] or None,
            usage.get("estimated_cost_usd"),
        )

    async def save_message(self, user_id: int, role: str, content: str):
        await self._pool().execute(
            "insert into public.conversation_messages (telegram_user_id, role, content) values ($1,$2,$3)",
            user_id, role, content[:12000],
        )

    async def get_recent_messages(self, user_id: int, limit: int = 12):
        rows = await self._pool().fetch(
            """select role, content from (
                select role, content, created_at, id
                from public.conversation_messages where telegram_user_id=$1
                order by created_at desc, id desc limit $2
            ) recent order by created_at asc, id asc""",
            user_id, limit,
        )
        return [dict(row) for row in rows]

    async def get_memory(self, user_id: int, memory_key: str | None = None):
        key = memory_key or self.SUMMARY_MEMORY_KEY
        row = await self._pool().fetchrow(
            """select memory_value from public.user_memories
            where telegram_user_id=$1 and memory_key=$2""",
            user_id, key,
        )
        return row["memory_value"] if row else None

    async def set_memory(self, user_id: int, memory_value: str, memory_key: str | None = None):
        key = memory_key or self.SUMMARY_MEMORY_KEY
        await self._pool().execute(
            """insert into public.user_memories (telegram_user_id, memory_key, memory_value, confidence, updated_at)
            values ($1,$2,$3,'explicit',now())
            on conflict (telegram_user_id, memory_key)
            do update set memory_value=excluded.memory_value, updated_at=now()""",
            user_id, key, memory_value[:5000],
        )

    async def get_messages_for_summary(
        self,
        user_id: int,
        after_id: int = 0,
        keep_recent: int = 8,
        limit: int = 24,
    ):
        rows = await self._pool().fetch(
            """with recent as (
                select id from public.conversation_messages
                where telegram_user_id=$1 order by id desc limit $3
            )
            select id, role, content
            from public.conversation_messages
            where telegram_user_id=$1 and id>$2
              and id not in (select id from recent)
            order by id asc limit $4""",
            user_id, after_id, keep_recent, limit,
        )
        return [dict(row) for row in rows]

    async def clear_conversation(self, user_id: int):
        await self._pool().execute(
            "delete from public.conversation_messages where telegram_user_id=$1",
            user_id,
        )
        await self._pool().execute(
            "delete from public.user_memories where telegram_user_id=$1 and memory_key=$2",
            user_id, self.SUMMARY_MEMORY_KEY,
        )

    async def delete_user_data(self, user_id: int):
        await self._pool().execute(
            "delete from public.user_profiles where telegram_user_id=$1", user_id
        )
