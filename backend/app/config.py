from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/db.sqlite3"

    # JWT — MUST override in production via env (.env or platform secret).
    # Dev default exists only so local runs don't error out.
    SECRET_KEY: str = "dev-only-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 14  # 14 days

    # HikerAPI (Instagram data)
    HIKER_API_KEY: str = ""
    HIKER_API_BASE_URL: str = "https://api.hikerapi.com"

    # Instagram Publishing (Meta Graph API)
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""
    INSTAGRAM_ACCESS_TOKEN: str = ""

    # Image
    IMAGE_MAX_WIDTH: int = 1080
    IMAGE_MAX_HEIGHT: int = 1350
    DATA_DIR: Path = Path("data")

    # Transparent Image Sourcing (priority order)
    PIXABAY_API_KEY: str = ""       # 1����: 투명 스톡 이미지 검색
    FLATICON_API_KEY: str = ""      # 2순위: 투명 아이콘/일러스트
    OPENAI_API_KEY: str = ""        # 3순위: AI 누끼 이미지 생성
    REMOVEBG_API_KEY: str = ""      # 폴백: 배경 제거 API

    # Stock Images (일반)
    UNSPLASH_ACCESS_KEY: str = ""
    PEXELS_API_KEY: str = ""

    # Web Image Search
    BING_SEARCH_KEY: str = ""           # Azure Cognitive Services (1000회/월 무료)
    NAVER_CLIENT_ID: str = ""           # Naver Developers (25000회/일 무료)
    NAVER_CLIENT_SECRET: str = ""

    # Proxy for outbound scraping (Naver image search etc.)
    # Single URL form (http://user:pass@host:port) — rotated by ;
    # Empty → no proxy (direct connection from server IP)
    SCRAPING_PROXY_URLS: str = ""

    # Comma-separated list of origins allowed by CORS. In dev defaults cover
    # localhost; in prod set to your actual frontend domain(s).
    ALLOWED_ORIGINS: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3452,"
        "http://127.0.0.1:3000,http://127.0.0.1:3001,http://127.0.0.1:3452"
    )

    # AI / LLM — CLI-first (API keys only needed as fallback)
    # If `claude` CLI is installed → no ANTHROPIC_API_KEY needed
    # If `gemini` CLI is installed → no GEMINI_API_KEY needed
    ANTHROPIC_API_KEY: str = ""   # Fallback: Claude via API
    GEMINI_API_KEY: str = ""      # Fallback: Gemini via API
    GOOGLE_API_KEY: str = ""      # Fallback: Gemini via Google GenAI

    # OpenAI — only for GPT-Image (image generation), NOT for LLM
    OPENAI_API_KEY: str = ""      # GPT-Image 누끼 생성용

    # fal.ai — GPU-hosted vision models. Used for "일반 누끼" (BiRefNet bg removal).
    # Empty → fall back to local rembg (CPU, free but slower).
    FAL_KEY: str = ""

    class Config:
        env_file = ".env"


settings = Settings()

# Push API keys to os.environ so libraries like litellm and helpers that
# read os.environ directly can pick them up.
import os as _os
for _k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
    _v = getattr(settings, _k, "")
    if _v and not _os.environ.get(_k):
        _os.environ[_k] = _v
