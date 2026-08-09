"""Manual scrape trigger endpoints."""

import asyncio
from fastapi import APIRouter, Depends, BackgroundTasks

from app.api.auth import get_current_user
from app.models.user import User

router = APIRouter(prefix="/scrape", tags=["scrape"])


@router.post("/run")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """수동으로 전체 채널 수집 실행 (백그라운드)."""
    from app.services.scrape_job import is_scrape_running, run_all_channels

    # Ask the job itself rather than tracking a local flag — the scheduler
    # starts runs without going through this endpoint.
    if is_scrape_running():
        return {"status": "already_running", "message": "이미 수집 중입니다"}

    background_tasks.add_task(run_all_channels)
    return {"status": "started", "message": "수집을 시작했습니다"}


@router.post("/channel/{handle}")
async def trigger_channel_scrape(
    handle: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """특정 채널만 수동 수집."""
    from sqlalchemy import select
    from app.database import async_session
    from app.models.channel import BenchmarkChannel

    async with async_session() as db:
        row = await db.execute(
            select(BenchmarkChannel).where(BenchmarkChannel.instagram_handle == handle)
        )
        channel = row.scalar_one_or_none()

    if not channel:
        return {"status": "error", "message": f"채널 '{handle}'을 찾을 수 없습니다"}

    async def job():
        from app.services.scrape_job import scrape_channel
        await scrape_channel(channel)

    background_tasks.add_task(job)
    return {"status": "started", "message": f"@{handle} 수집을 시작했습니다"}


@router.get("/status")
async def scrape_status(current_user: User = Depends(get_current_user)):
    """현재 수집 실행 여부 확인."""
    from app.services.scheduler import scheduler
    from app.services.scrape_job import is_scrape_running
    jobs = [
        {"id": j.id, "name": j.name, "next_run": str(j.next_run_time)}
        for j in scheduler.get_jobs()
    ]
    return {"running": is_scrape_running(), "scheduled_jobs": jobs}
