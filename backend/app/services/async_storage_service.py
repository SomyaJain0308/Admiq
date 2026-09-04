from supabase import create_async_client, AsyncClient

from backend.app.config import get_settings

settings = get_settings()

_async_client: AsyncClient | None = None

async def _bucket():
    global _async_client

    if _async_client is None:
        _async_client = await create_async_client(
            settings.supabase_url,
            settings.supabase_service_role_key,
        )

    assert _async_client is not None
    return _async_client.storage.from_(settings.storage_bucket)


async def upload_file_bytes(
    path: str,
    file_bytes: bytes,
    content_type: str = "application/pdf",
) -> str:
    bucket = await _bucket()
    await bucket.upload(
        path,
        file_bytes,
        {
            "content-type": content_type,
            "upsert": "true",
        },
    )
    return path


async def delete_file(path: str) -> None:
    bucket = await _bucket()
    await bucket.remove([path])


async def create_signed_url(path: str, expires_in: int = 3600) -> str:
    bucket = await _bucket()
    result = await bucket.create_signed_url(path, expires_in)
    return result["signedURL"] if "signedURL" in result else result["signed_url"]