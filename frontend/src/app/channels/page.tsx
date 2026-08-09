"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Channel, Category } from "@/lib/types";
import { ChannelTemplatesModal } from "@/components/ChannelTemplatesModal";

export default function ChannelsPage() {
  const [channels, setChannels] = useState<Channel[]>([]);
  const [loading, setLoading] = useState(true);
  const [mode, setMode] = useState<"none" | "single" | "bulk">("none");
  const [handle, setHandle] = useState("");
  const [category, setCategory] = useState("");
  const [groups, setGroups] = useState<Category[]>([]);
  const [bulk, setBulk] = useState("");
  const [adding, setAdding] = useState(false);
  const [bulkResults, setBulkResults] = useState<{ handle: string; ok: boolean; msg?: string }[]>([]);
  const [scraping, setScraping] = useState<Set<string>>(new Set());
  const [scrapingAll, setScrapingAll] = useState(false);
  const [templatesFor, setTemplatesFor] = useState<Channel | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);

  useEffect(() => {
    loadChannels();
    // 그룹 = 설정 > 카테고리 관리에서 만든 목록. 자유 입력을 두면 오타 하나로
    // 같은 그룹이 둘로 갈라져 소재 필터가 새기 때문에 목록에서만 고르게 한다.
    api.getCategories().then(setGroups).catch(() => setGroups([]));
  }, []);

  async function loadChannels() {
    try { setChannels(await api.getChannels()); }
    catch { /* ignore */ }
    finally { setLoading(false); }
  }

  async function changeGroup(id: number, value: string) {
    const before = channels;
    setChannels((cs) => cs.map((c) => (c.id === id ? { ...c, category: value } : c)));
    try {
      await api.updateChannel(id, { category: value });
    } catch (err) {
      setChannels(before);
      alert(err instanceof Error ? err.message : "그룹 변경 실패");
    }
  }

  async function addSingle(e: React.FormEvent) {
    e.preventDefault();
    if (!handle.trim() || adding) return;
    setAdding(true);
    try {
      await api.createChannel({ instagram_handle: handle.replace("@", "").trim(), category: category.trim() });
      setHandle(""); setCategory(""); setMode("none");
      loadChannels();
    } catch (err) {
      alert(err instanceof Error ? err.message : "채널 추가 실패");
    } finally { setAdding(false); }
  }

  function parseHandles(raw: string): string[] {
    return raw.split(/[\n,]+/)
      .map((s) => s.trim())
      .map((s) => s.replace(/^https?:\/\/(www\.)?instagram\.com\//i, "").replace(/\//g, "").replace(/^@/, ""))
      .filter(Boolean);
  }

  async function addBulk(e: React.FormEvent) {
    e.preventDefault();
    const handles = parseHandles(bulk);
    if (!handles.length || adding) return;
    setAdding(true);
    setBulkResults([]);
    const results: { handle: string; ok: boolean; msg?: string }[] = [];
    for (const h of handles) {
      try {
        await api.createChannel({ instagram_handle: h, category: category.trim() });
        results.push({ handle: h, ok: true });
      } catch (err) {
        results.push({ handle: h, ok: false, msg: err instanceof Error ? err.message : "실패" });
      }
    }
    setBulkResults(results);
    setBulk("");
    setAdding(false);
    loadChannels();
  }

  async function removeChannel(id: number) {
    if (!confirm("이 채널을 삭제하시겠습니까?")) return;
    try {
      await api.deleteChannel(id);
      setSelectedIds((prev) => { const n = new Set(prev); n.delete(id); return n; });
      loadChannels();
    } catch (err) {
      alert(err instanceof Error ? err.message : "삭제 실패");
    }
  }

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const n = new Set(prev);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  function toggleSelectAll() {
    setSelectedIds((prev) =>
      prev.size === channels.length ? new Set() : new Set(channels.map((c) => c.id))
    );
  }

  async function bulkDelete() {
    if (selectedIds.size === 0 || bulkDeleting) return;
    if (!confirm(`선택한 ${selectedIds.size}개 채널을 삭제하시겠습니까?`)) return;
    setBulkDeleting(true);
    try {
      await api.bulkDeleteChannels(Array.from(selectedIds));
      setSelectedIds(new Set());
      await loadChannels();
    } catch (err) {
      alert(err instanceof Error ? err.message : "일괄 삭제 실패");
    } finally {
      setBulkDeleting(false);
    }
  }

  async function scrapeOne(h: string) {
    setScraping((prev) => new Set(prev).add(h));
    try { await api.scrapeChannel(h); } catch { /* ignore */ }
    setTimeout(() => {
      setScraping((prev) => { const n = new Set(prev); n.delete(h); return n; });
      loadChannels();
    }, 8000);
  }

  async function scrapeAll() {
    setScrapingAll(true);
    try { await api.triggerScrape(); } catch { /* ignore */ }
    setTimeout(() => { setScrapingAll(false); loadChannels(); }, 15000);
  }

  const bulkCount = parseHandles(bulk).length;

  return (
    <div style={{ padding: "32px 40px", maxWidth: 960, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-primary)", letterSpacing: "-0.02em", margin: 0 }}>
            벤치마크 채널
          </h1>
          <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginTop: 4 }}>
            모니터링할 인스타그램 채널 관리
            {!loading && <span style={{ marginLeft: 8, color: "var(--text-secondary)" }}>{channels.length}개</span>}
          </p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {selectedIds.size > 0 && (
            <button onClick={bulkDelete} disabled={bulkDeleting}
              style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", fontSize: 12, fontWeight: 500, color: "var(--red)", background: "var(--red-muted)", border: "1px solid var(--red)", borderRadius: 6, cursor: bulkDeleting ? "default" : "pointer", opacity: bulkDeleting ? 0.6 : 1 }}>
              {bulkDeleting ? "삭제 중..." : `선택 삭제 (${selectedIds.size})`}
            </button>
          )}
          <button onClick={scrapeAll} disabled={scrapingAll}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", fontSize: 12, fontWeight: 500, color: scrapingAll ? "var(--text-disabled)" : "var(--text-secondary)", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6, cursor: scrapingAll ? "default" : "pointer" }}>
            {scrapingAll ? <><div className="spinner" style={{ width: 12, height: 12, borderWidth: 1.5 }} /> 수집 중...</> : (
              <><svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={1.8} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182" /></svg>전체 수집</>
            )}
          </button>
          <button onClick={() => setMode(mode === "bulk" ? "none" : "bulk")}
            style={{ padding: "6px 14px", fontSize: 12, fontWeight: 500, color: mode === "bulk" ? "var(--accent-text)" : "var(--text-secondary)", background: mode === "bulk" ? "var(--accent-muted)" : "var(--bg-elevated)", border: `1px solid ${mode === "bulk" ? "var(--accent)" : "var(--border)"}`, borderRadius: 6, cursor: "pointer" }}>
            대량 추가
          </button>
          <button onClick={() => setMode(mode === "single" ? "none" : "single")}
            style={{ display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", fontSize: 12, fontWeight: 500, color: "white", background: "var(--accent)", border: "none", borderRadius: 6, cursor: "pointer" }}>
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>
            채널 추가
          </button>
        </div>
      </div>

      {/* Single add */}
      {mode === "single" && (
        <form onSubmit={addSingle}
          style={{ display: "flex", gap: 8, alignItems: "center", padding: 14, marginBottom: 16, background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 8 }}>
          <div style={{ flex: 1, position: "relative" }}>
            <span style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", fontSize: 13, color: "var(--text-tertiary)" }}>@</span>
            <input type="text" value={handle} onChange={(e) => setHandle(e.target.value)} placeholder="인스타그램 핸들" autoFocus
              style={{ width: "100%", padding: "7px 10px 7px 26px", fontSize: 13, background: "var(--bg-overlay)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 5, outline: "none" }} />
          </div>
          <select value={category} onChange={(e) => setCategory(e.target.value)}
            style={{ width: 140, padding: "7px 10px", fontSize: 13, background: "var(--bg-overlay)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 5, outline: "none" }}>
            <option value="">그룹 (선택)</option>
            {groups.map((g) => <option key={g.id} value={g.name}>{g.name}</option>)}
          </select>
          <button type="submit" disabled={adding || !handle.trim()}
            style={{ padding: "7px 16px", fontSize: 12, fontWeight: 500, color: "white", background: "var(--green)", border: "none", borderRadius: 5, cursor: adding ? "default" : "pointer", opacity: adding || !handle.trim() ? 0.5 : 1 }}>
            {adding ? "추가 중..." : "추가"}
          </button>
          <button type="button" onClick={() => setMode("none")}
            style={{ padding: "7px 10px", fontSize: 12, color: "var(--text-tertiary)", background: "none", border: "none", cursor: "pointer" }}>
            취소
          </button>
        </form>
      )}

      {/* Bulk add */}
      {mode === "bulk" && (
        <form onSubmit={addBulk}
          style={{ padding: 14, marginBottom: 16, background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 8 }}>
          <textarea
            value={bulk} onChange={(e) => { setBulk(e.target.value); setBulkResults([]); }}
            placeholder={"핸들 또는 URL을 한 줄에 하나씩 입력\n@username\nhttps://instagram.com/username\nusername1, username2"}
            rows={5} autoFocus
            style={{ width: "100%", padding: "8px 10px", background: "var(--bg-overlay)", border: "1px solid var(--border)", borderRadius: 5, fontSize: 12, color: "var(--text-primary)", outline: "none", resize: "vertical", lineHeight: 1.7, fontFamily: "inherit" }} />
          <div style={{ display: "flex", gap: 8, marginTop: 10, alignItems: "center" }}>
            <select value={category} onChange={(e) => setCategory(e.target.value)}
              style={{ flex: 1, padding: "7px 10px", fontSize: 12, background: "var(--bg-overlay)", color: "var(--text-primary)", border: "1px solid var(--border)", borderRadius: 5, outline: "none" }}>
              <option value="">그룹 (선택, 전체 적용)</option>
              {groups.map((g) => <option key={g.id} value={g.name}>{g.name}</option>)}
            </select>
            <button type="submit" disabled={adding || !bulk.trim()}
              style={{ padding: "7px 16px", fontSize: 12, fontWeight: 500, color: "white", background: "var(--accent)", border: "none", borderRadius: 5, cursor: adding || !bulk.trim() ? "default" : "pointer", opacity: adding || !bulk.trim() ? 0.5 : 1, whiteSpace: "nowrap" }}>
              {adding ? "추가 중..." : `${bulkCount}개 추가`}
            </button>
            <button type="button" onClick={() => { setMode("none"); setBulkResults([]); }}
              style={{ padding: "7px 10px", fontSize: 12, color: "var(--text-tertiary)", background: "none", border: "none", cursor: "pointer" }}>
              취소
            </button>
          </div>
          {bulkResults.length > 0 && (
            <div style={{ marginTop: 10, display: "flex", flexDirection: "column", gap: 3 }}>
              {bulkResults.map((r) => (
                <div key={r.handle} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11 }}>
                  <span style={{ color: r.ok ? "var(--green)" : "var(--red)", fontWeight: 600 }}>{r.ok ? "+" : "x"}</span>
                  <span style={{ color: "var(--text-secondary)" }}>@{r.handle}</span>
                  {!r.ok && <span style={{ color: "var(--text-tertiary)" }}>{r.msg}</span>}
                </div>
              ))}
              <p style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 4 }}>
                {bulkResults.filter((r) => r.ok).length}개 추가 / {bulkResults.filter((r) => !r.ok).length}개 실패
              </p>
            </div>
          )}
        </form>
      )}

      {/* Channel table */}
      {loading ? (
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", paddingTop: 80 }}>
          <div className="spinner" />
        </div>
      ) : channels.length === 0 ? (
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "60px 24px", textAlign: "center", background: "var(--bg-subtle)" }}>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", fontWeight: 500, margin: 0 }}>등록된 채널이 없습니다</p>
          <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginTop: 4 }}>채널 추가 또는 대량 추가 버튼으로 채널을 등록하세요</p>
        </div>
      ) : (
        <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "var(--bg-subtle)", borderBottom: "1px solid var(--border)" }}>
                <th style={{ padding: "10px 0 10px 16px", width: 36 }}>
                  <input
                    type="checkbox"
                    checked={channels.length > 0 && selectedIds.size === channels.length}
                    ref={(el) => {
                      if (el) el.indeterminate = selectedIds.size > 0 && selectedIds.size < channels.length;
                    }}
                    onChange={toggleSelectAll}
                    style={{ cursor: "pointer", accentColor: "var(--accent)" }}
                  />
                </th>
                <th style={{ textAlign: "left", padding: "10px 16px", fontWeight: 500, color: "var(--text-tertiary)", fontSize: 12, width: "auto" }}>채널</th>
                <th style={{ textAlign: "left", padding: "10px 12px", fontWeight: 500, color: "var(--text-tertiary)", fontSize: 12, width: 120 }}>그룹</th>
                <th style={{ textAlign: "right", padding: "10px 12px", fontWeight: 500, color: "var(--text-tertiary)", fontSize: 12, width: 110 }}>마지막 수집</th>
                <th style={{ textAlign: "right", padding: "10px 16px", fontWeight: 500, color: "var(--text-tertiary)", fontSize: 12, width: 280 }}></th>
              </tr>
            </thead>
            <tbody>
              {channels.map((ch) => (
                <tr key={ch.id}
                  style={{ borderBottom: "1px solid var(--border)", transition: "background 0.12s", background: selectedIds.has(ch.id) ? "var(--accent-muted)" : "transparent" }}
                  onMouseEnter={(e) => { if (!selectedIds.has(ch.id)) e.currentTarget.style.background = "var(--bg-subtle)"; }}
                  onMouseLeave={(e) => { if (!selectedIds.has(ch.id)) e.currentTarget.style.background = "transparent"; }}>
                  <td style={{ padding: "12px 0 12px 16px" }}>
                    <input
                      type="checkbox"
                      checked={selectedIds.has(ch.id)}
                      onChange={() => toggleSelect(ch.id)}
                      style={{ cursor: "pointer", accentColor: "var(--accent)" }}
                    />
                  </td>
                  <td style={{ padding: "12px 16px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <div style={{ width: 32, height: 32, borderRadius: 6, background: "var(--accent-muted)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--accent-text)", fontSize: 13, fontWeight: 600, flexShrink: 0 }}>
                        {ch.instagram_handle.charAt(0).toUpperCase()}
                      </div>
                      <a
                        href={`https://www.instagram.com/${ch.instagram_handle}/`}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="인스타그램에서 열기"
                        style={{
                          color: "var(--text-primary)", fontWeight: 500,
                          textDecoration: "none",
                          display: "inline-flex", alignItems: "center", gap: 4,
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.color = "var(--accent-text)")}
                        onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-primary)")}
                      >
                        @{ch.instagram_handle}
                        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{ opacity: 0.6 }}>
                          <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 6H5.25A2.25 2.25 0 0 0 3 8.25v10.5A2.25 2.25 0 0 0 5.25 21h10.5A2.25 2.25 0 0 0 18 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25" />
                        </svg>
                      </a>
                    </div>
                  </td>
                  <td style={{ padding: "12px 16px", color: "var(--text-secondary)" }}>
                    <select value={ch.category || ""} onChange={(e) => changeGroup(ch.id, e.target.value)}
                      style={{ width: "100%", padding: "4px 6px", fontSize: 12, background: "var(--bg-overlay)", color: ch.category ? "var(--text-primary)" : "var(--text-tertiary)", border: "1px solid var(--border)", borderRadius: 4, outline: "none", cursor: "pointer" }}>
                      <option value="">-</option>
                      {groups.map((g) => <option key={g.id} value={g.name}>{g.name}</option>)}
                      {/* 목록에 없는 값이 이미 들어있으면 그대로 보여준다 — 자유 입력 시절 데이터 */}
                      {ch.category && !groups.some((g) => g.name === ch.category) && (
                        <option value={ch.category}>{ch.category}</option>
                      )}
                    </select>
                  </td>
                  <td style={{ padding: "12px 16px", textAlign: "right", color: "var(--text-tertiary)", fontSize: 12 }}>
                    {ch.last_scraped_at ? new Date(ch.last_scraped_at).toLocaleDateString("ko-KR") : "-"}
                  </td>
                  <td style={{ padding: "12px 16px", textAlign: "right" }}>
                    <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                      <a
                        href={`https://www.instagram.com/${ch.instagram_handle}/`}
                        target="_blank"
                        rel="noopener noreferrer"
                        title="인스타그램 계정 페이지 열기"
                        style={{
                          padding: "6px 12px", fontSize: 11, fontWeight: 500,
                          color: "var(--text-secondary)", background: "var(--bg-elevated)",
                          border: "1px solid var(--border)", borderRadius: 4,
                          cursor: "pointer", textDecoration: "none",
                          display: "inline-flex", alignItems: "center", gap: 4,
                        }}
                      >
                        방문 ↗
                      </a>
                      <button onClick={() => setTemplatesFor(ch)}
                        style={{ padding: "6px 12px", fontSize: 11, fontWeight: 500, color: "var(--text-secondary)", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 4, cursor: "pointer" }}>
                        템플릿
                      </button>
                      <button onClick={() => scrapeOne(ch.instagram_handle)} disabled={scraping.has(ch.instagram_handle)}
                        style={{ padding: "6px 12px", fontSize: 11, fontWeight: 500, color: scraping.has(ch.instagram_handle) ? "var(--text-disabled)" : "var(--accent-text)", background: "var(--accent-muted)", border: "none", borderRadius: 4, cursor: scraping.has(ch.instagram_handle) ? "default" : "pointer" }}>
                        {scraping.has(ch.instagram_handle) ? "수집 중..." : "수집"}
                      </button>
                      <button onClick={() => removeChannel(ch.id)}
                        style={{ padding: "6px 12px", fontSize: 11, fontWeight: 500, color: "var(--red)", background: "var(--red-muted)", border: "none", borderRadius: 4, cursor: "pointer" }}>
                        삭제
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {templatesFor && (
        <ChannelTemplatesModal
          channel={templatesFor}
          onClose={() => setTemplatesFor(null)}
          onChannelUpdate={(updated) => {
            setChannels((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
            setTemplatesFor(updated);
          }}
        />
      )}
    </div>
  );
}
