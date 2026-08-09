"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAppStore } from "@/lib/store";
import type { User } from "@/lib/types";

type Tab = "users" | "events" | "settings";

export default function AdminPage() {
  const router = useRouter();
  const me = useAppStore((s) => s.user);
  const [tab, setTab] = useState<Tab>("users");

  // Block non-admins. (Backend also enforces, this is just UX.)
  useEffect(() => {
    if (me && me.role !== "admin") {
      router.replace("/");
    }
  }, [me, router]);

  if (!me) return null;
  if (me.role !== "admin") {
    return (
      <div style={{ padding: 24, color: "#e85b5b" }}>
        admin 권한이 필요합니다. 메인으로 돌아갑니다…
      </div>
    );
  }

  return (
    <div style={{ padding: "32px 40px", maxWidth: 960, margin: "0 auto" }}>
      <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>
        관리자
      </h1>
      <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginBottom: 22 }}>
        직원 계정과 API 키를 한곳에서 관리합니다.
      </p>

      <div style={{ display: "flex", gap: 6, marginBottom: 20, borderBottom: "1px solid var(--border)" }}>
        {([
          { id: "users" as const, label: "직원 관리" },
          { id: "events" as const, label: "로그인 기록" },
          { id: "settings" as const, label: "API 키" },
        ]).map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            style={{
              padding: "8px 14px",
              fontSize: 13,
              fontWeight: 500,
              color: tab === t.id ? "var(--accent)" : "var(--text-secondary)",
              background: "transparent",
              border: "none",
              borderBottom: tab === t.id ? "2px solid var(--accent)" : "2px solid transparent",
              cursor: "pointer",
              marginBottom: -1,
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "users" && <UsersTab currentUserId={me.id} />}
      {tab === "events" && <EventsTab />}
      {tab === "settings" && <SettingsTab />}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────

function UsersTab({ currentUserId }: { currentUserId: number }) {
  const [users, setUsers] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<"worker" | "admin">("worker");
  const [creating, setCreating] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const list = await api.getUsers();
      setUsers(list);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }

  async function create(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    setCreating(true);
    setErr("");
    try {
      await api.createUser({ username: username.trim(), password, role });
      setUsername("");
      setPassword("");
      setRole("worker");
      load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "계정 생성 실패");
    } finally {
      setCreating(false);
    }
  }

  async function changeRole(uid: number, newRole: string) {
    try {
      await api.updateUserRole(uid, newRole);
      load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "역할 변경 실패");
    }
  }

  async function remove(uid: number, name: string) {
    if (!confirm(`'${name}' 계정을 삭제하시겠습니까?`)) return;
    try {
      await api.deleteUser(uid);
      load();
    } catch (e) {
      alert(e instanceof Error ? e.message : "삭제 실패");
    }
  }

  return (
    <div>
      <div
        style={{
          padding: 14,
          marginBottom: 18,
          background: "var(--bg-elevated)",
          border: "1px solid var(--border)",
          borderRadius: 8,
        }}
      >
        <h3 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0, marginBottom: 10 }}>
          새 직원 추가
        </h3>
        <form onSubmit={create} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <input
            type="text"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="아이디"
            required
            style={inputStyle}
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="비밀번호"
            required
            style={inputStyle}
          />
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as "worker" | "admin")}
            style={{ ...inputStyle, cursor: "pointer" }}
          >
            <option value="worker">worker</option>
            <option value="admin">admin</option>
          </select>
          <button
            type="submit"
            disabled={creating}
            style={{
              padding: "7px 16px",
              fontSize: 12,
              fontWeight: 500,
              color: "white",
              background: "var(--accent)",
              border: "none",
              borderRadius: 5,
              cursor: creating ? "default" : "pointer",
              opacity: creating ? 0.6 : 1,
            }}
          >
            {creating ? "추가 중…" : "추가"}
          </button>
          {err && <span style={{ fontSize: 11, color: "#e85b5b", alignSelf: "center" }}>{err}</span>}
        </form>
      </div>

      <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "var(--bg-subtle)", borderBottom: "1px solid var(--border)" }}>
              <th style={th}>아이디</th>
              <th style={{ ...th, width: 120 }}>역할</th>
              <th style={{ ...th, width: 150 }}>가입일</th>
              <th style={{ ...th, width: 110, textAlign: "right" }}></th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={4} style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)" }}>로딩…</td></tr>
            ) : users.length === 0 ? (
              <tr><td colSpan={4} style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)" }}>없음</td></tr>
            ) : users.map((u) => (
              <tr key={u.id} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={td}>
                  <span style={{ color: "var(--text-primary)", fontWeight: 500 }}>{u.username}</span>
                  {u.id === currentUserId && (
                    <span style={{ fontSize: 10, padding: "1px 6px", background: "var(--bg-overlay)", borderRadius: 3, marginLeft: 6, color: "var(--text-tertiary)" }}>나</span>
                  )}
                </td>
                <td style={td}>
                  <select
                    value={u.role}
                    disabled={u.id === currentUserId}
                    onChange={(e) => changeRole(u.id, e.target.value)}
                    style={{
                      padding: "3px 8px",
                      fontSize: 12,
                      background: "var(--bg-overlay)",
                      color: "var(--text-primary)",
                      border: "1px solid var(--border)",
                      borderRadius: 4,
                    }}
                  >
                    <option value="worker">worker</option>
                    <option value="admin">admin</option>
                  </select>
                </td>
                <td style={{ ...td, color: "var(--text-tertiary)", fontSize: 12 }}>
                  {new Date(u.created_at).toLocaleDateString("ko-KR")}
                </td>
                <td style={{ ...td, textAlign: "right" }}>
                  {u.id !== currentUserId && (
                    <button
                      onClick={() => remove(u.id, u.username)}
                      style={{
                        padding: "3px 10px",
                        fontSize: 11,
                        color: "var(--red)",
                        background: "var(--red-muted)",
                        border: "none",
                        borderRadius: 4,
                        cursor: "pointer",
                      }}
                    >
                      삭제
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────

type LoginEventRow = {
  id: number;
  user_id: number;
  username: string;
  ip: string;
  user_agent: string;
  occurred_at: string;
};

function EventsTab() {
  const [events, setEvents] = useState<LoginEventRow[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [userId, setUserId] = useState<number | null>(null);
  // null = 전체 기간. 한 번 누른 버튼을 다시 누르면 해제해도 좋겠지만,
  // "토글 해제 = 전체" 동작은 클릭 동선이 헷갈리니 별도 "전체" 버튼만 둠.
  const [days, setDays] = useState<number | null>(7);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.getUsers().then(setUsers).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, days]);

  async function load() {
    setLoading(true);
    try {
      const res = await api.listLoginEvents({
        user_id: userId ?? undefined,
        days: days ?? undefined,
        limit: 200,
      });
      setEvents(res.events);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }

  const ranges: { label: string; v: number | null }[] = [
    { label: "1일", v: 1 },
    { label: "7일", v: 7 },
    { label: "30일", v: 30 },
    { label: "전체", v: null },
  ];

  return (
    <div>
      <div style={{ display: "flex", gap: 10, marginBottom: 14, alignItems: "center", flexWrap: "wrap" }}>
        <select
          value={userId ?? ""}
          onChange={(e) => setUserId(e.target.value ? Number(e.target.value) : null)}
          style={{ ...inputStyle, cursor: "pointer", minWidth: 140 }}
        >
          <option value="">전체 직원</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
        </select>
        <div style={{ display: "flex", gap: 4 }}>
          {ranges.map((o) => {
            const active = days === o.v;
            return (
              <button
                key={String(o.v)}
                onClick={() => setDays(o.v)}
                style={{
                  padding: "5px 12px",
                  fontSize: 12,
                  borderRadius: 5,
                  cursor: "pointer",
                  background: active ? "var(--accent)" : "var(--bg-overlay)",
                  color: active ? "white" : "var(--text-secondary)",
                  border: `1px solid ${active ? "var(--accent)" : "var(--border)"}`,
                }}
              >
                {o.label}
              </button>
            );
          })}
        </div>
        <button
          onClick={load}
          style={{
            padding: "5px 12px",
            fontSize: 12,
            marginLeft: "auto",
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            color: "var(--text-secondary)",
            borderRadius: 5,
            cursor: "pointer",
          }}
        >
          새로고침
        </button>
      </div>

      <div style={{ border: "1px solid var(--border)", borderRadius: 8, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
          <thead>
            <tr style={{ background: "var(--bg-subtle)", borderBottom: "1px solid var(--border)" }}>
              <th style={{ ...th, width: 180 }}>시간</th>
              <th style={{ ...th, width: 140 }}>아이디</th>
              <th style={{ ...th, width: 150 }}>IP</th>
              <th style={th}>브라우저</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={4} style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)" }}>로딩…</td></tr>
            ) : events.length === 0 ? (
              <tr><td colSpan={4} style={{ padding: 24, textAlign: "center", color: "var(--text-tertiary)" }}>기록 없음</td></tr>
            ) : events.map((e) => (
              <tr key={e.id} style={{ borderBottom: "1px solid var(--border)" }}>
                <td style={{ ...td, fontSize: 12, color: "var(--text-tertiary)" }}>
                  {new Date(e.occurred_at).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "medium" })}
                </td>
                <td style={td}><span style={{ color: "var(--text-primary)", fontWeight: 500 }}>{e.username}</span></td>
                <td style={{ ...td, fontFamily: "monospace", fontSize: 12, color: "var(--text-primary)" }}>{e.ip || "—"}</td>
                <td style={{ ...td, fontSize: 11, color: "var(--text-tertiary)" }} title={e.user_agent}>
                  {shortenUserAgent(e.user_agent)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// Crude OS+browser detect for the table — hovering the cell still shows the
// raw user-agent string (`title` attr), so this is purely a readability aid.
function shortenUserAgent(ua: string): string {
  if (!ua) return "—";
  const browser =
    /Edg\//.test(ua) ? "Edge" :
    /OPR\//.test(ua) ? "Opera" :
    /Chrome\//.test(ua) ? "Chrome" :
    /Firefox\//.test(ua) ? "Firefox" :
    /Safari\//.test(ua) ? "Safari" :
    "기타";
  const os =
    /Windows/.test(ua) ? "Windows" :
    /Mac OS/.test(ua) ? "macOS" :
    /Android/.test(ua) ? "Android" :
    /iPhone|iPad/.test(ua) ? "iOS" :
    /Linux/.test(ua) ? "Linux" :
    "";
  return os ? `${browser} · ${os}` : browser;
}

// ─────────────────────────────────────────────────────────────────

function SettingsTab() {
  const [loading, setLoading] = useState(true);
  const [keys, setKeys] = useState<string[]>([]);
  const [meta, setMeta] = useState<Record<string, { value: string; source: string; preview: string }>>({});
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    load();
  }, []);

  async function load() {
    try {
      const data = await api.getSettings();
      setKeys(data.editable_keys);
      setMeta(data.settings);
      setDrafts({});
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "로드 실패");
    } finally {
      setLoading(false);
    }
  }

  async function save() {
    const changed = Object.fromEntries(Object.entries(drafts).filter(([k, v]) => meta[k]?.value !== v));
    if (Object.keys(changed).length === 0) {
      setMsg("변경된 값이 없습니다");
      return;
    }
    setSaving(true);
    setMsg("");
    try {
      const res = await api.updateSettings(changed);
      setMeta(res.settings);
      setDrafts({});
      setMsg("저장됨");
      setTimeout(() => setMsg(""), 3000);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "저장 실패");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <p style={{ color: "var(--text-tertiary)" }}>로딩…</p>;

  return (
    <div>
      <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 16, lineHeight: 1.6 }}>
        여기서 입력한 키가 우선 적용됩니다 (서버 .env보다 위). 비우면 .env 폴백.
        모든 직원이 이 키로 호출하니까 비용 관리는 admin 책임.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {keys.map((k) => {
          const m = meta[k] || { value: "", source: "missing", preview: "" };
          const current = drafts[k] !== undefined ? drafts[k] : m.value;
          const changed = drafts[k] !== undefined && drafts[k] !== m.value;
          return (
            <div
              key={k}
              style={{
                padding: 12,
                background: "var(--bg-elevated)",
                border: `1px solid ${changed ? "var(--accent)" : "var(--border)"}`,
                borderRadius: 6,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 6 }}>
                <label style={{ fontSize: 12, fontWeight: 600, color: "var(--text-primary)", fontFamily: "monospace" }}>
                  {k}
                </label>
                <span
                  style={{
                    fontSize: 10,
                    padding: "1px 6px",
                    borderRadius: 3,
                    background:
                      m.source === "db" ? "rgba(0,200,100,0.15)" :
                      m.source === "env" ? "rgba(120,140,255,0.15)" :
                      "rgba(232,91,91,0.15)",
                    color:
                      m.source === "db" ? "rgb(80,200,150)" :
                      m.source === "env" ? "rgb(140,160,255)" :
                      "rgb(232,91,91)",
                  }}
                >
                  {m.source === "db" ? "DB (override)" : m.source === "env" ? ".env (fallback)" : "미설정"}
                </span>
              </div>
              <input
                type="text"
                value={current}
                onChange={(e) => setDrafts((p) => ({ ...p, [k]: e.target.value }))}
                placeholder={m.preview || "값 입력"}
                style={{ ...inputStyle, width: "100%", fontFamily: "monospace", fontSize: 12 }}
              />
            </div>
          );
        })}
      </div>
      <div style={{ marginTop: 14, display: "flex", gap: 8, alignItems: "center" }}>
        <button
          onClick={save}
          disabled={saving || Object.keys(drafts).length === 0}
          style={{
            padding: "8px 18px",
            fontSize: 13,
            fontWeight: 500,
            color: "white",
            background: "var(--accent)",
            border: "none",
            borderRadius: 5,
            cursor: saving ? "default" : "pointer",
            opacity: saving || Object.keys(drafts).length === 0 ? 0.5 : 1,
          }}
        >
          {saving ? "저장 중…" : "변경사항 저장"}
        </button>
        <button
          onClick={load}
          disabled={saving}
          style={{
            padding: "8px 14px",
            fontSize: 12,
            color: "var(--text-secondary)",
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: 5,
            cursor: "pointer",
          }}
        >
          되돌리기
        </button>
        {msg && <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{msg}</span>}
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: "7px 10px",
  fontSize: 12,
  background: "var(--bg-overlay)",
  color: "var(--text-primary)",
  border: "1px solid var(--border)",
  borderRadius: 5,
  outline: "none",
};

const th: React.CSSProperties = {
  padding: "10px 16px",
  fontSize: 11,
  fontWeight: 500,
  color: "var(--text-tertiary)",
  textAlign: "left",
};

const td: React.CSSProperties = {
  padding: "10px 16px",
  color: "var(--text-secondary)",
};
