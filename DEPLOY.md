# 배포 가이드 — AWS Lightsail Seoul

전체 스택(backend + frontend + nginx)을 단일 Lightsail VPS에 docker-compose로 띄웁니다.

## 1. Lightsail 인스턴스 만들기

콘솔: https://lightsail.aws.amazon.com/

- **Region**: Seoul (`ap-northeast-2`)
- **Platform**: Linux/Unix
- **Blueprint**: OS Only → Ubuntu 22.04 LTS
- **Instance plan**: $10/mo (2 GB RAM, 1 vCPU, 60 GB SSD) — 빌드 시 메모리 여유 있으려면 이 정도가 안전
- **Instance name**: `carousel-prod`

생성 후 **Networking** 탭에서:
- **Static IP** 만들고 인스턴스에 attach
- **Firewall** — 80(HTTP), 443(HTTPS), 22(SSH) 열려있는지 확인

## 2. SSH 들어가기

콘솔에서 `Connect using SSH` (또는 키 받아서 로컬에서):

```bash
ssh ubuntu@<static-ip>
```

## 3. Docker 설치

```bash
sudo apt update && sudo apt -y upgrade
sudo apt -y install docker.io docker-compose-plugin git curl
sudo usermod -aG docker ubuntu
exit       # 그룹 적용 위해 재로그인
```

다시 SSH 들어가서:

```bash
docker --version          # 확인
docker compose version    # plugin v2 확인
```

## 4. 코드 가져오기

```bash
cd /opt
sudo git clone https://github.com/dlalsgur78885-dotcom/claude-skills.git carousel
sudo chown -R ubuntu:ubuntu /opt/carousel
cd /opt/carousel
```

(다른 repo면 URL 교체)

## 5. 데이터 디렉터리 + 환경변수

```bash
sudo mkdir -p /var/app/data
sudo chown -R ubuntu:ubuntu /var/app/data

cp .env.example .env
nano .env
```

`.env`에 채워야 할 값:
- `DOMAIN` — 도메인 (아직 없으면 일단 빈칸. nginx HTTPS 블록은 cert 발급 후 활성화)
- `SECRET_KEY` — `openssl rand -hex 64`로 생성
- `GEMINI_API_KEY` — Google AI Studio
- `HIKER_API_KEY` — hikerapi.com
- `PEXELS_API_KEY`, `PIXABAY_API_KEY` — stock 이미지
- `SCRAPING_PROXY_URLS` — Naver 프록시 (옵션)
- `ALLOWED_ORIGINS` — 비워두면 `https://${DOMAIN}` 자동 사용

## 6. 도메인 연결 (도메인 있을 때)

Route 53 / 가비아 / Cloudflare에서:
- A 레코드: `your-domain.com` → Lightsail static IP

DNS 전파 확인:
```bash
dig +short your-domain.com
```

## 7. SSL 발급 (Let's Encrypt)

처음 띄울 때는 nginx의 HTTPS 블록을 잠시 주석 처리해서 80포트만 동작하게:

```bash
nano nginx.conf
# `server { listen 443 ssl; ...` 블록 통째로 주석 처리
# `location / { return 301 https://...` 도 잠시 주석 (or `return 404;`)
```

먼저 컨테이너 띄움:
```bash
docker compose up -d --build
```

webroot 폴더 만들기:
```bash
sudo mkdir -p /var/www/certbot
```

certbot 한 번 실행:
```bash
sudo apt -y install certbot
sudo certbot certonly --webroot -w /var/www/certbot -d your-domain.com
```

성공하면 `/etc/letsencrypt/live/your-domain.com/`에 cert 생김.

다시 `nginx.conf` 편집:
- `REPLACE_WITH_DOMAIN`을 실제 도메인으로 교체
- 주석 처리했던 부분 다시 활성화

재시작:
```bash
docker compose restart nginx
```

자동 갱신 cron:
```bash
echo "0 3 * * * certbot renew --quiet --post-hook 'docker compose -f /opt/carousel/docker-compose.yml restart nginx'" | sudo crontab -
```

## 8. 첫 실행

```bash
cd /opt/carousel
docker compose up -d --build
docker compose ps           # 3개 컨테이너 healthy 확인
docker compose logs -f      # 로그 확인 (Ctrl+C로 빠져나옴)
```

확인:
```bash
curl http://localhost/health           # {"status":"ok"}
curl http://localhost/api/auth/me      # 401 (인증 안 됐으니 정상)
```

브라우저: `https://your-domain.com`

## 9. 첫 admin 가입

브라우저에서 `/login` → 회원가입. 첫 가입자가 자동으로 admin.

## 10. 운영 명령어

```bash
# 코드 업데이트
cd /opt/carousel
git pull
docker compose up -d --build

# 로그
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f nginx

# 컨테이너 재시작
docker compose restart backend

# DB 백업
sudo cp /var/app/data/db.sqlite3 ~/db-backup-$(date +%Y%m%d).sqlite3

# 디스크 확인
df -h /var/app/data
du -sh /var/app/data/*
```

## 11. 데이터 정책

- **영구 보존**: `/var/app/data/db.sqlite3`, `/var/app/data/images/logos/`
- **자동 삭제 (3시간 TTL)**: `images/raw/`, `images/processed/`, `images/sourced/`, `images/restyled/`, `images/pool/`, `template_studio_cache/`
- 30분마다 cleanup job 실행 (backend의 APScheduler)

## 12. 비용 예상

- Lightsail $10/mo (2GB)
- 도메인 ~$12/year (Route 53 등)
- Vision/Image API — 사용량 따라 ($0.001~0.14 per call, 위 문서 참고)
- 총 운영 비용: 월 $10~30 (트래픽 적을 때)

## 트러블슈팅

- **502 Bad Gateway**: `docker compose logs backend` — 백엔드 죽었거나 healthcheck 실패
- **nginx exit (-1)**: ssl cert 경로 못 찾음. cert 발급 전이면 HTTPS 블록 주석 처리
- **CORS 에러**: `.env`의 `ALLOWED_ORIGINS` 확인, `docker compose restart backend`
- **디스크 가득**: `docker system prune -af` 후 cleanup job 강제 실행
  ```bash
  docker compose exec backend python -c "import asyncio; from app.services.scheduler import cleanup_images; asyncio.run(cleanup_images())"
  ```
- **Vision timeout**: 90초 이상 걸리는 호출은 nginx `proxy_read_timeout`을 더 늘림 (현재 180s)
