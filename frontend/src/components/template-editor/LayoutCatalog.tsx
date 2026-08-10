"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { LayoutCatalogItem } from "@/lib/types";
import { LayoutMiniPreview } from "./LayoutMiniPreview";
import type { TemplateData } from "./types";

/** 낱장 보기 — 템플릿을 레이아웃 한 장 단위로 펼쳐 보여준다.
 *
 *  세트 보기는 카드에 커버 한 장만 보여서 클릭해야 속을 알 수 있었고, `썸네일`·`CTA`
 *  같은 공통 장면이 세트마다 중복됐다. 여기서는 낱장을 전부 펼치고, 분류로 걸러보고,
 *  중복은 직접 숨길 수 있다.
 *
 *  숨김은 이 목록에서만 가린다 — 템플릿 원본은 그대로라 세트 보기는 계속 동작한다.
 */

const CATEGORIES = [
  { key: "all", label: "전체" },
  { key: "cover", label: "표지" },
  { key: "grid", label: "격자" },
  { key: "cta", label: "CTA" },
  { key: "body", label: "본문·단일" },
] as const;

type CategoryKey = (typeof CATEGORIES)[number]["key"];

const BADGE_COLOR: Record<LayoutCatalogItem["category"], string> = {
  cover: "var(--blue, #3b82f6)",
  grid: "var(--purple, #8b5cf6)",
  cta: "var(--amber, #f59e0b)",
  body: "var(--text-secondary)",
};

interface Props {
  /** 낱장을 골랐을 때. 없으면 둘러보기 전용(숨기기만 가능). */
  onPick?: (item: LayoutCatalogItem) => void;
}

export function LayoutCatalog({ onPick }: Props) {
  const [items, setItems] = useState<LayoutCatalogItem[]>([]);
  // template_id → 렌더에 필요한 전체 템플릿. 미리보기가 canvas/brand/layouts 를
  // 통째로 요구하므로 카탈로그와 별개로 받아둔다.
  const [templates, setTemplates] = useState<Record<number, TemplateData>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [category, setCategory] = useState<CategoryKey>("all");
  const [showHidden, setShowHidden] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await api.listLayoutCatalog();
      setItems(res.layouts);

      // 낱장 39개가 템플릿 13개에서 나오므로 템플릿 단위로만 받는다.
      // 순차로 돌면 폭포수가 되니 병렬로 던진다.
      const ids = [...new Set(res.layouts.map((l) => l.template_id))];
      const loaded = await Promise.all(
        ids.map((id) =>
          api
            .getTemplate(id)
            .then((t) => [id, t as unknown as TemplateData] as const)
            // 템플릿 하나가 실패해도 목록 전체를 죽이지 않는다 — 그 카드만 미리보기가 빈다.
            .catch(() => null),
        ),
      );
      setTemplates(Object.fromEntries(loaded.filter((x): x is readonly [number, TemplateData] => x !== null)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "낱장 목록을 불러오지 못했습니다");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggleHidden(item: LayoutCatalogItem) {
    const id = `${item.template_id}:${item.layout_key}`;
    setBusy(id);
    const next = !item.hidden;
    try {
      await api.setLayoutHidden(item.template_id, item.layout_key, next);
      setItems((prev) =>
        prev.map((x) =>
          x.template_id === item.template_id && x.layout_key === item.layout_key
            ? { ...x, hidden: next }
            : x,
        ),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "숨김 처리에 실패했습니다");
    } finally {
      setBusy(null);
    }
  }

  const counts = useMemo(() => {
    const visible = items.filter((x) => showHidden || !x.hidden);
    const c: Record<string, number> = { all: visible.length };
    for (const x of visible) c[x.category] = (c[x.category] ?? 0) + 1;
    return c;
  }, [items, showHidden]);

  const shown = useMemo(
    () =>
      items.filter(
        (x) => (showHidden || !x.hidden) && (category === "all" || x.category === category),
      ),
    [items, category, showHidden],
  );

  const hiddenCount = items.filter((x) => x.hidden).length;

  if (loading) return <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>낱장 불러오는 중…</p>;

  return (
    <div>
      {error && (
        <p style={{ fontSize: 12, color: "var(--red)", marginBottom: 10 }}>{error}</p>
      )}

      {/* 분류 필터 + 숨김 토글 */}
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 14, flexWrap: "wrap" }}>
        {CATEGORIES.map((c) => {
          const active = category === c.key;
          const n = counts[c.key] ?? 0;
          return (
            <button
              key={c.key}
              onClick={() => setCategory(c.key)}
              style={{
                padding: "5px 12px", fontSize: 12, borderRadius: 999,
                fontWeight: active ? 600 : 400,
                background: active ? "var(--text-primary)" : "var(--bg-elevated)",
                color: active ? "var(--bg-base)" : "var(--text-secondary)",
                border: "1px solid var(--border)",
                cursor: "pointer",
              }}
            >
              {c.label} {n > 0 && <span style={{ opacity: 0.7 }}>{n}</span>}
            </button>
          );
        })}

        <div style={{ flex: 1 }} />

        {hiddenCount > 0 && (
          <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-secondary)", cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={showHidden}
              onChange={(e) => setShowHidden(e.target.checked)}
            />
            숨긴 항목 보기 ({hiddenCount})
          </label>
        )}
      </div>

      {shown.length === 0 ? (
        <p style={{ fontSize: 13, color: "var(--text-secondary)" }}>
          {items.length === 0 ? "낱장이 없습니다. 먼저 템플릿을 만드세요." : "이 분류에 해당하는 낱장이 없습니다."}
        </p>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
          {shown.map((item) => {
            const id = `${item.template_id}:${item.layout_key}`;
            const tpl = templates[item.template_id];
            return (
              <div
                key={id}
                style={{
                  border: "1px solid var(--border)", borderRadius: 8, padding: 10,
                  background: "var(--bg-elevated)",
                  opacity: item.hidden ? 0.45 : 1,
                  display: "flex", flexDirection: "column", gap: 8,
                }}
              >
                <div
                  onClick={onPick && !item.hidden ? () => onPick(item) : undefined}
                  style={{
                    display: "flex", justifyContent: "center",
                    cursor: onPick && !item.hidden ? "pointer" : "default",
                  }}
                >
                  {tpl ? (
                    <LayoutMiniPreview template={tpl} layoutName={item.layout_key} size={104} />
                  ) : (
                    <div style={{ width: 104, height: 104, background: "var(--bg-base)", borderRadius: 4 }} />
                  )}
                </div>

                <div style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 0 }}>
                  <span
                    style={{
                      fontSize: 10, fontWeight: 600, color: BADGE_COLOR[item.category],
                      textTransform: "none",
                    }}
                  >
                    {item.label}
                  </span>
                  <span
                    title={`${item.template_name} / ${item.layout_key}`}
                    style={{
                      fontSize: 11, color: "var(--text-secondary)",
                      overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    }}
                  >
                    {item.template_name}
                  </span>
                </div>

                <button
                  onClick={() => void toggleHidden(item)}
                  disabled={busy === id}
                  style={{
                    padding: "4px 8px", fontSize: 11,
                    background: "transparent", color: "var(--text-secondary)",
                    border: "1px solid var(--border)", borderRadius: 5,
                    cursor: busy === id ? "default" : "pointer",
                    opacity: busy === id ? 0.5 : 1,
                  }}
                >
                  {item.hidden ? "다시 보이기" : "숨기기"}
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
