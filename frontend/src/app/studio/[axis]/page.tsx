"use client";

/**
 * 상황별 일본어 원클릭 스튜디오 — 한 화면에서 6단계를 끝낸다.
 *
 * 요청서: docs/process/개발요청_상황별일본어_원클릭대시보드.md
 * 화면 기준: 레포 루트 DESIGN.md (linear.app) — 색·간격·굴림·버튼 치수가 거기서 온다.
 *
 * ⚠ 이 파일에 프롬프트·톤·글자 수 규칙을 **베껴 넣지 않는다.** 규칙의 원본은
 *   docs/process 의 단계별 지침서이고, codex 가 있는 PC 의 일꾼이 그 파일을 읽어 쓴다.
 *
 * 화면이 하는 일은 셋뿐이다: **기다리고 · 보여주고 · 고른 것을 적는다.**
 * 짓는 것은 이 화면이 아니라 일꾼이다(`backend/app/services/studio_worker.py`).
 *
 * 2026-09-03 화면 검토에서 고친 것:
 *  ① 기다리는 중인지 알 수 없었다 → 맨 위 띠에 항상 보이게(접힌 단계 안에 숨지 않는다)
 *  ② 안 고른 단계도 초록 체크였다 → **값이 확정된** 단계만 체크
 *  ③ 사진 10장이 한 덩어리였다 → 지침서가 택1 하라는 단위(인물·풍경)로 나눠 보여준다
 *  ④ 「다시 뽑기」가 제일 눈에 띄었다 → 약한 버튼으로 내리고, 밤에 만들어 둔 것을
 *     지우게 되는 경우에만 한 번 더 묻는다
 *  ⑤ 보관 주제를 풀 수 없었다 → 「보관 해제」 되돌림
 *  ⑥ 단계마다 주소를 준다 → 진행 띠를 눌러 그 단계로 바로 간다(`#step-3`).
 *     새로고침·링크 공유에도 그 자리로 돌아온다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "next/navigation";
import {
  api,
  type StudioBodyItem,
  type StudioCta1,
  type StudioImage,
  type StudioSession,
  type StudioStep,
} from "@/lib/api";

// 색은 앱의 globals.css 변수를 그대로 쓴다 — accent(#5e6ad2)가 DESIGN.md 의 primary 와 같다.
// 치수(간격·굴림·버튼)는 DESIGN.md 값이다.
const T = {
  line: "1px solid var(--border)",
  muted: "var(--text-secondary)",
  faint: "var(--text-tertiary)",
  accent: "var(--accent)",
  card: "var(--bg-subtle)",
  raise: "var(--bg-elevated)",
  text: "var(--text-primary)",
  r: { sm: 6, md: 8, lg: 12, pill: 9999 },
  s: { xs: 8, sm: 12, md: 16, lg: 24 },
};

const SID_PARAM = "s";

/** 주소 한 조각 → 축 이름. 축을 늘리려면 여기와 백엔드 AXES 두 곳만 고치면 된다. */
const AXES: Record<string, { axis: string; title: string; scenery?: boolean; food?: boolean }> = {
  // 인물 말고 무엇을 더 그리는 축인지 — 백엔드 `AXES[축].cover_shots` 와 짝이다.
  // 상황별일본어는 풍경, 일본맛집은 음식이다(본문 배경은 실제 가게 사진이라 여기서 안 그린다).
  "ja-situations": { axis: "상황별일본어", title: "상황별 일본어", scenery: true },
  "ja-restaurants": { axis: "일본맛집", title: "일본 맛집", food: true },
  "map": { axis: "지도", title: "지도" },
};

/** 화면에 보이는 단계. 진행 띠와 주소(#step-n)가 이 순서를 쓴다.
 *  지도 축만 본문과 캡션 사이에 **CTA1** 이 하나 더 있다(지도_3-4단계).
 *  백엔드의 `studio_sessions.STEP_ORDER` 와 같은 순서여야 한다 — `reset_from` 이 이 번호다. */
const STEPS_DEFAULT = ["주제", "훅 문구", "사진", "본문", "캡션", "링크"] as const;
const STEPS_MAP = ["주제", "훅 문구", "지도", "본문", "CTA1", "캡션", "링크"] as const;

const WAITING: Record<StudioStep, string> = {
  topics: "주제 후보를 짓는 중… 20초쯤",
  hooks: "훅 문구를 짓는 중… 20초쯤",
  images: "사진을 그리는 중… 10장이면 6분쯤",
  body: "본문을 짓는 중… 40초쯤",
  cta1: "CTA1 문구를 짓는 중… 20초쯤",
  caption: "캡션을 짓는 중… 25초쯤",
  build: "캐러셀을 만드는 중… 10초쯤",
  keep: "보관함·제외 목록에 적는 중…",
  prepare: "주제 10개를 통째로 미리 만드는 중… 한 시간 넘게 걸립니다",
};

/** 「다시 뽑기」로 날아가는 시간. 확인 창에서 사람에게 그대로 보여준다. */
const REDO_COST: Partial<Record<StudioStep, string>> = {
  topics: "20초", hooks: "20초", images: "6분", body: "40초", cta1: "20초", caption: "25초",
};

const rowBetween: React.CSSProperties = {
  display: "flex", justifyContent: "space-between", alignItems: "center",
  gap: T.s.md, marginTop: T.s.md, flexWrap: "wrap",
};

function Btn({
  children, onClick, disabled, kind = "quiet", small,
}: {
  children: React.ReactNode; onClick?: () => void; disabled?: boolean;
  kind?: "primary" | "quiet" | "ghost"; small?: boolean;
}) {
  const style: React.CSSProperties = {
    font: "inherit",
    fontSize: small ? 13 : 14,
    fontWeight: 500,
    lineHeight: 1.2,
    padding: small ? "5px 10px" : "8px 14px",
    borderRadius: T.r.md,
    cursor: disabled ? "not-allowed" : "pointer",
    border: T.line,
    background: T.raise,
    color: T.text,
    ...(kind === "primary" ? { background: T.accent, borderColor: "transparent", color: "#fff" } : {}),
    ...(kind === "ghost" ? { background: "none", borderColor: "transparent", color: T.faint } : {}),
    ...(disabled ? { background: "var(--bg-overlay)", borderColor: "transparent", color: "var(--text-disabled)" } : {}),
  };
  return <button onClick={onClick} disabled={disabled} style={style}>{children}</button>;
}

type StepState = "idle" | "now" | "done";

function dotStyle(state: StepState, size: number): React.CSSProperties {
  return {
    width: size, height: size, borderRadius: T.r.pill, flex: "none",
    display: "grid", placeItems: "center",
    fontSize: size > 20 ? 13 : 11, fontWeight: 600,
    background: state === "done" ? "var(--green)" : state === "now" ? T.accent : T.raise,
    color: state === "done" ? "#04140a" : state === "now" ? "#fff" : T.faint,
    border: state === "idle" ? T.line : "none",
  };
}

/** 단계 묶음. 주소(#step-n)로 바로 열 수 있어야 해서 열림 상태를 밖에서 받는다. */
function Step({
  n, title, state, pick, open, onToggle, children,
}: {
  n: number; title: string; state: StepState;
  pick?: React.ReactNode; open: boolean; onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <section id={`step-${n}`} style={{
      border: T.line, borderRadius: T.r.lg, marginBottom: T.s.sm,
      overflow: "hidden", background: T.card, scrollMarginTop: 72,
    }}>
      <header onClick={onToggle} style={{
        display: "flex", alignItems: "center", gap: 10,
        padding: "14px 18px", cursor: "pointer", background: T.raise,
      }}>
        <span style={dotStyle(state, 24)}>{state === "done" ? "✓" : n}</span>
        <strong style={{ fontSize: 16, fontWeight: 500, color: T.text }}>{title}</strong>
        {!open && pick ? (
          <span style={{
            color: T.muted, fontSize: 14, flex: 1,
            overflow: "hidden", whiteSpace: "nowrap", textOverflow: "ellipsis",
          }}>{pick}</span>
        ) : <span style={{ flex: 1 }} />}
        <span style={{ color: T.faint, fontSize: 13 }}>{open ? "접기" : "펼쳐 고치기"}</span>
      </header>
      {open ? <div style={{ padding: T.s.md, borderTop: T.line }}>{children}</div> : null}
    </section>
  );
}

function Group({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: T.s.xs,
      fontSize: 13, fontWeight: 500, letterSpacing: ".4px",
      color: T.faint, margin: `${T.s.md}px 0 ${T.s.xs}px`,
    }}>
      {children}
      <span style={{ flex: 1, height: 1, background: "var(--border)" }} />
    </div>
  );
}

export default function AxisStudio() {
  const routeAxis = String(useParams()?.axis || "ja-situations");
  const AX = AXES[routeAxis] || AXES["ja-situations"];
  const [s, setS] = useState<StudioSession | null>(null);
  const [err, setErr] = useState("");
  const [dropped, setDropped] = useState<string[]>([]);
  const [excluded, setExcluded] = useState<Set<number>>(new Set());
  // 낱장 사진을 바꾼 것만 기록한다. 펼친 줄은 하나만 — 40장을 한꺼번에 늘어놓지 않는다.
  const [swapped, setSwapped] = useState<Record<number, string>>({});
  const [openShots, setOpenShots] = useState<number>(-1);
  const [captionDraft, setCaptionDraft] = useState<string | null>(null);
  const [cta1Draft, setCta1Draft] = useState<StudioCta1 | null>(null);
  const [openStep, setOpenStep] = useState(1);
  // 사진은 인물만·풍경만 따로 다시 그릴 수 있다 — kind 가 그것이다("" 면 둘 다).
  const [redo, setRedo] = useState<{ step: StudioStep; kind: string } | null>(null);
  // 크게 보고 있는 사진의 주소. "" 면 안 띄운다.
  const [zoom, setZoom] = useState("");
  // 그 사진이 **어느 낱장의 것**인지. -1 이면 표지 후보다.
  // 크게 띄운 화면에서 「고르기」가 표지냐 낱장 교체냐가 갈린다.
  const [zoomSlide, setZoomSlide] = useState(-1);
  const poll = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    const url = new URL(window.location.href);
    const existing = url.searchParams.get(SID_PARAM);
    const hash = window.location.hash.match(/^#step-([1-7])$/);
    if (hash) setOpenStep(Number(hash[1]));
    (async () => {
      try {
        // 주소에 회차가 있으면 그것. 없으면 **밤에 미리 만들어 둔 것**을 먼저 찾고,
        // 그것도 없을 때만 새로 연다 — 아침에 열자마자 고를 수 있게 하려는 것이다.
        let session: StudioSession;
        if (existing) {
          session = await api.studioGet(existing);
        } else {
          const ready = await api.studioLatest(AX.axis).catch(() => ({}));
          // ⚠ 새로 열 때 `pending` 을 비워 둔다. "topics" 로 열면 화면을 열자마자 일꾼이
          //    주제를 다시 짓는다 — 주소에 회차 번호가 없으면(메뉴·즐겨찾기) 들어올 때마다
          //    그랬다(2026-09-07 사람 신고). 새로 짓는 것은 **예약 시각**과 [다시 뽑기] 뿐이다.
          session = (ready as StudioSession).id ? (ready as StudioSession) : await api.studioCreate(AX.axis, "");
          url.searchParams.set(SID_PARAM, session.id);
          window.history.replaceState(null, "", url.toString() + window.location.hash);
        }
        setS(session);
      } catch (e) {
        setErr(String((e as Error).message || e));
      }
    })();
    return () => { if (poll.current) clearInterval(poll.current); };
  }, [AX.axis]);

  // 일꾼이 일하는 동안만 물어본다. 사람 차례엔 서버를 두드리지 않는다.
  useEffect(() => {
    if (poll.current) { clearInterval(poll.current); poll.current = null; }
    if (!s?.pending) return;
    poll.current = setInterval(async () => {
      try { setS(await api.studioGet(s.id)); } catch { /* 다음 차례에 다시 */ }
    }, 4000);
    return () => { if (poll.current) clearInterval(poll.current); };
  }, [s?.id, s?.pending]);

  /** 단계로 이동 — 주소에 남겨 새로고침·링크 공유에도 그 자리로 온다. */
  const jump = useCallback((n: number) => {
    setOpenStep(n);
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#step-${n}`);
    requestAnimationFrame(() => {
      document.getElementById(`step-${n}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }, []);

  const send = useCallback(async (
    body: Parameters<typeof api.studioPatch>[1], goto?: number,
  ) => {
    if (!s) return;
    setErr("");
    try {
      setS(await api.studioPatch(s.id, body));
      if (goto) jump(goto);
    } catch (e) { setErr(String((e as Error).message || e)); }
  }, [s, jump]);

  const cRaw = s?.candidates || {};
  const ch = s?.chosen || {};
  const busy = !!s?.pending;
  const prepared = cRaw.prepared || {};

  // 밤에 미리 만들어 둔 것이 있으면 그대로 쓴다 — 기다릴 필요가 없다.
  // 「다시 뽑기」로 새로 만든 것이 있으면 그쪽이 우선한다.
  const prep = prepared[ch.topic || ""] || {};
  const c = {
    ...cRaw,
    hooks: cRaw.hooks ?? prep.hooks,
    images: cRaw.images ?? prep.images,
    body: cRaw.body ?? prep.body,
    cta1: cRaw.cta1 ?? prep.cta1,
    caption: cRaw.caption ?? prep.caption,
  };
  // 보관한 주제는 위쪽 보관 상자에 뜬다. 후보 목록에도 남겨 두면 같은 줄이 두 번 보여 헷갈린다.
  // c.dropped 는 제외 목록에 쌓인 주제다 — 회차를 다시 열어도 안 보여야 하므로 여기서도 뺀다
  // (dropped 는 이번 화면에서 방금 누른 것. 서버 답이 오기 전에도 바로 사라지게 한다).
  const topicList = (c.topics || []).filter(
    (t) => !dropped.includes(t.topic)
        && !(c.dropped || []).includes(t.topic)
        && !(c.kept || []).includes(t.topic),
  );
  // 지도 축만 단계가 일곱이다. 번호(#step-n · reset_from)가 이 목록을 따른다.
  const hasCta1 = AX.axis === "지도";
  const STEPS = hasCta1 ? STEPS_MAP : STEPS_DEFAULT;
  const KEYS = hasCta1
    ? ["topics", "hooks", "images", "body", "cta1", "caption", "build"]
    : ["topics", "hooks", "images", "body", "caption", "build"];
  /** 그 단계가 화면에서 몇 번인지 — 축마다 다르므로 이름으로 찾는다. */
  const stepNo = (key: string) => KEYS.indexOf(key) + 1;

  const items = c.body || [];
  // 바꾼 사진만 담는다(낱장 번호 → 고른 주소). 안 건드린 낱장은 여기 없다.
  const chosenItems = items
    .map((it: StudioBodyItem, i: number) => (swapped[i] ? { ...it, photo: swapped[i] } : it))
    .filter((_, i: number) => !excluded.has(i));
  const caption = captionDraft ?? ch.caption ?? c.caption ?? "";
  // CTA1 도 캡션처럼 사람이 고쳐 쓸 수 있다. 고른 것 → 미리 만든 것 순.
  const cta1 = cta1Draft ?? ch.cta1 ?? c.cta1 ?? null;

  const photos = useMemo(() => {
    const all: StudioImage[] = c.images || [];
    return {
      person: all.filter((i) => i.kind === "person"),
      scenery: all.filter((i) => i.kind === "scenery"),
      food: all.filter((i) => i.kind === "food"),
      map: all.filter((i) => i.kind === "map"),
    };
  }, [c.images]);

  /** **값이 확정된** 단계만 done. 열어서 고르는 중이면 아직 done 이 아니다.
   *  축마다 단계 수가 달라(지도는 CTA1 이 하나 더) 번호가 아니라 **이름**으로 따진다. */
  const stepState = (n: number): StepState => {
    const key = KEYS[n - 1];
    const done: Record<string, boolean> = {
      topics: !!ch.topic, hooks: !!ch.hook_lines?.length, images: !!ch.image_url,
      body: !!ch.items?.length, cta1: !!ch.cta1, caption: !!s?.result, build: !!s?.result,
    };
    if (done[key]) return "done";
    const ready: Record<string, boolean> = {
      topics: true, hooks: !!ch.topic, images: !!ch.hook_lines?.length,
      body: !!ch.image_url, cta1: !!ch.items?.length,
      caption: hasCta1 ? !!ch.cta1 : !!ch.items?.length,
      build: hasCta1 ? !!ch.cta1 : !!ch.items?.length,
    };
    return ready[key] ? "now" : "idle";
  };

  /** 밤에 만들어 둔 것이 지워질 때만 묻는다. 없으면 그냥 짓는다. */
  const askRedo = (step: StudioStep, kind = "") => {
    if (ch.topic && prepared[ch.topic]) setRedo({ step, kind });
    else send(redoBody(step, kind));
  };
  /** 사진만 「무엇을 다시 그릴지」를 함께 보낸다. chosen 은 서버에서 합쳐지므로 매번 적는다. */
  const redoBody = (step: StudioStep, kind: string) =>
    step === "images" ? { pending: step, chosen: { image_kind: kind } } : { pending: step };

  // ── 고르기 — **이미 만들어 둔 것이 있으면 다시 짓지 않는다** (2026-09-03 사람 지시).
  //    누를 때마다 아래 단계를 날리고 새로 지어 사진에서 6분씩 버렸다. 새로 짓는 것은
  //    각 단계의 [다시 뽑기] 뿐이다.
  //    주제가 바뀔 때만 아래를 무효로 한다 — 훅이 바뀌어도 사진·본문은 그대로 쓴다.
  //    밤에 미리 만들 때도 그 둘은 훅 없이 주제만 보고 짓는다(`studio_worker._do_prepare`).

  const pickTopic = (topic: string) => {
    if (ch.topic === topic) return jump(2);
    // 지도 축은 주제가 곧 「어느 가이드의 어느 버튼」이다. 그 값을 함께 보내야 뒤 단계가
    // 같은 버튼의 장소·지도·수량을 쓴다. 후보 목록이나 미리 만들어 둔 것에서 찾는다.
    // (보관해 둔 주제는 문구만 남아 여기서 못 찾는데, 그때는 백엔드가 문구로 되찾는다.)
    const meta = (c.topics || []).find((t) => t.topic === topic) || prepared[topic] || {};
    const where = "guide_id" in meta && meta.guide_id
      ? {
          guide_id: meta.guide_id,
          button: (meta as { button?: string }).button || "",
          // 지역까지 좁힌 주제면 그것도 함께 — 장소·지도·수량이 그 지역을 따라간다.
          region: (meta as { region?: string }).region || "",
        }
      : {};
    send({ chosen: { topic, ...where }, reset_from: 2, pending: prepared[topic] ? "" : "hooks" }, 2);
  };

  const pickHook = (lines: string[]) => {
    if (ch.hook_lines?.join("\n") === lines.join("\n")) return jump(3);
    send({ chosen: { hook_lines: lines }, pending: c.images?.length ? "" : "images" }, 3);
  };

  const pickPhoto = (url: string) => {
    if (ch.image_url === url) return jump(4);
    send({ chosen: { image_url: url }, pending: c.body?.length ? "" : "body" }, 4);
  };

  if (err && !s) return <main style={{ padding: 40, color: "var(--red)" }}>{err}</main>;
  if (!s) return <main style={{ padding: 40, color: T.muted }}>회차를 여는 중…</main>;

  /** 캐러셀을 만들어 편집 링크까지 받은 주제 — 목록에서 [선택] 대신 [완료] 로 보인다. */
  const isBuilt = (topic: string) => (s.built || []).includes(topic);

  const closeZoom = () => { setZoom(""); setZoomSlide(-1); };
  /** 크게 띄운 사진이 속한 낱장이 **지금 쓰고 있는** 사진. 같으면 바꿀 것이 없다. */
  const zoomShot = zoomSlide >= 0
    ? (swapped[zoomSlide] || items[zoomSlide]?.photo || "")
    : "";

  // 다섯 칸으로 쪼개 놓으면 얼굴·글자가 안 보여 고를 수가 없다.
  // 그래서 누르면 **크게 띄우고**, 고르는 것은 그 큰 화면에서 한다.
  const photoRow = (list: StudioImage[]) => (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: T.s.xs }}>
      {list.map((im) => (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={im.url} src={im.url} alt={im.kind === "person" ? "인물 사진" : "풍경 사진"}
          onClick={() => { setZoomSlide(-1); setZoom(im.url); }}
          style={{
            width: "100%", aspectRatio: "2/3", objectFit: "cover", borderRadius: T.r.sm,
            cursor: "pointer", display: "block",
            border: ch.image_url === im.url ? `2px solid ${T.accent}` : "2px solid transparent",
            boxShadow: ch.image_url === im.url ? "0 0 0 3px var(--accent-muted)" : "none",
          }}
        />
      ))}
    </div>
  );

  return (
    <>
      {/* ── 맨 위 진행 띠 — 어디인지 · 무엇을 기다리는지 항상 보인다 ────────── */}
      <div style={{ position: "sticky", top: 0, zIndex: 20, background: "var(--bg-app)", borderBottom: T.line }}>
        <div style={{
          maxWidth: 880, margin: "0 auto", padding: "12px 20px",
          display: "flex", alignItems: "center", gap: T.s.md, flexWrap: "wrap",
        }}>
          <nav style={{ display: "flex", gap: 6, flex: 1, flexWrap: "wrap" }}>
            {STEPS.map((name, i) => {
              const n = i + 1;
              const st = stepState(n);
              return (
                <a key={n} href={`#step-${n}`}
                   onClick={(e) => { e.preventDefault(); jump(n); }}
                   style={{
                     display: "flex", alignItems: "center", gap: 6, fontSize: 13,
                     padding: "4px 10px", borderRadius: T.r.pill, textDecoration: "none",
                     border: openStep === n ? `1px solid ${T.accent}` : "1px solid transparent",
                     background: openStep === n ? "var(--accent-muted)" : "transparent",
                     color: st === "idle" ? T.faint : T.muted,
                   }}>
                  <span style={dotStyle(st, 18)}>{st === "done" ? "✓" : n}</span>
                  {name}
                </a>
              );
            })}
          </nav>
          {busy ? (
            <span style={{ color: T.accent, fontSize: 13, whiteSpace: "nowrap" }}>
              ● {WAITING[s.pending as StudioStep]}
            </span>
          ) : null}
        </div>
      </div>

      <main style={{ maxWidth: 880, margin: "0 auto", padding: "24px 20px 96px", fontSize: 16, lineHeight: 1.5 }}>
        <h1 style={{ fontSize: 28, fontWeight: 600, letterSpacing: "-.6px", margin: "8px 0 6px" }}>
          {AX.title} — 원클릭
          {/* 지금 고른 주제가 밤에 미리 만들어 둔 것일 때만 붙인다 — 아니면 배지가 거짓말이 된다. */}
          {Object.keys(prep).length > 0 ? (
            <span style={{
              fontSize: 13, fontWeight: 500, color: "var(--green)", marginLeft: 10,
              padding: "3px 10px", borderRadius: T.r.pill, verticalAlign: "3px",
              background: "var(--green-muted)", border: "1px solid var(--green)",
            }}>✓ 밤에 미리 만들어 둠</span>
          ) : null}
        </h1>
        <p style={{ color: T.faint, fontSize: 14, margin: `0 0 ${T.s.lg}px` }}>
          밤에 만들어 둔 것에서 고르기만 하면 됩니다. 규칙은 <code>docs/process</code> 의 단계별 지침서를 그대로 따릅니다.
        </p>

        {(err || s.error) ? (
          <div style={{
            background: "var(--red-muted)", color: "var(--red)", border: "1px solid var(--red)",
            borderRadius: T.r.md, padding: T.s.sm, marginBottom: T.s.md, fontSize: 14,
          }}>{err || s.error}</div>
        ) : null}

        {/* ── 1 주제 ─────────────────────────────────────── */}
        <Step n={1} title="주제 고르기" state={stepState(1)} pick={ch.topic}
              open={openStep === 1} onToggle={() => setOpenStep(openStep === 1 ? 0 : 1)}>
          {c.kept?.length ? (
            <div style={{ background: T.raise, border: T.line, borderRadius: T.r.md, padding: T.s.sm, marginBottom: T.s.md }}>
              <div style={{ fontSize: 13, color: T.faint, marginBottom: T.s.xs }}>보관해 둔 주제</div>
              {c.kept.map((t) => (
                <div key={t} style={{ display: "flex", gap: T.s.xs, alignItems: "center", padding: "6px 0" }}>
                  <span style={{ flex: 1 }}>{t}</span>
                  <Btn small kind="ghost" disabled={busy}
                       onClick={() => send({ chosen: { keep_topic: t, keep_off: true, drop_topic: "" }, pending: "keep" })}>보관 해제</Btn>
                  {isBuilt(t) ? (
                    <Btn small disabled={busy}
                         onClick={() => send({ chosen: { keep_topic: t, keep_off: true, drop_topic: "" }, pending: "keep" })}>✓ 완료</Btn>
                  ) : (
                    <Btn small kind="primary" disabled={busy}
                         onClick={() => pickTopic(t)}>선택</Btn>
                  )}
                </div>
              ))}
            </div>
          ) : null}

          <Group>이번 회차 후보 {topicList.length}개</Group>
          {topicList.length === 0 && !busy ? (
            <p style={{ color: T.muted, margin: "8px 0", fontSize: 14 }}>
              아직 없습니다. [다시 뽑기] 를 눌러 주세요. (예약 시각에 자동으로 채워집니다)
            </p>
          ) : null}
          {topicList.map((t) => (
            <div key={t.topic} style={{ display: "flex", gap: T.s.xs, alignItems: "flex-start", padding: "10px 0", borderTop: T.line }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 500 }}>{t.topic}</div>
                {t.why ? <div style={{ color: T.faint, fontSize: 14 }}>{t.why}</div> : null}
              </div>
              {/* 보관 = 다음 회차에 다시 나온다 / 삭제 = 제외 목록에 쌓여 다시 안 나온다.
                  chosen 은 **합쳐지므로** 반대쪽 칸을 빈 값으로 함께 보내 지운다 —
                  안 그러면 지난번에 누른 [삭제] 가 남아 [보관] 을 눌러도 또 삭제된다. */}
              <Btn small kind="ghost" disabled={busy}
                   onClick={() => send({
                     chosen: { keep_topic: t.topic, keep_off: false, drop_topic: "" }, pending: "keep",
                   })}>보관</Btn>
              <Btn small kind="ghost" disabled={busy}
                   onClick={() => {
                     setDropped((d) => [...d, t.topic]);
                     send({ chosen: { drop_topic: t.topic, keep_topic: "" }, pending: "keep" });
                   }}>삭제</Btn>
              {isBuilt(t.topic) ? (
                <Btn small onClick={() => setDropped((d) => [...d, t.topic])}>✓ 완료</Btn>
              ) : (
                <Btn small kind="primary" disabled={busy}
                     onClick={() => pickTopic(t.topic)}>선택</Btn>
              )}
            </div>
          ))}

          <div style={rowBetween}>
            <span style={{ color: T.faint, fontSize: 13 }}>이미 만든 주제와 삭제한 주제는 빼고 뽑습니다.</span>
            <Btn kind="ghost" disabled={busy} onClick={() => { setDropped([]); askRedo("topics"); }}>다시 뽑기</Btn>
          </div>
        </Step>

        {/* ── 2 훅 ───────────────────────────────────────── */}
        {ch.topic ? (
          <Step n={2} title="훅 문구 고르기" state={stepState(2)} pick={ch.hook_lines?.join(" ")}
                open={openStep === 2} onToggle={() => setOpenStep(openStep === 2 ? 0 : 2)}>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(16rem, 1fr))", gap: `0 ${T.s.lg}px` }}>
              {/* 지도 축은 표지가 하나라 2줄만 나온다 — 빈 묶음의 제목만 남으면 「3줄은 왜
                  비었지」 하고 헷갈린다. 후보가 있는 묶음만 보여준다. */}
              {([["three", "3줄 → 표지_3줄"], ["two", hasCta1 ? "2줄 → 표지_지도" : "2줄 → 표지_2줄"]] as const)
                .filter(([k]) => (c.hooks?.[k] || []).length > 0)
                .map(([k, label]) => (
                <div key={k}>
                  <Group>{label}</Group>
                  {(c.hooks?.[k] || []).map((h, i) => (
                    <div key={i} style={{ display: "flex", gap: T.s.xs, alignItems: "center", padding: "8px 0", borderTop: T.line }}>
                      <div style={{ flex: 1, whiteSpace: "pre-line", lineHeight: 1.45 }}>{h.lines.join("\n")}</div>
                      <Btn small kind="primary" disabled={busy}
                           onClick={() => pickHook(h.lines)}>선택</Btn>
                    </div>
                  ))}
                </div>
              ))}
            </div>
            <div style={rowBetween}>
              <span style={{ color: T.faint, fontSize: 13 }}>고른 줄 수가 표지 낱장을 정합니다.</span>
              <Btn kind="ghost" disabled={busy} onClick={() => askRedo("hooks")}>다시 뽑기</Btn>
            </div>
          </Step>
        ) : null}

        {/* ── 3 사진 ─────────────────────────────────────── */}
        {ch.hook_lines?.length ? (
          <Step n={3} title="썸네일 사진 고르기" state={stepState(3)} pick={ch.image_url ? "1장 선택됨" : ""}
                open={openStep === 3} onToggle={() => setOpenStep(openStep === 3 ? 0 : 3)}>
            {/* 지도 축은 그리는 게 아니라 **진짜 지도를 찍은 것**이라 한 묶음이다.
                다른 축은 지침서가 「인물 5 · 풍경 5 중 택 1」 이라 그 단위로 나눠 보여준다. */}
            {hasCta1 ? (
              <>
                <Group>지도 {photos.map.length}장</Group>
                {photoRow(photos.map)}
              </>
            ) : (
              <>
                <Group>
                  인물 {photos.person.length}장
                  <Btn small kind="ghost" disabled={busy} onClick={() => askRedo("images", "person")}>인물만 다시</Btn>
                </Group>
                {photoRow(photos.person)}
                {AX.scenery ? (
                  <>
                    <Group>
                      풍경 {photos.scenery.length}장
                      <Btn small kind="ghost" disabled={busy} onClick={() => askRedo("images", "scenery")}>풍경만 다시</Btn>
                    </Group>
                    {photoRow(photos.scenery)}
                  </>
                ) : null}
                {AX.food ? (
                  <>
                    <Group>
                      음식 {photos.food.length}장
                      <Btn small kind="ghost" disabled={busy} onClick={() => askRedo("images", "food")}>음식만 다시</Btn>
                    </Group>
                    {photoRow(photos.food)}
                  </>
                ) : null}
              </>
            )}
            <div style={rowBetween}>
              <span style={{ color: T.faint, fontSize: 13 }}>
                {hasCta1
                  ? "고른 1장이 표지·CTA1·CTA2 에 함께 들어갑니다. 장소 카드가 없는 컷을 고르세요."
                  : "고른 1장이 표지와 CTA 배경에 함께 들어갑니다."}
              </span>
              <Btn kind="ghost" disabled={busy} onClick={() => askRedo("images")}>
                {hasCta1 ? "다시 찍기" : "다시 그리기"}
              </Btn>
            </div>
          </Step>
        ) : null}

        {/* ── 4 본문 ─────────────────────────────────────── */}
        {ch.image_url ? (
          <Step n={4} title="본문 고르기" state={stepState(4)} pick={ch.items?.length ? `${ch.items.length}개 사용` : ""}
                open={openStep === 4} onToggle={() => setOpenStep(openStep === 4 ? 0 : 4)}>
            <p style={{ color: T.muted, fontSize: 14, margin: `0 0 ${T.s.xs}px` }}>
              뺄 것만 체크하세요. 지금 <b style={{ color: T.text }}>{chosenItems.length}개</b>가 들어갑니다.
            </p>
            {items.map((it: StudioBodyItem, i: number) => {
              const shot = swapped[i] || it.photo || "";
              // 가게를 다루는 축은 칸 이름이 다르다(name/where/desc). 사진도 여기만 있다.
              const isPlace = !!it.name;
              return (
                <div key={i} style={{ borderTop: T.line, opacity: excluded.has(i) ? 0.38 : 1 }}>
                  <label style={{ display: "flex", gap: T.s.sm, padding: "10px 0", cursor: "pointer" }}>
                    <input type="checkbox" checked={excluded.has(i)} style={{ marginTop: 6 }}
                      onChange={() => setExcluded((prev) => {
                        const n = new Set(prev); if (n.has(i)) n.delete(i); else n.add(i); return n;
                      })} />
                    {shot ? (
                      // 라벨 안이라 그냥 두면 누를 때 체크박스가 토글된다. 막고 크게 띄운다.
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={shot} alt="크게 보기" width={72} height={72}
                           onClick={(e) => { e.preventDefault(); e.stopPropagation(); setZoomSlide(i); setZoom(shot); }}
                           style={{ width: 72, height: 72, objectFit: "cover", borderRadius: T.r.md,
                                    flexShrink: 0, cursor: "zoom-in" }} />
                    ) : null}
                    {/* 지침서 형식 그대로 세로로. 큰따옴표·줄바꿈을 다듬지 않는다. */}
                    <div style={{ whiteSpace: "pre-line", minWidth: 0 }}>
                      <div style={{ fontWeight: 500 }}>{isPlace ? it.name : it.jp}</div>
                      <div style={{ color: T.muted, fontSize: 14 }}>{isPlace ? it.where : it.reading}</div>
                      <div>{isPlace ? it.desc : it.meaning}</div>
                      {isPlace ? null : <div style={{ color: T.faint, fontSize: 14 }}>{it.situation}</div>}
                    </div>
                  </label>
                  {(it.photos?.length || 0) > 1 ? (
                    <div style={{ paddingBottom: 10 }}>
                      <Btn kind="ghost" onClick={() => setOpenShots(openShots === i ? -1 : i)}>
                        {openShots === i ? "사진 닫기" : `사진 바꾸기 (${it.photos!.length}장)`}
                      </Btn>
                      {openShots === i ? (
                        <div style={{ display: "flex", gap: T.s.xs, overflowX: "auto", paddingTop: T.s.xs }}>
                          {/* 96px 로는 무엇이 찍혔는지 안 보인다 — 표지 후보와 똑같이
                              **누르면 크게 띄우고**, 고르는 것은 그 큰 화면에서 한다. */}
                          {it.photos!.map((u: string) => (
                            <button key={u} type="button" onClick={() => { setZoomSlide(i); setZoom(u); }}
                              style={{
                                padding: 0, background: "none", cursor: "pointer", flexShrink: 0, lineHeight: 0,
                                border: `2px solid ${u === shot ? T.accent : "transparent"}`, borderRadius: T.r.md,
                              }}>
                              {/* eslint-disable-next-line @next/next/no-img-element */}
                              <img src={u} alt="" width={96} height={96}
                                   style={{ width: 96, height: 96, objectFit: "cover", borderRadius: T.r.sm }} />
                            </button>
                          ))}
                        </div>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              );
            })}
            <div style={rowBetween}>
              <Btn kind="primary" disabled={busy || chosenItems.length === 0}
                   onClick={() => {
                     // 지도 축은 본문 다음이 캡션이 아니라 **CTA1** 이다.
                     const next = hasCta1 ? stepNo("cta1") : stepNo("caption");
                     const wait = hasCta1
                       ? (prep.cta1 ? "" : "cta1")
                       : (prep.caption ? "" : "caption");
                     return JSON.stringify(ch.items || []) === JSON.stringify(chosenItems)
                       ? jump(next)
                       : send({ chosen: { items: chosenItems }, reset_from: next, pending: wait }, next);
                   }}>
                이 {chosenItems.length}개로 진행
              </Btn>
              <Btn kind="ghost" disabled={busy} onClick={() => { setExcluded(new Set()); setSwapped({}); setOpenShots(-1); askRedo("body"); }}>다시 뽑기</Btn>
            </div>
          </Step>
        ) : null}

        {/* ── CTA1 (지도 축만) ───────────────────────────── */}
        {hasCta1 && ch.items?.length ? (
          <Step n={stepNo("cta1")} title="CTA1 문구" state={stepState(stepNo("cta1"))}
                pick={ch.cta1 ? "확정됨" : ""}
                open={openStep === stepNo("cta1")}
                onToggle={() => setOpenStep(openStep === stepNo("cta1") ? 0 : stepNo("cta1"))}>
            {/* 세 칸이 각각 다른 슬롯으로 간다 — 한 칸에 뭉치지 않는다(지도_3-4단계). */}
            {cta1 ? (
              <div style={{ display: "grid", gap: T.s.sm }}>
                {([
                  ["강조 (2줄)", "headline"],
                  ["공감·수량 (1줄)", "subtext"],
                  ["팔로우 유도 (2줄)", "body"],
                ] as const).map(([label, key]) => (
                  <label key={key} style={{ display: "grid", gap: 4 }}>
                    <span style={{ color: T.faint, fontSize: 13 }}>{label}</span>
                    <textarea
                      value={cta1[key] || ""} rows={key === "subtext" ? 1 : 2}
                      onChange={(e) => setCta1Draft({ ...cta1, [key]: e.target.value })}
                      style={{
                        width: "100%", padding: T.s.sm, border: T.line, borderRadius: T.r.md,
                        background: "var(--bg-app)", color: T.text, font: "inherit", fontSize: 14, lineHeight: 1.6,
                      }}
                    />
                  </label>
                ))}
              </div>
            ) : (
              <p style={{ color: T.muted, margin: 0, fontSize: 14 }}>아직 없습니다. [다시 뽑기] 를 눌러 주세요.</p>
            )}
            <div style={rowBetween}>
              <Btn kind="primary" disabled={busy || !cta1}
                   onClick={() => send(
                     { chosen: { cta1 }, pending: prep.caption ? "" : "caption" },
                     stepNo("caption"),
                   )}>
                이 문구로 진행
              </Btn>
              <Btn kind="ghost" disabled={busy}
                   onClick={() => { setCta1Draft(null); askRedo("cta1"); }}>다시 뽑기</Btn>
            </div>
          </Step>
        ) : null}

        {/* ── 캡션 ───────────────────────────────────────── */}
        {ch.items?.length && (!hasCta1 || ch.cta1) ? (
          <Step n={stepNo("caption")} title="캡션 문구" state={stepState(stepNo("caption"))}
                pick={s.result ? "확정됨" : ""}
                open={openStep === stepNo("caption")}
                onToggle={() => setOpenStep(openStep === stepNo("caption") ? 0 : stepNo("caption"))}>
            <textarea
              value={caption} onChange={(e) => setCaptionDraft(e.target.value)} rows={11}
              style={{
                width: "100%", padding: T.s.sm, border: T.line, borderRadius: T.r.md,
                background: "var(--bg-app)", color: T.text, font: "inherit", fontSize: 14, lineHeight: 1.7,
              }}
            />
            <div style={rowBetween}>
              <Btn kind="primary" disabled={busy}
                   onClick={() => send({ chosen: { caption }, pending: "build" }, stepNo("build"))}>
                확인 — 캐러셀 만들기
              </Btn>
              <Btn kind="ghost" disabled={busy} onClick={() => { setCaptionDraft(null); askRedo("caption"); }}>재생성</Btn>
            </div>
          </Step>
        ) : null}

        {/* ── 링크 ───────────────────────────────────────── */}
        {(s.pending === "build" || s.result) ? (
          <Step n={stepNo("build")} title="편집 링크" state={stepState(stepNo("build"))}
                pick={s.result ? `#${s.result.id}` : ""}
                open={openStep === stepNo("build") || !!s.result}
                onToggle={() => setOpenStep(openStep === stepNo("build") ? 0 : stepNo("build"))}>
            {s.result ? (
              <div style={{ padding: T.s.md, background: T.raise, borderRadius: T.r.md }}>
                <div style={{ marginBottom: T.s.xs }}>
                  낱장 {s.result.slides}장 · 캐러셀 #{s.result.id}
                  {s.result.history_recorded ? " · 제작 이력에 기록됨" : " · ⚠ 이력 기록 실패"}
                </div>
                <a href={s.result.url} target="_blank" rel="noreferrer" style={{ color: T.accent, fontWeight: 500 }}>
                  편집기에서 열기 →
                </a>
              </div>
            ) : (
              <p style={{ color: T.muted, margin: 0, fontSize: 14 }}>만들고 있습니다. 잠시만요.</p>
            )}
          </Step>
        ) : null}
      </main>

      {/* ── 「다시 뽑기」 확인 — 밤에 만들어 둔 것이 지워질 때만 뜬다 ─────── */}
      {redo ? (
        <div onClick={() => setRedo(null)} style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,.6)", zIndex: 50,
          display: "grid", placeItems: "center", padding: T.s.md,
        }}>
          <div onClick={(e) => e.stopPropagation()} style={{
            background: T.card, border: T.line, borderRadius: T.r.lg,
            padding: T.s.lg, maxWidth: 380, color: T.text,
          }}>
            <p style={{ margin: `0 0 ${T.s.md}px`, fontSize: 15, lineHeight: 1.6 }}>
              <b>다시 뽑으면 밤에 만들어 둔 것이 지워집니다.</b><br />
              {redo.kind ? (redo.kind === "person" ? "인물 5장만 " : "풍경 5장만 ") : ""}
              새로 짓는 데 {redo.kind ? "3분" : (REDO_COST[redo.step] || "시간이")} 걸립니다.
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: T.s.xs }}>
              <Btn onClick={() => setRedo(null)}>그대로 둘게요</Btn>
              <Btn kind="primary" onClick={() => { const r = redo; setRedo(null); send(redoBody(r.step, r.kind)); }}>
                다시 뽑기
              </Btn>
            </div>
          </div>
        </div>
      ) : null}

      {/* ── 사진 크게 보기 — 고르는 것도 여기서 한다 ─────────────────── */}
      {zoom ? (
        <div onClick={closeZoom} style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,.8)", zIndex: 60,
          display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
          gap: T.s.md, padding: T.s.lg,
        }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={zoom} alt="" onClick={(e) => e.stopPropagation()} style={{
            maxWidth: "min(92vw, 720px)", maxHeight: "78vh", objectFit: "contain",
            borderRadius: T.r.md, display: "block",
          }} />
          <div onClick={(e) => e.stopPropagation()} style={{ display: "flex", alignItems: "center", gap: T.s.xs }}>
            {/* 표지 후보냐(-1) 본문 낱장 사진이냐에 따라 고르는 일이 다르다. */}
            {zoomSlide >= 0 ? (
              zoomShot === zoom ? (
                <span style={{ color: "#fff", fontSize: 14 }}>이 낱장에 지금 쓰는 사진입니다</span>
              ) : (
                <Btn kind="primary"
                     onClick={() => { setSwapped((p) => ({ ...p, [zoomSlide]: zoom })); setOpenShots(-1); closeZoom(); }}>
                  이 사진으로 바꾸기
                </Btn>
              )
            ) : ch.image_url === zoom ? (
              <span style={{ color: "#fff", fontSize: 14 }}>이미 고른 사진입니다</span>
            ) : (
              <Btn kind="primary" disabled={busy}
                   onClick={() => { const url = zoom; closeZoom(); pickPhoto(url); }}>
                이 사진으로 선택
              </Btn>
            )}
            <Btn onClick={closeZoom}>닫기</Btn>
          </div>
        </div>
      ) : null}
    </>
  );
}
