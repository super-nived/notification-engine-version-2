import logging
import requests

from app.core.settings import settings

logger = logging.getLogger(__name__)

_token: str | None = None


def authenticate():
    global _token
    resp = requests.post(
        f"{settings.PB_URL}/api/admins/auth-with-password",
        json={
            "identity": settings.PB_ADMIN_EMAIL,
            "password": settings.PB_ADMIN_PASSWORD,
        },
        timeout=10,
    )
    resp.raise_for_status()
    _token = resp.json()["token"]
    logger.info("PocketBase admin authenticated")


def _headers() -> dict:
    return {"Authorization": _token or ""}


def get_token() -> str:
    return _token or ""


# ── CRUD helpers ──────────────────────────────────────────────


def pb_list(
    collection: str,
    page: int = 1,
    per_page: int = 200,
    sort: str = "",
    filter_str: str = "",
    expand: str = "",
) -> dict:
    params: dict = {"page": page, "perPage": per_page}
    if sort:
        params["sort"] = sort
    if filter_str:
        params["filter"] = filter_str
    if expand:
        params["expand"] = expand
    resp = requests.get(
        f"{settings.PB_URL}/api/collections/{collection}/records",
        headers=_headers(),
        params=params,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def pb_get_full_list(
    collection: str,
    sort: str = "",
    filter_str: str = "",
    expand: str = "",
) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        data = pb_list(
            collection,
            page=page,
            per_page=200,
            sort=sort,
            filter_str=filter_str,
            expand=expand,
        )
        items.extend(data.get("items", []))
        if page >= data.get("totalPages", 1):
            break
        page += 1
    return items


def pb_get_one(collection: str, record_id: str) -> dict:
    resp = requests.get(
        f"{settings.PB_URL}/api/collections/{collection}/records"
        f"/{record_id}",
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def pb_create(collection: str, data: dict) -> dict:
    resp = requests.post(
        f"{settings.PB_URL}/api/collections/{collection}/records",
        headers=_headers(),
        json=data,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def pb_update(
    collection: str, record_id: str, data: dict
) -> dict:
    resp = requests.patch(
        f"{settings.PB_URL}/api/collections/{collection}/records"
        f"/{record_id}",
        headers=_headers(),
        json=data,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def pb_delete(collection: str, record_id: str) -> None:
    resp = requests.delete(
        f"{settings.PB_URL}/api/collections/{collection}/records"
        f"/{record_id}",
        headers=_headers(),
        timeout=10,
    )
    resp.raise_for_status()


# ── SSE connection ────────────────────────────────────────────


def pb_sse_connect():
    """Open a streaming SSE connection to PocketBase realtime."""
    resp = requests.get(
        f"{settings.PB_URL}/api/realtime",
        headers=_headers(),
        stream=True,
        timeout=None,
    )
    resp.raise_for_status()
    return resp


def pb_sse_subscribe(client_id: str, subscriptions: list[str]):
    """Subscribe to collections via PocketBase realtime."""
    resp = requests.post(
        f"{settings.PB_URL}/api/realtime",
        headers=_headers(),
        json={
            "clientId": client_id,
            "subscriptions": subscriptions,
        },
        timeout=10,
    )
    resp.raise_for_status()
    if resp.status_code == 204:
        return {}
    return resp.json()
