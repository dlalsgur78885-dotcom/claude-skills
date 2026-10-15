from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/db.sqlite3"

    # Background jobs: 소재 수집 / 이미지 정리 / post 만료 / VACUUM.
    # 같은 코드로 인스턴스를 하나 더 띄울 때(dev 등) 반드시 False 로 둘 것 —
    # 스케줄러가 둘이면 채널을 회차당 두 번 긁고, 정리·만료 잡이 중복 실행된다.
    ENABLE_SCHEDULER: bool = True

    # JWT — MUST override in production via env (.env or platform secret).
    # Dev default exists only so local runs don't error out.
    SECRET_KEY: str = "dev-only-change-me"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 14  # 14 days

    # 원클릭 스튜디오 일꾼(services/studio_worker.py)이 들락거릴 서버.
    # 화면·회차 상태·템플릿·편집기가 전부 그쪽에 있고, 이 PC 는 codex 작업만 맡는다.
    # 비어 있으면 일꾼이 켜지지 않는다(서버에서 이 코드가 돌 때가 그렇다).
    STUDIO_API_BASE: str = ""
    STUDIO_ACCOUNT: str = ""
    STUDIO_PASSWORD: str = ""

    # 축마다 **다른 계정**으로 캐러셀을 만들어야 할 때 쓴다 — `아이디:비번,아이디:비번`.
    # 왜 필요한가: 템플릿도 캐러셀도 **계정별**이라, 준혁 축을 솔희 계정으로 만들면
    # 준혁이 편집 링크를 열어도 자기 캐러셀이 없다(트래블뷰 80 이 solhee 에만 있던 것과 같은 일).
    # 축에 계정이 정해져 있지 않으면 위 STUDIO_ACCOUNT 로 만든다.
    # ⚠ 회차 상태를 들고 다니는 일꾼은 여기 안 쓴다 — 그건 STUDIO_ACCOUNT 하나로 충분하다.
    STUDIO_ACCOUNTS: str = ""

    # 출근 전에 미리 다 만들어 둘 시각 (KST). 쉼표로 여러 개 — 예: "23:00,06:00".
    # 두 번 도는 이유는 한 번이 실패해도 아침에 빈손이 되지 않게 하려는 것이다.
    # 비우면 안 돈다.
    # ⚠ 공용 스케줄러(ENABLE_SCHEDULER)를 쓰지 않는다 — 그것을 켜면 소재 수집까지
    #   같이 돌아 채널을 두 번 긁는다. 그래서 일꾼이 자기 시계를 본다.
    STUDIO_PREPARE_AT: str = ""
    STUDIO_PREPARE_COUNT: int = 10

    # 엔 → 원 환산율 — **1엔이 몇 원인가**(원 = 엔 × 이 값). 일본숙소 축이 쟈란 요금을
    # 「2인 N만원대」로 바꿀 때 쓴다(`services/jalan_lookup.py`).
    # 8.4156 은 2026-10 회차 스크립트(`.work/sukso46/jprice3.py` `R=8.4156`)가 쓰던 값이다 —
    # 「7,700엔 ≈ 1인 3만 2천원」(1단계 회차 기록)과 맞는 방향이다. 환율이 크게 움직이면
    # .env 의 JPY_KRW_RATE 로 덮어쓴다. 범위(만원대)로만 쓰므로 소수점까지 맞출 일은 없다.
    JPY_KRW_RATE: float = 8.4156

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

    # 캔버스/템플릿 저장(JSON) 본문 상한(MB). 이미지 업로드(multipart)는 해당 없음.
    # 실측(2026-08-26, prod+dev 캐러셀 33건): 정상 최대 0.065MB, 템플릿 최대 0.006MB.
    # 2MB 는 그 30배로 여유가 크고, 사고를 낸 17.5MB 는 확실히 막는다.
    MAX_CANVAS_SAVE_MB: float = 2.0

    # 로컬 누끼(rembg) 허용 여부. 메모리가 좁은 인스턴스에서는 반드시 false 로 둘 것.
    # rembg 는 onnx 모델(~170MB)을 내려받아 RAM 에 올리는데, 그 스파이크가 한도를 넘으면
    # 커널이 uvicorn 워커를 죽인다. 그러면 컨테이너는 Up 인 채 모든 요청이 504 가 되고,
    # 겉으로는 "봇이 먹통" 으로만 보여 원인을 찾기 어렵다(2026-08-25 dev 에서 두 번 발생).
    # false 면 폴백 대신 명확한 에러를 낸다 — 누끼 한 장을 포기하고 서비스를 살린다.
    ALLOW_LOCAL_CUTOUT: bool = True

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
