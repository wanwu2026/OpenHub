"""Web 管理后台路由骨架。"""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pathlib import Path

from core.config import BASE_DIR

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
def admin_index():
    return (BASE_DIR / "templates" / "index.html").read_text(encoding="utf-8")
