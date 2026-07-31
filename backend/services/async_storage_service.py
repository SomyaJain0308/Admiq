from supabase import create_async_client, AsyncClient

from backend.config import get_settings

settings = get_settings()

_async_client: AsyncClient | None = None


async def _bucket():
    global _async_client
    if _async_client is None:
        _async_client = await create_async_client(settings.supabase_url, settings.supabase_service_role_key)
    return _async_client.storage.from_(settings.storage_bucket)

async def upload_file_bytes(path: str, file_bytes: bytes, content_type: str = "application/pdf") -> str:
    bucket = await _bucket()
    await bucket.upload(path, file_bytes, {"content-type": content_type})
    return path