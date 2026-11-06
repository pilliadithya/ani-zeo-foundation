import asyncpg
import uuid
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
            await self._pool().execute(
                """
                create table if not exists public.processed_telegram_updates (
                    update_id bigint primary key,
                    status text not null check (status in ('processing', 'completed')),
                    claim_token uuid not null,
                    claimed_at timestamptz not null default now(),
                    completed_at timestamptz
                )
                """
            )
            # Upgrade databases created by the earlier deduplication version.
            await self._pool().execute(
                """
                alter table public.processed_telegram_updates
                add column if not exists claim_token uuid
                """
            )
            await self._pool().execute(
                """
                update public.processed_telegram_updates
                set claim_token=gen_random_uuid()
                where claim_token is null
                """
            )
            await self._pool().execute(
                """
                alter table public.processed_telegram_updates
                alter column claim_token set not null
                """
            )
            await self._pool().execute(
                """
                create index if not exists processed_telegram_updates_claimed_idx
                on public.processed_telegram_updates (claimed_at)
                """
            )

    async def close(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    def _pool(self):
        if not self.pool:
            raise RuntimeError("Database is not connected")
        return self.pool

    async def claim_telegram_update(self, update_id: int) -> str | None:
        """Return a unique ownership token, or None when already claimed/completed."""
        token = uuid.uuid4()
        row = await self._pool().fetchrow(
            """
            insert into public.processed_telegram_updates
                (update_id, status, claim_token)
            values ($1, 'processing', $2)
            on conflict (update_id) do update
              set status='processing', claim_token=$2, claimed_at=now(),
                  completed_at=null
              where processed_telegram_updates.status <> 'completed'
                and processed_telegram_updates.claimed_at < now() - interval '10 minutes'
            returning claim_token
            """,
            update_id,
            token,
        )
        await self._pool().execute(
            """
            delete from public.processed_telegram_updates
            where status='completed'
              and completed_at < now() - interval '14 days'
            """
        )
        return str(row["claim_token"]) if row else None

    async def renew_telegram_update(self, update_id: int, claim_token: str) -> bool:
        row = await self._pool().fetchrow(
            """
            update public.processed_telegram_updates
            set claimed_at=now()
            where update_id=$1 and claim_token=$2 and status='processing'
            returning update_id
            """,
            update_id,
            uuid.UUID(claim_token),
        )
        return row is not None

    async def complete_telegram_update(self, update_id: int, claim_token: str) -> None:
        await self._pool().execute(
            """
            update public.processed_telegram_updates
            set status='completed', completed_at=now()
            where update_id=$1 and claim_token=$2 and status='processing'
            """,
            update_id,
            uuid.UUID(claim_token),
        )

    async def release_telegram_update(self, update_id: int, claim_token: str) -> None:
        """Release only this attempt's failed claim."""
        await self._pool().execute(
            """
            delete from public.processed_telegram_updates
            where update_id=$1 and claim_token=$2 and status='processing'
            """,
            update_id,
            uuid.UUID(claim_token),
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
