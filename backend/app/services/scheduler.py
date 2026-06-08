"""APScheduler-based scheduler — scraping + image cleanup."""

import logging
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()

# 수집하거나 생성한 모든 이미지: 3시간 후 자동 삭제
EPHEMERAL_HOURS = 3
MAX_TOTAL_MB = 2500

# 절대 삭제 금지 — single source of truth. 두 부류:
#   (1) 사용자 영구 자산: template_assets / logos / output / cta
#   (2) 카루셀 콘텐츠(복구 불가): restyled(AI 생성) / cutouts(누끼) / enhanced(보정)
#       — 캐러셀이 src 로 참조하는 생성물. age/용량으로 지우면 카루셀이 깨지고 원본 픽셀은
#       복구 불가(=carousel 158). proxy_cache 처럼 "재요청하면 재생성"이 안 됨.
NEVER_DELETE_FOLDERS: frozenset[str] = frozenset({
    "template_assets",     # 사용자가 템플릿에 업로드한 데코 에셋 — 삭제 시 저장된 템플릿 렌더 실패
    "logos",               # 채널/브랜드 로고
    "output",              # 최종 캐러셀 산출물
    "cta",                 # CTA 이미지
    "restyled",            # AI 스타일 변환 이미지 (카루셀 콘텐츠)
    "cutouts",             # 누끼 이미지 (카루셀 콘텐츠)
    "enhanced",            # AI 보정 이미지 (카루셀 콘텐츠)
})

# ephemeral(3h) 정리 + 용량 캡(MAX_TOTAL_MB) 양쪽에서 블라인드 삭제 금지할 폴더.
# proxy_cache(외부 이미지 디스크 캐시)도 포함 — blind evict 하면 캐러셀이 참조하는
# 이미지가 사라진다(=carousel 158). proxy_cache 는 전용 cleanup_proxy_cache 가
# "미참조 + 7일 경과"만 골라 지운다(참조분/최근분 보존).
PERMANENT_FOLDERS: set[str] = set(NEVER_DELETE_FOLDERS) | {"proxy_cache"}

# cleanup_proxy_cache: 미참조 proxy 파일이 이만큼 지나면 삭제.
LONG_LIVED_DAYS = 7


async def scrape_job():
    from app.services.scrape_job import run_all_channels
    await run_all_channels()


async def expire_posts_job():
    """5일 지난 post는 본문/이미지/요소 삭제하고 row만 남겨 dedupe 유지.
    '내 소재'(saved_at)에 들어간 post는 면제."""
    from app.database import async_session
    from app.services.post_cleanup import expire_old_posts
    async with async_session() as db:
        await expire_old_posts(db, days=5)


def _is_under(path: Path, parents: set[str]) -> bool:
    """True if any parent directory name is in `parents`."""
    return any(p.name in parents for p in path.parents)


async def cleanup_images():
    """3시간 지난 ephemeral 이미지 삭제 + 용량 초과 시 강제 정리.

    삭제 대상:
      - data/images/raw, processed, sourced, pool
      - data/template_studio_cache/<slug>/slide_*.webp
    (restyled 는 ephemeral 이 아님 — LONG_LIVED 7일 룰로 별도 관리)

    보존 대상:
      - data/images/logos/  (브랜드 로고)
      - data/images/output/ (최종 산출물)
      - data/db.sqlite3
    """
    data_dir = settings.DATA_DIR
    now = datetime.now()
    cutoff = now - timedelta(hours=EPHEMERAL_HOURS)
    deleted = 0
    freed = 0

    ephemeral_roots = [
        data_dir / "images" / "raw",
        data_dir / "images" / "processed",
        data_dir / "images" / "sourced",
        data_dir / "images" / "pool",
        data_dir / "template_studio_cache",
    ]

    for root in ephemeral_roots:
        if not root.exists():
            continue
        for item in root.rglob("*"):
            try:
                if not item.is_file():
                    continue
                if _is_under(item, PERMANENT_FOLDERS):
                    continue
                if datetime.fromtimestamp(item.stat().st_mtime) < cutoff:
                    size = item.stat().st_size
                    item.unlink()
                    freed += size
                    deleted += 1
            except Exception as e:
                logger.warning(f"[Cleanup] Failed to delete {item}: {e}")

    # Sweep empty directories left behind
    for root in ephemeral_roots:
        if not root.exists():
            continue
        for d in sorted([p for p in root.rglob("*") if p.is_dir()], key=lambda p: -len(p.parts)):
            try:
                d.rmdir()  # only removes if empty
            except OSError:
                pass

    # Hard cap on total disk usage
    images_dir = data_dir / "images"
    if images_dir.exists():
        total = sum(f.stat().st_size for f in images_dir.rglob("*") if f.is_file())
        cap = MAX_TOTAL_MB * 1024 * 1024
        if total > cap:
            evictable = sorted(
                [f for f in images_dir.rglob("*") if f.is_file() and not _is_under(f, PERMANENT_FOLDERS)],
                key=lambda f: f.stat().st_mtime,
            )
            for f in evictable:
                if total <= cap:
                    break
                try:
                    fsize = f.stat().st_size
                    f.unlink()
                    total -= fsize
                    freed += fsize
                    deleted += 1
                except Exception:
                    pass

    if deleted:
        logger.info(f"[Cleanup] removed {deleted} files, freed {freed / 1024 / 1024:.1f}MB (>{EPHEMERAL_HOURS}h old)")
    else:
        logger.debug("[Cleanup] nothing to clean")


async def cleanup_proxy_cache():
    """proxy_cache 정리 — '미참조 + 7일 경과' 파일만 삭제.

    proxy_cache 는 캐러셀이 src 로 참조하는 외부 이미지의 디스크 캐시다. 캐러셀이
    아직 쓰는 파일을 지우면 편집기에서 이미지가 안 뜨고(=carousel 158), 소스가 이미
    죽었으면 영구 손실이 된다. 규칙:
      - 어떤 캐러셀이라도 참조 → 영구 보존 (나이 무관)
      - 최근 7일 내 받은 파일 → 보존 (아직 저장 안 한 작업 중 픽 일 수 있음)
      - 미참조 + 7일 경과 (검색만 하고 안 고른 후보 잔해) → 삭제
    캐시 키 = sha1(요청 url). 저장 src 의 ?url= 값을 여러 디코딩 변형으로 모두 해시해
    보호 set 을 만든다 — 참조 파일을 절대 오삭제하지 않도록 보수적으로.
    """
    import hashlib
    import json
    from urllib.parse import unquote
    from app.database import async_session
    from app.models.carousel import GeneratedCarousel
    from sqlalchemy import select

    cache = settings.DATA_DIR / "images" / "proxy_cache"
    if not cache.exists():
        return

    referenced: set[str] = set()
    async with async_session() as db:
        rows = (await db.execute(select(GeneratedCarousel.canvas_data))).all()
    for (cd,) in rows:
        data = cd if isinstance(cd, dict) else None
        if data is None:
            try:
                data = json.loads(cd) if cd else {}
            except Exception:
                continue
        for s in (data.get("canvas_slides") or []):
            for o in (s.get("objects") or []):
                src = str(o.get("src", ""))
                if "/api/images/proxy" in src and "url=" in src:
                    enc = src.split("url=", 1)[1].split("&", 1)[0]
                    for v in {enc, unquote(enc), unquote(unquote(enc))}:
                        referenced.add(hashlib.sha1(v.encode("utf-8", "ignore")).hexdigest())

    cutoff = datetime.now() - timedelta(days=LONG_LIVED_DAYS)
    deleted = 0
    freed = 0
    for f in cache.iterdir():
        try:
            if not f.is_file():
                continue
            if f.name.rsplit(".", 1)[0] in referenced:
                continue  # 참조됨 → 영구 보존
            if datetime.fromtimestamp(f.stat().st_mtime) >= cutoff:
                continue  # 최근 7일 → 보존
            size = f.stat().st_size
            f.unlink()
            freed += size
            deleted += 1
        except Exception as e:
            logger.warning(f"[ProxyCleanup] failed to delete {f.name}: {e}")
    if deleted:
        logger.info(
            f"[ProxyCleanup] removed {deleted} unreferenced proxy files "
            f"(>{LONG_LIVED_DAYS}d old), freed {freed / 1024 / 1024:.1f}MB "
            f"(kept {len(referenced)} referenced keys)"
        )


def start_scheduler():
    # 소재 수집: 매일 09:00, 21:00 KST (하루 2회) — 회차당 최대 50개 NEW post.
    # 한 번 수집한 instagram_post_id는 row가 expire되어도 영구 dedupe.
    scheduler.add_job(
        scrape_job,
        trigger=CronTrigger(hour="9,21", minute=0, timezone="Asia/Seoul"),
        id="scrape_rolling",
        name="하루 2회 소재 수집 (09:00 / 21:00 KST)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # 5일 지난 post 본문/이미지 정리 (instagram_post_id는 보존 → 영구 dedupe).
    # 수집 1시간 전 (08:00, 20:00 KST)에 돌려 늘 가장 신선한 데이터를 보여줌.
    # saved_at(내 소재)에 있는 post는 면제.
    scheduler.add_job(
        expire_posts_job,
        trigger=CronTrigger(hour="8,20", minute=0, timezone="Asia/Seoul"),
        id="expire_posts",
        name="5일 지난 post soft-delete (saved_at 면제)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    # 이미지 정리: 30분마다 (3시간 임계값을 정확히 맞추기 위해)
    scheduler.add_job(
        cleanup_images,
        trigger=IntervalTrigger(minutes=30),
        id="cleanup_images",
        name="이미지 정리 (3h ephemeral)",
        replace_existing=True,
    )

    # proxy_cache 정리: 매일 03:30 KST — 미참조 + 7일 초과 외부 이미지 캐시만.
    # (참조분/최근분은 보존 — 캐러셀 이미지가 사라지지 않게)
    scheduler.add_job(
        cleanup_proxy_cache,
        trigger=CronTrigger(hour=3, minute=30, timezone="Asia/Seoul"),
        id="cleanup_proxy_cache",
        name=f"proxy_cache 정리 (미참조 + {LONG_LIVED_DAYS}일)",
        replace_existing=True,
        misfire_grace_time=3600,
    )

    scheduler.start()
    logger.info(
        f"[Scheduler] Started — scrape 09/21 KST, post expiry 08/20 KST (5d TTL), "
        f"image cleanup every 30min (3h), long-lived cleanup daily 03:30 KST ({LONG_LIVED_DAYS}d)"
    )


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("[Scheduler] Stopped")
