from supabase import create_client
from backend.rag.config import get_settings

def _bucket():
    settings = get_settings()
    client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return client.storage.from_(settings.supabase_service_role_key)

def upload_file_bytes(path: str, file_bytes: bytes, content_type: str = "application/pdf") -> str:
    _bucket().upload(path, file_bytes, {"content-type": content_type})
    return path

def download_file_bytes(path: str) -> bytes:
    return _bucket().download(path)