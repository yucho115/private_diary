"""MCP server for the Django private diary app.

Run with:
    python -m mcp_server.server
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime
from functools import wraps
from pathlib import Path
from typing import Any, Callable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "private_diary.settings_dev")

import django
from asgiref.sync import sync_to_async
from django.contrib.auth import get_user_model
from django.core.exceptions import MultipleObjectsReturned, ObjectDoesNotExist, ValidationError
from django.db.models import Q
from django.utils import timezone
from mcp.server.fastmcp import FastMCP

django.setup()

from diary.models import Diary


mcp = FastMCP("django-private-diary")


def django_db_tool(func: Callable[..., Any]) -> Callable[..., Any]:
    """Run synchronous Django ORM work outside FastMCP's async event loop."""
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return await sync_to_async(func, thread_sensitive=True)(*args, **kwargs)

    return wrapper


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return timezone.localtime(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _file_info(file_field: Any) -> dict[str, str | None]:
    if not file_field:
        return {"name": None, "url": None, "path": None}

    try:
        path = file_field.path
    except (NotImplementedError, ValueError):
        path = None

    try:
        url = file_field.url
    except ValueError:
        url = None

    return {"name": file_field.name or None, "url": url, "path": path}


def _diary_to_dict(diary: Diary, include_content: bool = True) -> dict[str, Any]:
    data = {
        "id": diary.id,
        "user": {
            "id": diary.user_id,
            "username": diary.user.username,
            "email": diary.user.email,
        },
        "title": diary.title,
        "created_at": _iso(diary.created_at),
        "updated_at": _iso(diary.updated_at),
        "photos": {
            "photo1": _file_info(diary.photo1),
            "photo2": _file_info(diary.photo2),
            "photo3": _file_info(diary.photo3),
        },
    }
    if include_content:
        data["content"] = diary.content
    else:
        content = diary.content or ""
        data["content_preview"] = content[:160]
    return data


def _get_user(user_id: int | None = None, email: str | None = None, username: str | None = None):
    User = get_user_model()
    filters = Q()

    if user_id is not None:
        filters &= Q(id=user_id)
    if email:
        filters &= Q(email=email)
    if username:
        filters &= Q(username=username)

    if not filters:
        raise ValueError("user_id, email, or username is required.")

    try:
        return User.objects.get(filters)
    except ObjectDoesNotExist as exc:
        raise ValueError("User not found.") from exc
    except MultipleObjectsReturned as exc:
        raise ValueError("Multiple users matched. Specify user_id.") from exc


def _parse_date(value: str | None, field_name: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be YYYY-MM-DD.") from exc


@mcp.tool()
@django_db_tool
def database_status() -> dict[str, Any]:
    """Check whether Django can see users and diary entries."""
    User = get_user_model()
    return {
        "users": User.objects.count(),
        "diaries": Diary.objects.count(),
        "settings_module": os.environ.get("DJANGO_SETTINGS_MODULE"),
        "database": "default",
    }


@mcp.tool()
@django_db_tool
def list_users(limit: int = 50) -> list[dict[str, Any]]:
    """List diary app users so a caller can choose the diary owner."""
    User = get_user_model()
    limit = max(1, min(limit, 200))
    users = User.objects.order_by("id")[:limit]
    return [
        {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "is_active": user.is_active,
            "date_joined": _iso(user.date_joined),
        }
        for user in users
    ]


@mcp.tool()
@django_db_tool
def list_diaries(
    user_id: int | None = None,
    email: str | None = None,
    username: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    """List diary entries, newest first. Optionally filter by one user."""
    limit = max(1, min(limit, 100))
    offset = max(0, offset)
    queryset = Diary.objects.select_related("user")
    if user_id is not None or email or username:
        user = _get_user(user_id=user_id, email=email, username=username)
        queryset = queryset.filter(user=user)
    queryset = queryset.order_by("-created_at", "-id")
    total = queryset.count()
    diaries = queryset[offset : offset + limit]
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [_diary_to_dict(diary, include_content=False) for diary in diaries],
    }


@mcp.tool()
@django_db_tool
def search_diaries(
    query: str,
    user_id: int | None = None,
    email: str | None = None,
    username: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search diary title and content. Optionally filter by one user."""
    limit = max(1, min(limit, 100))
    start = _parse_date(start_date, "start_date")
    end = _parse_date(end_date, "end_date")

    queryset = Diary.objects.select_related("user")
    if user_id is not None or email or username:
        user = _get_user(user_id=user_id, email=email, username=username)
        queryset = queryset.filter(user=user)
    if query:
        queryset = queryset.filter(Q(title__icontains=query) | Q(content__icontains=query))
    if start:
        queryset = queryset.filter(created_at__date__gte=start)
    if end:
        queryset = queryset.filter(created_at__date__lte=end)

    diaries = queryset.order_by("-created_at", "-id")[:limit]
    return [_diary_to_dict(diary, include_content=False) for diary in diaries]


@mcp.tool()
@django_db_tool
def get_diary(
    diary_id: int,
    user_id: int | None = None,
    email: str | None = None,
    username: str | None = None,
) -> dict[str, Any]:
    """Get one diary entry. User arguments are optional ownership checks."""
    queryset = Diary.objects.select_related("user")
    if user_id is not None or email or username:
        user = _get_user(user_id=user_id, email=email, username=username)
        queryset = queryset.filter(user=user)

    try:
        diary = queryset.get(id=diary_id)
    except ObjectDoesNotExist as exc:
        raise ValueError("Diary not found.") from exc

    return _diary_to_dict(diary, include_content=True)


@mcp.tool()
@django_db_tool
def create_diary(
    title: str,
    content: str = "",
    user_id: int | None = None,
    email: str | None = None,
    username: str | None = None,
) -> dict[str, Any]:
    """Create a diary entry for one user."""
    user = _get_user(user_id=user_id, email=email, username=username)
    diary = Diary(user=user, title=title, content=content)
    try:
        diary.full_clean(exclude=["photo1", "photo2", "photo3"])
    except ValidationError as exc:
        raise ValueError(exc.message_dict) from exc
    diary.save()
    return _diary_to_dict(diary, include_content=True)


@mcp.tool()
@django_db_tool
def update_diary(
    diary_id: int,
    title: str | None = None,
    content: str | None = None,
    user_id: int | None = None,
    email: str | None = None,
    username: str | None = None,
) -> dict[str, Any]:
    """Update title and/or content for one diary entry."""
    try:
        diary = Diary.objects.get(id=diary_id)
    except ObjectDoesNotExist as exc:
        raise ValueError("Diary not found.") from exc
    if user_id is not None or email or username:
        user = _get_user(user_id=user_id, email=email, username=username)
        if diary.user_id != user.id:
            raise ValueError("Diary does not belong to the specified user.")

    if title is not None:
        diary.title = title
    if content is not None:
        diary.content = content

    try:
        diary.full_clean(exclude=["photo1", "photo2", "photo3"])
    except ValidationError as exc:
        raise ValueError(exc.message_dict) from exc
    diary.save()
    return _diary_to_dict(diary, include_content=True)


@mcp.tool()
@django_db_tool
def delete_diary(
    diary_id: int,
    user_id: int | None = None,
    email: str | None = None,
    username: str | None = None,
) -> dict[str, Any]:
    """Delete one diary entry. User arguments are optional ownership checks."""
    try:
        diary = Diary.objects.get(id=diary_id)
    except ObjectDoesNotExist as exc:
        raise ValueError("Diary not found.") from exc
    if user_id is not None or email or username:
        user = _get_user(user_id=user_id, email=email, username=username)
        if diary.user_id != user.id:
            raise ValueError("Diary does not belong to the specified user.")

    deleted_id = diary.id
    diary.delete()
    return {"deleted": True, "id": deleted_id}


if __name__ == "__main__":
    mcp.run()
