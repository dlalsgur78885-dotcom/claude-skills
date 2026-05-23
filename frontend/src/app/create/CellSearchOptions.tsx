"use client";

import { useState } from "react";
import {
  ALL_IMAGE_TYPES,
  MODIFIER_LABEL_KO,
  type ImageType,
  type ItemQueryPlan,
} from "@/lib/query-builder";

// Per-cell search controls — carousel studio feedback #15-16 (slide 5+).
// Sits above each cell's image-candidate grid in step 2 (이미지 선택). Lets
// the user steer what kind of images come back for THIS cell:
//
//   - 7개 modifier chip (음식·외관·내부·전경·풍경·분위기·제품)
//     기본 선택 = LLM이 plan.desired_image_types 에 넣은 값. 다중 선택 가능.
//   - "+ 추가" 입력칸으로 사용자 정의 modifier 단어 (`야경`, `겨울` 등)
//   - 지역 포함 토글 ([✓ 도쿄]) — plan.region_anchor 가 있을 때만 노출
//   - "↓ 이후 셀에 적용" 버튼 — 위 세 설정을 이후 모든 셀에 일괄 복사
//
// 토글이 바뀌면 onChange 가 호출되고, 부모(create/page)가 디바운스 후
// buildQueries → /images/search 재호출 → 후보 새로고침.

export interface CellSearchState {
  modifiers: ImageType[];          // override of plan.desired_image_types
  regionAnchorEnabled: boolean;    // default true
  customModifiers: string[];       // 사용자가 직접 추가한 단어들
}

interface Props {
  plan?: ItemQueryPlan;            // undefined = LLM 응답 아직 안 옴 (UI 비활성)
  state: CellSearchState;
  loading?: boolean;               // plan fetch / 재검색 중 표시
  onChange: (next: CellSearchState) => void;
  onApplyBelow?: () => void;       // 없으면 버튼 숨김 (마지막 셀)
}

const CHIP_BASE: React.CSSProperties = {
  padding: "4px 10px",
  fontSize: 11,
  fontWeight: 500,
  borderRadius: 14,
  cursor: "pointer",
  border: "1px solid var(--border)",
  background: "var(--bg-overlay)",
  color: "var(--text-secondary)",
  userSelect: "none",
};
const CHIP_ON: React.CSSProperties = {
  background: "var(--accent)",
  color: "white",
  border: "1px solid var(--accent)",
};

export function CellSearchOptions({ plan, state, loading, onChange, onApplyBelow }: Props) {
  const [customDraft, setCustomDraft] = useState("");

  function toggleModifier(m: ImageType) {
    const has = state.modifiers.includes(m);
    onChange({
      ...state,
      modifiers: has ? state.modifiers.filter((x) => x !== m) : [...state.modifiers, m],
    });
  }

  function toggleRegion() {
    onChange({ ...state, regionAnchorEnabled: !state.regionAnchorEnabled });
  }

  function addCustom() {
    const v = customDraft.trim();
    if (!v) return;
    if (state.customModifiers.includes(v)) {
      setCustomDraft("");
      return;
    }
    onChange({ ...state, customModifiers: [...state.customModifiers, v] });
    setCustomDraft("");
  }

  function removeCustom(c: string) {
    onChange({ ...state, customModifiers: state.customModifiers.filter((x) => x !== c) });
  }

  // 지역 anchor — UI에는 한국어 표기를 보여줌. ko 없으면 첫 form 언어로 폴백.
  const anchorLabel =
    plan?.region_anchor?.ko ||
    plan?.region_anchor?.ja ||
    plan?.region_anchor?.zh ||
    plan?.region_anchor?.en ||
    "";

  const disabled = !plan || loading;

  return (
    <div
      style={{
        display: "flex", flexDirection: "column", gap: 6,
        padding: "8px 10px", marginBottom: 8,
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        opacity: disabled ? 0.6 : 1,
      }}
    >
      {/* modifier chips + custom 입력 */}
      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 5 }}>
        <span style={{ fontSize: 10, color: "var(--text-tertiary)", marginRight: 4 }}>검색 옵션</span>

        {ALL_IMAGE_TYPES.map((m) => {
          const on = state.modifiers.includes(m);
          return (
            <button
              key={m}
              type="button"
              disabled={disabled}
              onClick={() => toggleModifier(m)}
              style={{ ...CHIP_BASE, ...(on ? CHIP_ON : {}) }}
              title={`${MODIFIER_LABEL_KO[m]} 이미지 우선 검색`}
            >
              {MODIFIER_LABEL_KO[m]}
            </button>
          );
        })}

        {/* 사용자 추가 modifier 들 — 회색-보라 칩 */}
        {state.customModifiers.map((c) => (
          <span
            key={c}
            style={{
              ...CHIP_BASE,
              background: "rgba(120,100,255,0.18)",
              color: "rgb(180,165,255)",
              border: "1px solid rgba(120,100,255,0.35)",
              display: "inline-flex", alignItems: "center", gap: 4,
            }}
          >
            {c}
            <button
              type="button"
              onClick={() => removeCustom(c)}
              disabled={disabled}
              title="제거"
              style={{
                background: "none", border: "none", padding: 0, lineHeight: 1,
                color: "rgb(180,165,255)", cursor: "pointer", fontSize: 12,
              }}
            >
              ✕
            </button>
          </span>
        ))}

        {/* + 추가 입력 */}
        <input
          type="text"
          value={customDraft}
          onChange={(e) => setCustomDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") { e.preventDefault(); addCustom(); }
          }}
          disabled={disabled}
          placeholder="+ 추가 (예: 야경, 겨울)"
          style={{
            width: 140, padding: "4px 8px", fontSize: 11,
            color: "var(--text-primary)",
            background: "var(--bg-base)",
            border: "1px solid var(--border)",
            borderRadius: 14,
          }}
        />
        {customDraft.trim() && (
          <button
            type="button"
            onClick={addCustom}
            disabled={disabled}
            style={{ ...CHIP_BASE, background: "var(--bg-base)" }}
          >
            추가
          </button>
        )}
      </div>

      {/* 지역 토글 + 적용 버튼 */}
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        {anchorLabel && (
          <button
            type="button"
            disabled={disabled}
            onClick={toggleRegion}
            title={`각 쿼리에 ${anchorLabel}을(를) 포함`}
            style={{
              ...CHIP_BASE,
              ...(state.regionAnchorEnabled ? CHIP_ON : {}),
              padding: "3px 10px",
            }}
          >
            지역 포함 {state.regionAnchorEnabled ? "✓" : "—"} {anchorLabel}
          </button>
        )}

        {loading && (
          <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>검색 중…</span>
        )}

        <span style={{ flex: 1 }} />

        {onApplyBelow && (
          <button
            type="button"
            disabled={disabled}
            onClick={onApplyBelow}
            title="이 셀의 modifier · 지역 설정을 이후 모든 셀에 일괄 적용"
            style={{
              padding: "3px 10px", fontSize: 11,
              color: "var(--text-secondary)",
              background: "var(--bg-base)",
              border: "1px solid var(--border)",
              borderRadius: 6,
              cursor: disabled ? "default" : "pointer",
            }}
          >
            ↓ 이후 셀에 적용
          </button>
        )}
      </div>
    </div>
  );
}
