import uuid
from urllib.parse import urlparse

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

    async def ensure_profile(self, user_id: int, username: str | None = None, display_name: str | None = None):
        """Create the minimum profile using only Telegram's required numeric account ID."""
        await self._pool().execute(
            """insert into public.user_profiles (telegram_user_id)
            values ($1) on conflict (telegram_user_id) do update set
            updated_at=now()""",
            user_id,
        )

    async def get_profile(self, user_id: int):
        row = await self._pool().fetchrow(
            "select * from public.user_profiles where telegram_user_id=$1", user_id
        )
        return dict(row) if row else None

    async def set_consent(self, user_id: int, version="v1"):
        await self._pool().execute(
            "update public.user_profiles set consent_version=$2, consented_at=now(), onboarding_step='awaiting_name', updated_at=now() where telegram_user_id=$1",
            user_id, version,
        )

    async def set_display_name(self, user_id: int, display_name: str):
        await self._pool().execute(
            "update public.user_profiles set display_name=$2, updated_at=now() where telegram_user_id=$1",
            user_id, display_name[:40],
        )

    async def set_onboarding_step(self, user_id: int, step: str):
        allowed = {"welcome", "awaiting_name", "awaiting_language", "completed", "declined"}
        if step not in allowed:
            raise ValueError("Unsupported onboarding step")
        await self._pool().execute(
            "update public.user_profiles set onboarding_step=$2, updated_at=now() where telegram_user_id=$1",
            user_id, step,
        )

    async def set_language(self, user_id: int, language: str):
        if language not in {"tenglish", "hinglish", "tanglish", "english"}:
            raise ValueError("Unsupported language")
        await self._pool().execute(
            "update public.user_profiles set preferred_language=$2, updated_at=now() where telegram_user_id=$1",
            user_id, language,
        )

    async def store_research_evidence(self, evidence: list[dict], provider: str) -> int:
        """Store short, source-linked anime excerpts for historical retrieval; never store user queries."""
        allowed = {
            "primary_source",
            "reputable_reporting",
            "unverified_publisher",
            "grounding_support_passed",
        }
        stored = 0
        for item in (evidence or [])[:5]:
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "").strip()
            title = str(item.get("title") or "").strip()[:180]
            snippet = str(item.get("snippet") or "").strip()[:400]
            status = str(item.get("verification_status") or "")
            domain = str(item.get("domain") or urlparse(url).hostname or "").lower()[:160]
            if (
                not url.startswith("https://")
                or not title
                or not snippet
                or not domain
                or status not in allowed
            ):
                continue
            await self._pool().execute(
                """insert into public.anime_research_evidence
                    (source_url, source_domain, title, snippet, published_at,
                     verification_status, provider, last_verified_at)
                values ($1,$2,$3,$4,$5,$6,$7,now())
                on conflict (source_url) do update set
                    source_domain=excluded.source_domain,
                    title=excluded.title,
                    snippet=excluded.snippet,
                    published_at=excluded.published_at,
                    verification_status=excluded.verification_status,
                    provider=excluded.provider,
                    last_verified_at=now()""",
                url,
                domain,
                title,
                snippet,
                str(item.get("published") or "")[:40] or None,
                status,
                str(provider or "unknown")[:40],
            )
            stored += 1
        return stored

    async def search_research_evidence(self, query: str, limit: int = 5):
        """Retrieve previously verified anime source excerpts for explicit historical queries."""
        text = str(query or "").strip()[:300]
        if not text:
            return []
        safe_limit = max(1, min(int(limit), 8))
        rows = await self._pool().fetch(
            """select title, source_url as url, snippet, source_domain as domain,
                      published_at as published, verification_status, last_verified_at
               from public.anime_research_evidence
               where to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(snippet, ''))
                     @@ websearch_to_tsquery('simple', $1)
               order by last_verified_at desc
               limit $2""",
            text,
            safe_limit,
        )
        return [dict(row) for row in rows]

    async def log_ai_usage(self, user_id: int, provider: str, usage: dict, latency_ms: int | None = None):
        """Persist token telemetry only; never store prompts, answers, or credentials."""
        usage = usage if isinstance(usage, dict) else {}
        await self._pool().execute(
            """insert into public.ai_usage_events
                (telegram_user_id, provider, model, input_tokens, output_tokens,
                 total_tokens, cached_input_tokens, thinking_tokens, tool_tokens,
                 estimated_input_tokens, latency_ms, finish_reason, estimated_cost_usd, operation)
            values ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)""",
            user_id,
            str(provider or "unknown")[:80],
            str(usage.get("model") or "")[:160] or None,
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            usage.get("total_tokens"),
            usage.get("cached_input_tokens"),
            usage.get("thinking_tokens"),
            usage.get("tool_tokens"),
            usage.get("estimated_input_tokens"),
            latency_ms,
            str(usage.get("finish_reason") or "")[:80] or None,
            usage.get("estimated_cost_usd"),
            str(usage.get("operation") or "chat_response")[:80],
        )

    async def get_ai_usage_summary(self, days: int = 7):
        """Aggregate usage without returning prompts, responses, or per-message content."""
        safe_days = max(1, min(int(days), 90))
        return await self._pool().fetch(
            """select provider, operation, count(*)::bigint as requests,
                      sum(input_tokens)::bigint as input_tokens,
                      sum(output_tokens)::bigint as output_tokens,
                      sum(total_tokens)::bigint as total_tokens,
                      sum(cached_input_tokens)::bigint as cached_input_tokens,
                      sum(thinking_tokens)::bigint as thinking_tokens,
                      sum(tool_tokens)::bigint as tool_tokens,
                      sum(estimated_cost_usd)::numeric as estimated_cost_usd,
                      round(avg(latency_ms))::bigint as average_latency_ms
               from public.ai_usage_events
               where created_at >= now() - ($1::text || ' days')::interval
               group by provider, operation
               order by provider, operation""",
            str(safe_days),
        )

    async def save_message(self, user_id: int, role: str, content: str):
        await self._pool().execute(
            "insert into public.conversation_messages (telegram_user_id, role, content) values ($1,$2,$3)",
            user_id, role, content[:12000],
        )

    async def save_exchange(self, user_id: int, user_text: str, assistant_text: str, update_id: int | None = None):
        """Persist only a completed, delivered exchange in one transaction.

        Both rows share the Telegram update id so retries cannot duplicate either turn.
        """
        async with self._pool().acquire() as conn:
            async with conn.transaction():
                if update_id is not None:
                    existing = await conn.fetchval(
                        """select 1 from public.conversation_messages
                           where telegram_user_id=$1 and telegram_update_id=$2
                           limit 1""",
                        user_id, update_id,
                    )
                    if existing:
                        return False
                await conn.execute(
                    """insert into public.conversation_messages
                       (telegram_user_id, role, content, telegram_update_id)
                       values ($1,'user',$2,$3)
                       on conflict do nothing""",
                    user_id, user_text[:12000], update_id,
                )
                await conn.execute(
                    """insert into public.conversation_messages
                       (telegram_user_id, role, content, telegram_update_id)
                       values ($1,'assistant',$2,$3)
                       on conflict do nothing""",
                    user_id, assistant_text[:12000], update_id,
                )
        return True

    async def get_conversation_state(self, user_id: int):
        row = await self._pool().fetchrow(
            """select active_topic, resolved_entities, last_completed_update_id,
                      context_version, updated_at
               from public.conversation_state where telegram_user_id=$1""",
            user_id,
        )
        return dict(row) if row else {}

    async def update_conversation_state(
        self, user_id: int, active_topic: str | None = None,
        resolved_entities: list | None = None, update_id: int | None = None,
    ):
        """Update canonical topic metadata without asking any model to own session state."""
        entities = resolved_entities if isinstance(resolved_entities, list) else []
        await self._pool().execute(
            """insert into public.conversation_state
                 (telegram_user_id, active_topic, resolved_entities, last_completed_update_id, updated_at)
               values ($1,$2,$3::jsonb,$4,now())
               on conflict (telegram_user_id) do update set
                 active_topic=coalesce(excluded.active_topic, conversation_state.active_topic),
                 resolved_entities=case
                   when jsonb_array_length(excluded.resolved_entities) > 0
                   then excluded.resolved_entities else conversation_state.resolved_entities end,
                 last_completed_update_id=coalesce(excluded.last_completed_update_id, conversation_state.last_completed_update_id),
                 updated_at=now()""",
            user_id, (active_topic or "")[:160] or None,
            __import__("json").dumps(entities[:12], ensure_ascii=False), update_id,
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
        await self._pool().execute(
            "delete from public.conversation_state where telegram_user_id=$1",
            user_id,
        )

    async def delete_user_data(self, user_id: int):
        await self._pool().execute(
            "delete from public.user_profiles where telegram_user_id=$1", user_id
        )
