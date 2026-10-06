"use client";

/**
 * 인스타 업로드 입력칸 — 에디터 [업로드] 창과 「내 작업 › 예약」 수정 창이 함께 쓴다.
 * 업로더(instagram-reel-uploader)의 「캐러셀 게시」 화면과 같은 칸을 같은 순서로 둔다
 * (2026-10-06 트립앤라이프 피드백 — 「해당 링크에 있는 기능 동일하게」).
 */

import type React from "react";
import type { ScheduledStatus, UploaderAccounts } from "@/lib/types";

export interface UploadValues {
  account: string;
  caption: string;
  /** datetime-local 값(이 컴퓨터 시각). 빈 문자열이면 바로 게시 */
  atLocal: string;
  autoRespond: boolean;
  preset: string;
}

export const fieldLabel: React.CSSProperties = {
  display: "block", fontSize: 11, color: "var(--text-tertiary)", marginBottom: 4,
};

export const fieldInput: React.CSSProperties = {
  width: "100%", padding: "7px 10px", fontSize: 13,
  background: "var(--bg-overlay)", color: "var(--text-primary)",
  border: "1px solid var(--border)", borderRadius: 5, outline: "none", font: "inherit",
};

/** datetime-local ↔ ISO. 브라우저가 이 컴퓨터의 시간대로 읽고 쓴다(한국이면 +09:00). */
export function localToIso(local: string): string {
  return local ? new Date(local).toISOString() : "";
}

export function isoToLocal(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}

export function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString("ko-KR", {
    year: "numeric", month: "numeric", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

export const STATUS_LABEL: Record<ScheduledStatus, { text: string; color: string; bg: string }> = {
  pending: { text: "대기", color: "var(--text-secondary)", bg: "var(--bg-elevated)" },
  uploading: { text: "올리는 중", color: "rgb(150,180,255)", bg: "rgba(90,130,255,0.16)" },
  processing: { text: "처리 중", color: "rgb(150,180,255)", bg: "rgba(90,130,255,0.16)" },
  published: { text: "게시됨", color: "rgb(160,230,190)", bg: "rgba(100,200,150,0.18)" },
  failed: { text: "실패", color: "rgb(255,160,150)", bg: "rgba(230,90,80,0.18)" },
  deleted: { text: "삭제됨", color: "var(--text-tertiary)", bg: "var(--bg-elevated)" },
};

export function UploadFields({
  values, onChange, options, disabled, idPrefix,
}: {
  values: UploadValues;
  onChange: (next: UploadValues) => void;
  options: UploaderAccounts | null;
  disabled?: boolean;
  idPrefix: string;
}) {
  const set = <K extends keyof UploadValues>(k: K, v: UploadValues[K]) => onChange({ ...values, [k]: v });
  return (
    <div style={{ display: "grid", gap: 12 }}>
      <div>
        <label htmlFor={`${idPrefix}-account`} style={fieldLabel}>계정</label>
        <select id={`${idPrefix}-account`} value={values.account} disabled={disabled || !options}
                onChange={(e) => set("account", e.target.value)} style={fieldInput}>
          {!options ? <option value="">계정을 불러오는 중…</option> : null}
          {options?.accounts.map((a) => (
            <option key={a.username} value={a.username}>
              @{a.username}{a.isDefault ? " (기본)" : ""}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label htmlFor={`${idPrefix}-caption`} style={fieldLabel}>
          캡션 <span style={{ fontVariantNumeric: "tabular-nums" }}>({values.caption.length}/2200)</span>
        </label>
        <textarea id={`${idPrefix}-caption`} value={values.caption} disabled={disabled} rows={7}
                  onChange={(e) => set("caption", e.target.value)}
                  style={{ ...fieldInput, resize: "vertical", lineHeight: 1.6 }} />
      </div>
      <div>
        <label htmlFor={`${idPrefix}-at`} style={fieldLabel}>예약 시각 (비워 두면 바로 게시)</label>
        <input id={`${idPrefix}-at`} type="datetime-local" value={values.atLocal} disabled={disabled}
               onChange={(e) => set("atLocal", e.target.value)} style={fieldInput} />
      </div>
      <label htmlFor={`${idPrefix}-auto`} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13, color: "var(--text-primary)" }}>
        <input id={`${idPrefix}-auto`} type="checkbox" checked={values.autoRespond} disabled={disabled}
               onChange={(e) => set("autoRespond", e.target.checked)} />
        이 게시물의 댓글에 자동 응답 사용
      </label>
      {values.autoRespond ? (
        <div>
          <label htmlFor={`${idPrefix}-preset`} style={fieldLabel}>사용할 템플릿</label>
          <select id={`${idPrefix}-preset`} value={values.preset} disabled={disabled || !options}
                  onChange={(e) => set("preset", e.target.value)} style={fieldInput}>
            {options?.presets.map((p) => (
              <option key={p.id} value={p.id}>{p.name}{p.isDefault ? " (기본)" : ""}</option>
            ))}
          </select>
        </div>
      ) : null}
    </div>
  );
}
