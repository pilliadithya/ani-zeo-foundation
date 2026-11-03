import asyncpg
from app.config import Settings

class Database:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        if self.pool is None:
            self.pool = await asyncpg.create_pool(dsn=self.settings.database_url, min_size=1, max_size=5,
                                                  command_timeout=15, ssl="require")

    async def close(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    def _pool(self):
        if not self.pool:
            raise RuntimeError("Database is not connected")
        return self.pool

    async def ensure_profile(self, user_id: int, username: str | None, display_name: str | None):
        await self._pool().execute("""insert into public.user_profiles (telegram_user_id, username, display_name)
          values ($1,$2,$3) on conflict (telegram_user_id) do update set username=excluded.username,
          display_name=excluded.display_name, updated_at=now()""", user_id, username, display_name)

    async def get_profile(self, user_id: int):
        row = await self._pool().fetchrow("select * from public.user_profiles where telegram_user_id=$1", user_id)
        return dict(row) if row else None

    async def set_consent(self, user_id: int, version="v1"):
        await self._pool().execute("update public.user_profiles set consent_version=$2, consented_at=now(), updated_at=now() where telegram_user_id=$1", user_id, version)

    async def set_language(self, user_id: int, language: str):
        if language not in {"tenglish", "hinglish", "tanglish", "english"}:
            raise ValueError("Unsupported language")
        await self._pool().execute("update public.user_profiles set preferred_language=$2, updated_at=now() where telegram_user_id=$1", user_id, language)

    async def save_message(self, user_id: int, role: str, content: str):
        await self._pool().execute("insert into public.conversation_messages (telegram_user_id, role, content) values ($1,$2,$3)", user_id, role, content[:12000])

    async def get_recent_messages(self, user_id: int, limit: int = 12):
        rows = await self._pool().fetch("""select role, content from (
          select role, content, created_at, id from public.conversation_messages where telegram_user_id=$1
          order by created_at desc, id desc limit $2) recent order by created_at asc, id asc""", user_id, limit)
        return [dict(row) for row in rows]

    async def clear_conversation(self, user_id: int):
        await self._pool().execute("delete from public.conversation_messages where telegram_user_id=$1", user_id)

    async def delete_user_data(self, user_id: int):
        await self._pool().execute("delete from public.user_profiles where telegram_user_id=$1", user_id)
