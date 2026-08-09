"""CLI entry point using Typer."""

import asyncio
from typing import Optional

import typer

app = typer.Typer(
    name="carousel-auto",
    help="인스타그램 캐러셀 자동화 CLI",
)

channels_app = typer.Typer(help="벤치마크 채널 관리")
app.add_typer(channels_app, name="channels")


@app.command()
def serve(
    host: str = typer.Option("0.0.0.0", help="서버 호스트"),
    port: int = typer.Option(8000, help="서버 포트"),
    reload: bool = typer.Option(False, help="자동 리로드"),
):
    """FastAPI 서버 실행"""
    import uvicorn

    uvicorn.run("app.main:app", host=host, port=port, reload=reload)


@app.command()
def scrape(
    channel: Optional[str] = typer.Option(None, "--channel", "-c", help="특정 채널 핸들"),
    limit: int = typer.Option(10, "--limit", "-l", help="최대 수집 포스트 수"),
):
    """인스타그램 소재 수집"""
    from app.agents.orchestrator import Orchestrator

    async def _run():
        orchestrator = Orchestrator()
        context = {"limit": limit}
        if channel:
            context["handle"] = channel
        result = await orchestrator.run(
            user_request="채널 소재 수집",
            context=context,
        )
        typer.echo(f"\n✅ 완료: {result['goal']}")
        typer.echo(f"상태: {result['status']}")
        if result.get("evaluation"):
            typer.echo(f"평가: {result['evaluation'].get('summary', '')}")

    asyncio.run(_run())


@app.command()
def process(
    post_id: Optional[int] = typer.Option(None, "--post", "-p", help="특정 포스트 ID"),
):
    """이미지 처리 (리사이즈 + 배경 제거)"""
    from app.agents.orchestrator import Orchestrator

    async def _run():
        orchestrator = Orchestrator()
        post_ids = [post_id] if post_id else []
        result = await orchestrator.run(
            user_request="이미지 처리",
            context={"post_ids": post_ids},
        )
        typer.echo(f"\n✅ 완료: {result['goal']}")

    asyncio.run(_run())


@app.command()
def generate(
    topic: str = typer.Option(..., "--topic", "-t", help="콘텐츠 주제"),
    source: Optional[int] = typer.Option(None, "--source", "-s", help="참고할 포스트 ID"),
    template: str = typer.Option("minimal", "--template", help="디자인 템플릿"),
):
    """AI 캐러셀 콘텐츠 생성"""
    from app.agents.orchestrator import Orchestrator

    async def _run():
        orchestrator = Orchestrator()
        result = await orchestrator.run(
            user_request="캐러셀 만들기",
            context={
                "topic": topic,
                "source_post_id": source,
                "template": template,
            },
        )
        typer.echo(f"\n✅ 완료: {result['goal']}")
        if result.get("evaluation"):
            typer.echo(f"평가: {result['evaluation'].get('summary', '')}")

    asyncio.run(_run())


@channels_app.command("list")
def channels_list():
    """벤치마크 채널 목록 조회"""
    from app.database import async_session
    from app.models.channel import BenchmarkChannel
    from sqlalchemy import select

    async def _run():
        async with async_session() as db:
            result = await db.execute(
                select(BenchmarkChannel).order_by(BenchmarkChannel.created_at.desc())
            )
            channels = result.scalars().all()

        if not channels:
            typer.echo("등록된 채널이 없습니다.")
            return

        for ch in channels:
            status = "🟢" if ch.is_active else "🔴"
            typer.echo(
                f"{status} @{ch.instagram_handle} "
                f"[{ch.category or '미분류'}] "
                f"태그: {', '.join(ch.style_tags) if ch.style_tags else '-'}"
            )

    asyncio.run(_run())


@channels_app.command("add")
def channels_add(
    handle: str = typer.Argument(..., help="인스타그램 핸들"),
    name: str = typer.Option("", "--name", "-n", help="표시 이름"),
    category: str = typer.Option("", "--category", "-c", help="카테고리"),
    tags: Optional[str] = typer.Option(None, "--tags", "-t", help="스타일 태그 (쉼표 구분)"),
):
    """벤치마크 채널 추가"""
    from app.database import async_session, init_db
    from app.models.channel import BenchmarkChannel

    async def _run():
        await init_db()
        async with async_session() as db:
            channel = BenchmarkChannel(
                user_id=1,  # Default user for CLI
                instagram_handle=handle.lstrip("@"),
                display_name=name or handle,
                category=category,
                style_tags=tags.split(",") if tags else [],
            )
            db.add(channel)
            await db.commit()
            typer.echo(f"✅ @{channel.instagram_handle} 채널이 추가되었습니다.")

    asyncio.run(_run())


@app.command()
def scheduler(
    action: str = typer.Argument("start", help="start 또는 stop"),
):
    """스케줄러 데몬 실행"""
    if action == "start":
        typer.echo("🕐 스케줄러 시작 (매일 02:00 소재 수집)")
        from app.services.scheduler import start_scheduler

        start_scheduler()
        # Keep running
        import asyncio

        try:
            asyncio.get_event_loop().run_forever()
        except KeyboardInterrupt:
            typer.echo("\n스케줄러 종료")
    else:
        typer.echo("스케줄러 종료")


if __name__ == "__main__":
    app()
