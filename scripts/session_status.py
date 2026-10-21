"""다른 방(작업 세션)이 지금 무엇을 하고 있는지 읽어서 보여 준다 — 읽기만 한다.

보고 전용 방(솔희-캐러셀2)이 쓴다. 디스코드 브리지가 방마다 Claude 세션을
하나 쓰고, 그 대화록을 `~/.claude/projects/<워크스페이스>/<세션ID>.jsonl` 에 남긴다.
방 → 세션ID 는 `캐러셀 봇/data/<봇>/bridge-sessions.json` 이 갖는다.

    python scripts/session_status.py            # 모든 방, 최근 3턴
    python scripts/session_status.py --turns 6  # 더 길게
    python scripts/session_status.py --room 캐러셀3
    python scripts/session_status.py --whoami "방금 사람이 보낸 말 일부"  # 내가 어느 방인지
"""

import argparse
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

BOT_ROOT = Path("C:/Users/PC/Desktop/클코/캐러셀 봇")
WORKSPACE = Path("C:/Users/PC/Desktop/클코/캐러셀 자동화")
TRANSCRIPTS = Path(os.path.expanduser("~")) / ".claude" / "projects" / "C--Users-PC-Desktop-----------"
KST = timezone(timedelta(hours=9))
MAX_TEXT = 400
PRIMER_HEAD = "[캐러셀 봇 브리지 세션 초기화]"


def rooms():
    """[(봇, 방이름, 세션ID)] — 설정과 세션 맵을 맞춰 본다."""
    out = []
    for cfg in sorted(BOT_ROOT.glob("config/channels.bot*.json")):
        bot = cfg.stem.split(".")[-1]
        chans = json.loads(cfg.read_text(encoding="utf-8")).get("channels", {})
        smap_path = BOT_ROOT / "data" / bot / "bridge-sessions.json"
        smap = json.loads(smap_path.read_text(encoding="utf-8")) if smap_path.exists() else {}
        for cid, entry in chans.items():
            sid = (smap.get(cid) or {}).get("sessionId")
            out.append((bot, entry.get("label", cid), sid))
    return out


def turns(path: Path, want: int):
    """대화록 끝에서 사람 요청·봇 답·마지막 도구를 뽑는다."""
    user, assistant, tool = [], [], None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        content = (row.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        text = " ".join(b.get("text", "") for b in content if b.get("type") == "text").strip()
        if row.get("type") == "user" and text and not text.startswith("<"):
            if text.startswith(PRIMER_HEAD):  # 프라이머는 사람이 쓴 말이 아니다
                continue
            user.append((row.get("timestamp"), text))
        elif row.get("type") == "assistant":
            if text:
                assistant.append((row.get("timestamp"), text))
            for b in content:
                if b.get("type") == "tool_use":
                    tool = b.get("name")
    return user[-want:], assistant[-want:], tool


def stamp(iso: str | None) -> str:
    if not iso:
        return "시각 모름"
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KST).strftime("%m-%d %H:%M")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=3)
    ap.add_argument("--room", default="")
    ap.add_argument("--whoami", default="", help="사람이 방금 보낸 말 일부 — 그 말이 적힌 대화록의 방을 찾는다")
    args = ap.parse_args()

    if args.whoami:
        hits = []
        for bot, label, sid in rooms():
            if not sid:
                continue
            path = TRANSCRIPTS / f"{sid}.jsonl"
            if not path.exists():
                continue
            if args.whoami in path.read_text(encoding="utf-8", errors="replace"):
                hits.append((path.stat().st_mtime, bot, label))
        if not hits:
            print("못 찾았다 — 사람이 보낸 말을 더 길게/정확히 넣어라")
        else:
            hits.sort(reverse=True)
            for _, bot, label in hits:
                print(f"이 방 = {label} ({bot})" if hits[0][2] == label else f"  (같은 말이 {label} 에도 있다)")
        return

    for bot, label, sid in rooms():
        if args.room and args.room not in label:
            continue
        print(f"\n=== {label} ({bot})")
        if not sid:
            print("  세션 없음 — 이 방은 아직 대화를 시작하지 않았다")
            continue
        path = TRANSCRIPTS / f"{sid}.jsonl"
        if not path.exists():
            print(f"  대화록 없음 ({sid[:8]}) — 세션이 비워졌을 수 있다")
            continue
        mtime = datetime.fromtimestamp(path.stat().st_mtime, KST)
        idle = (datetime.now(KST) - mtime).total_seconds() / 60
        state = "지금 돌고 있는 듯" if idle < 3 else f"{int(idle)}분 전 멈춤"
        print(f"  마지막 기록 {mtime:%m-%d %H:%M} ({state})")
        user, assistant, tool = turns(path, args.turns)
        for ts, text in user:
            print(f"  [사람 {stamp(ts)}] {text[:MAX_TEXT]}")
        for ts, text in assistant:
            print(f"  [봇 {stamp(ts)}] {text[:MAX_TEXT]}")
        if tool:
            print(f"  마지막으로 쓴 도구: {tool}")


if __name__ == "__main__":
    os.chdir(WORKSPACE)
    main()
