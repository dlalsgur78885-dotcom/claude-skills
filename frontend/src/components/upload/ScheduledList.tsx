"use client";

/**
 * 「내 작업 › 예약」 — 스튜디오에서 업로더로 보낸 캐러셀(대기·게시됨·실패)을 보고 고치고 취소한다.
 * 업로더의 「예약 목록」 과 같은 일을 한다(2026-10-06 트립앤라이프 피드백). 사진을 바꾸려면
 * 취소하고 에디터에서 다시 올린다 — 업로더 수정 API 가 사진 교체를 받지 않는다.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { api, resolveImageUrl } from "@/lib/api";
import type { ScheduledPost, ScheduledStatus, ScheduleEdit, UploaderAccounts } from "@/lib/types";
import {
  STATUS_LABEL, UploadFields, formatWhen, isoToLocal, localToIso, type UploadValues,
} from "./UploadFields";

const btn: React.CSSProperties = {
  padding: "5px 12px", fontSize: 12, borderRadius: 5, cursor: "pointer",
  background: "var(--bg-elevated)", color: "var(--text-secondary)", border: "1px solid var(--border)",
};

export default function ScheduledList() {
  const [items, setItems] = useState<ScheduledPost[] | null>(null);
  const [options, setOptions] = useState<UploaderAccounts | null>(null);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [editing, setEditing] = useState<ScheduledPost | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    try {
      const data = await api.scheduledPosts();
      setItems(data.items);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "예약 목록을 불러오지 못했습니다");
      setItems((prev) => prev ?? []);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { api.uploaderAccounts().then(setOptions).catch(() => {}); }, []);

  // 올라가는 중인 항목이 있으면 30초마다 다시 본다 — 업로더 크론이 1분마다 처리한다.
  const moving = (items || []).some((i) => i.status === "uploading" || i.status === "processing" || i.status === "pending");
  useEffect(() => {
    if (!moving) return;
    const t = setInterval(() => void load(), 30_000);
    return () => clearInterval(t);
  }, [moving, load]);

  async function remove(item: ScheduledPost) {
    const published = item.status === "published";
    const ok = window.confirm(published
      ? "인스타그램에서 이 게시물을 지웁니다. 되돌릴 수 없습니다."
      : "이 예약을 취소합니다.");
    if (!ok) return;
    setBusyId(item.id);
    try {
      await api.deleteScheduled(item.id);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "처리하지 못했습니다");
    } finally {
      setBusyId("");
    }
  }

  // 목록에서만 뺀다 — 인스타 게시물은 그대로라 되묻지 않는다(업로더 예약목록과 같다).
  async function hide(target: { id: string } | { done: true }, busy: string) {
    setBusyId(busy);
    try {
      await api.hideScheduled(target);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "목록에서 지우지 못했습니다");
    } finally {
      setBusyId("");
    }
  }

  if (items === null) return <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>예약 목록을 불러오는 중…</p>;

  // 일괄 지우기는 실패를 남긴다 — 실패는 이유를 보고 하나씩 지운다(업로더와 같은 규칙).
  const doneCount = items.filter((i) => i.status === "published" || i.status === "deleted").length;

  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
        <p style={{ fontSize: 12, color: "var(--text-tertiary)", margin: 0 }}>
          에디터의 [업로드]로 보낸 캐러셀입니다. 대기 중인 것은 캡션·시각·계정을 고칠 수 있고, 사진을 바꾸려면 취소한 뒤 다시 올려 주세요.
        </p>
        <div style={{ display: "flex", gap: 6 }}>
          {doneCount > 0 ? (
            <button style={btn} disabled={busyId === "done"} onClick={() => void hide({ done: true }, "done")}>
              게시·삭제된 항목 모두 지우기 ({doneCount})
            </button>
          ) : null}
          <button onClick={() => void load()} style={btn}>새로고침</button>
        </div>
      </div>
      {error ? <p role="alert" style={{ fontSize: 12, color: "var(--red)", margin: 0 }}>{error}</p> : null}
      {items.length === 0 ? (
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>아직 업로드한 캐러셀이 없어요. 에디터 오른쪽 위 [업로드]로 올릴 수 있습니다.</p>
      ) : items.map((item) => {
        const st = STATUS_LABEL[item.status as ScheduledStatus] ?? STATUS_LABEL.pending;
        const open = expanded.has(item.id);
        const thumb = item.carousel?.thumbnail_url ? resolveImageUrl(item.carousel.thumbnail_url) : "";
        return (
          <div key={item.id} style={{
            display: "grid", gridTemplateColumns: "64px 1fr", gap: 14, alignItems: "start",
            background: "var(--bg-subtle)", border: "1px solid var(--border)", borderRadius: 10, padding: 14,
          }}>
            <div style={{ width: 64, aspectRatio: "4 / 5", borderRadius: 6, overflow: "hidden", background: "var(--bg-elevated)" }}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {thumb ? <img src={thumb} alt="" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : null}
            </div>
            <div style={{ display: "grid", gap: 6, minWidth: 0 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span style={{ padding: "1px 8px", borderRadius: 999, fontSize: 11, fontWeight: 600, color: st.color, background: st.bg }}>{st.text}</span>
                <span style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", fontVariantNumeric: "tabular-nums" }}>{formatWhen(item.at)}</span>
                <span style={{ fontSize: 12, color: "var(--text-tertiary)" }}>@{item.account} · 캐러셀 {item.mediaCount}장</span>
                <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
                  {item.status === "pending" ? (
                    <>
                      <button style={btn} disabled={busyId === item.id} onClick={() => setEditing(item)}>수정</button>
                      <button style={btn} disabled={busyId === item.id} onClick={() => void remove(item)}>취소</button>
                    </>
                  ) : null}
                  {item.status === "published" ? (
                    <button style={btn} disabled={busyId === item.id} onClick={() => void remove(item)}>인스타에서 삭제</button>
                  ) : null}
                  {item.status === "published" || item.status === "deleted" || item.status === "failed" ? (
                    <button style={btn} disabled={busyId === item.id} onClick={() => void hide({ id: item.id }, item.id)}>목록에서 지우기</button>
                  ) : null}
                </div>
              </div>
              {item.carousel ? (
                <Link href={`/editor/${item.carousel.id}`} style={{ fontSize: 12, color: "var(--text-secondary)", textDecoration: "none" }}>
                  {item.carousel.title || `캐러셀 ${item.carousel.id}`} · 에디터 열기
                </Link>
              ) : null}
              <p style={{
                margin: 0, fontSize: 13, color: "var(--text-primary)", whiteSpace: "pre-line", lineHeight: 1.55,
                ...(open ? {} : { display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }),
              }}>{item.caption}</p>
              {item.caption.split("\n").length > 2 || item.caption.length > 90 ? (
                <button onClick={() => setExpanded((s) => { const n = new Set(s); if (n.has(item.id)) n.delete(item.id); else n.add(item.id); return n; })}
                        style={{ justifySelf: "start", background: "none", border: "none", padding: 0, fontSize: 12, color: "var(--accent)", cursor: "pointer" }}>
                  {open ? "접기" : "더보기"}
                </button>
              ) : null}
              {item.permalink ? (
                <a href={item.permalink} target="_blank" rel="noreferrer" style={{ fontSize: 12, color: "var(--accent)", wordBreak: "break-all" }}>{item.permalink}</a>
              ) : null}
              {item.status === "failed" && item.error ? (
                <p style={{ margin: 0, fontSize: 12, color: "var(--red)" }}>실패 이유: {item.error}</p>
              ) : null}
            </div>
          </div>
        );
      })}
      {editing ? (
        <EditModal item={editing} options={options} onClose={() => setEditing(null)}
                   onSaved={() => { setEditing(null); void load(); }} />
      ) : null}
    </div>
  );
}

function EditModal({
  item, options, onClose, onSaved,
}: {
  item: ScheduledPost;
  options: UploaderAccounts | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const initial: UploadValues = {
    account: item.account,
    caption: item.caption,
    atLocal: isoToLocal(item.at),
    autoRespond: item.autoRespond ?? true,
    preset: item.preset ?? options?.presets.find((p) => p.isDefault)?.id ?? "",
  };
  const [values, setValues] = useState<UploadValues>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function save() {
    setError("");
    // 바뀐 칸만 보낸다 — 업로더도 보낸 칸만 바꾼다.
    const change: ScheduleEdit = {};
    if (values.caption !== initial.caption) change.caption = values.caption;
    if (values.atLocal !== initial.atLocal) change.at = localToIso(values.atLocal);
    if (values.account !== initial.account) change.account = values.account;
    if (values.autoRespond !== initial.autoRespond) change.auto_respond = values.autoRespond;
    if (values.autoRespond && values.preset !== initial.preset) change.preset = values.preset || null;
    if (!Object.keys(change).length) return onClose();
    setSaving(true);
    try {
      await api.updateScheduled(item.id, change);
      onSaved();
    } catch (e) {
      setError(e instanceof Error ? e.message : "수정하지 못했습니다");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div onClick={() => !saving && onClose()} style={{
      position: "fixed", inset: 0, background: "rgba(0,0,0,0.78)", zIndex: 200,
      display: "flex", alignItems: "center", justifyContent: "center", padding: 24,
    }}>
      <div role="dialog" aria-modal="true" aria-labelledby="edit-scheduled-title" onClick={(e) => e.stopPropagation()} style={{
        background: "var(--bg-base, #141414)", border: "1px solid var(--border)", borderRadius: 12,
        width: "100%", maxWidth: 520, maxHeight: "calc(100vh - 48px)", overflowY: "auto",
        padding: 22, display: "grid", gap: 14, boxShadow: "0 20px 60px rgba(0,0,0,0.6)",
      }}>
        <h3 id="edit-scheduled-title" style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>예약 수정</h3>
        <UploadFields idPrefix={`edit-${item.id}`} values={values} onChange={setValues} options={options} disabled={saving} />
        {!values.atLocal ? (
          <p style={{ fontSize: 12, color: "var(--text-tertiary)", margin: 0 }}>예약 시각이 필요합니다. 바로 올리려면 지금보다 몇 분 뒤로 정해 주세요.</p>
        ) : null}
        {error ? <p role="alert" style={{ fontSize: 12, color: "var(--red)", margin: 0 }}>{error}</p> : null}
        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button onClick={onClose} disabled={saving} style={btn}>닫기</button>
          <button onClick={() => void save()} disabled={saving || !values.atLocal}
                  style={{ ...btn, background: "var(--accent)", color: "#fff", border: "none", fontWeight: 600,
                           opacity: saving || !values.atLocal ? 0.5 : 1 }}>
            {saving ? "저장 중…" : "저장"}
          </button>
        </div>
      </div>
    </div>
  );
}
