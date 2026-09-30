"""Private object storage adapters for local development and cloud deployment."""
from pathlib import Path
from urllib.parse import quote

import httpx

from app.config import settings
from app.services.firebase import get_bucket


def _local_path(key: str) -> Path:
    root = Path(settings.local_storage_dir).resolve()
    target = (root / key).resolve()
    if root not in target.parents:
        raise ValueError("Invalid storage key")
    return target


def _supabase_url(key: str) -> str:
    base = settings.supabase_url.rstrip("/")
    bucket = quote(settings.supabase_storage_bucket, safe="")
    object_key = quote(key, safe="/")
    return f"{base}/storage/v1/object/{bucket}/{object_key}"


def _supabase_headers(content_type: str | None = None) -> dict[str, str]:
    key = settings.supabase_service_role_key
    if not settings.supabase_url or not key or not settings.supabase_storage_bucket:
        raise RuntimeError("Supabase Storage is not configured")
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    if content_type:
        headers["Content-Type"] = content_type
        headers["x-upsert"] = "false"
    return headers


def save_object(key: str, data: bytes, content_type: str):
    if settings.local_storage_dir:
        target = _local_path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    elif settings.supabase_url:
        response = httpx.post(_supabase_url(key), headers=_supabase_headers(content_type), content=data, timeout=60)
        response.raise_for_status()
    else:
        get_bucket().blob(key).upload_from_string(data, content_type=content_type)


def read_object(key: str) -> bytes:
    if settings.local_storage_dir:
        return _local_path(key).read_bytes()
    if settings.supabase_url:
        response = httpx.get(_supabase_url(key), headers=_supabase_headers(), timeout=60)
        if response.status_code == 404:
            raise FileNotFoundError(key)
        response.raise_for_status()
        return response.content
    return get_bucket().blob(key).download_as_bytes()


def delete_object(key: str):
    if settings.local_storage_dir:
        _local_path(key).unlink(missing_ok=True)
    elif settings.supabase_url:
        url = f"{settings.supabase_url.rstrip('/')}/storage/v1/object/{quote(settings.supabase_storage_bucket, safe='')}"
        response = httpx.delete(url, headers=_supabase_headers(), json={"prefixes": [key]}, timeout=60)
        if response.status_code != 404:
            response.raise_for_status()
    else:
        get_bucket().blob(key).delete()
