"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { User, Category } from "@/lib/types";

export default function SettingsPage() {
  const [apiKey, setApiKey] = useState("");
  const [saved, setSaved] = useState(false);
  const [me, setMe] = useState<User | null>(null);

  useEffect(() => {
    api.getMe().catch(() => null).then((u) => setMe(u ?? null));
  }, []);

  function handleSave() {
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  const isAdmin = me?.role === "admin";

  const sectionStyle: React.CSSProperties = {
    background: "var(--bg-elevated)",
    border: "1px solid var(--border)",
    borderRadius: 8,
    padding: "20px 24px",
  };

  const labelStyle: React.CSSProperties = {
    display: "block",
    fontSize: 11,
    fontWeight: 500,
    color: "var(--text-secondary)",
    marginBottom: 6,
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    padding: "8px 12px",
    background: "var(--bg-overlay)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    fontSize: 13,
    color: "var(--text-primary)",
    outline: "none",
  };

  return (
    <div style={{ padding: "32px 40px", maxWidth: 720, margin: "0 auto" }}>
      <div style={{ marginBottom: 28 }}>
        <h1 style={{ fontSize: 20, fontWeight: 600, color: "var(--text-primary)", letterSpacing: "-0.02em", margin: 0 }}>
          설정
        </h1>
        <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginTop: 4 }}>
          {isAdmin ? "API·채널 그룹·사용자 관리" : "API 키와 채널 그룹을 설정하세요"}
        </p>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        {/* API Settings */}
        <section style={sectionStyle}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
            <div style={{ width: 28, height: 28, borderRadius: 6, background: "var(--accent-muted)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={1.6} stroke="var(--accent-text)">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 5.25a3 3 0 0 1 3 3m3 0a6 6 0 0 1-7.029 5.912c-.563-.097-1.159.026-1.563.43L10.5 17.25H8.25v2.25H6v2.25H2.25v-2.818c0-.597.237-1.17.659-1.591l6.499-6.499c.404-.404.527-1 .43-1.563A6 6 0 1 1 21.75 8.25Z" />
              </svg>
            </div>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>API 설정</h2>
          </div>
          <div>
            <label style={labelStyle}>Google GenAI API Key</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="API 키를 입력하세요"
              style={inputStyle}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
            />
            <p style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 6 }}>AI 콘텐츠 생성에 사용됩니다</p>
          </div>
        </section>

        {/* Scheduler */}
        <section style={sectionStyle}>
          <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 12 }}>
            <div style={{ width: 28, height: 28, borderRadius: 6, background: "var(--green-muted)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={1.6} stroke="var(--green)">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
              </svg>
            </div>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>스케줄러</h2>
          </div>
          <p style={{ fontSize: 13, color: "var(--text-secondary)", lineHeight: 1.6, margin: 0 }}>
            매일 새벽 2시에 활성화된 벤치마크 채널에서 자동으로 소재를 수집합니다.
          </p>
          <div
            style={{
              marginTop: 12,
              display: "flex",
              alignItems: "center",
              gap: 8,
              background: "var(--green-muted)",
              borderRadius: 6,
              padding: "8px 12px",
            }}
          >
            <span
              style={{
                width: 6,
                height: 6,
                borderRadius: "50%",
                background: "var(--green)",
                flexShrink: 0,
                boxShadow: "0 0 0 3px rgba(76,175,130,0.2)",
              }}
            />
            <span style={{ fontSize: 12, color: "var(--green)", fontWeight: 500 }}>스케줄러 활성 상태</span>
          </div>
        </section>

        {/* Admin sections */}
        {/* 채널 그룹은 작업자도 만든다. admin 전용으로 두었더니 실제로 일하는 계정이
            전부 worker 라 만들 통로가 없었고, 그래서 그룹이 하나도 안 만들어졌다.
            사용자 관리는 admin 전용 그대로. */}
        <CategoryManager />
        {isAdmin && <UserManager currentUserId={me?.id ?? 0} />}

        <button
          onClick={handleSave}
          style={{
            width: "100%",
            padding: "10px",
            borderRadius: 6,
            fontSize: 13,
            fontWeight: 500,
            background: saved ? "var(--green)" : "var(--accent)",
            color: "white",
            cursor: "pointer",
            transition: "background 0.15s",
          }}
          onMouseEnter={(e) => { if (!saved) e.currentTarget.style.background = "var(--accent-hover)"; }}
          onMouseLeave={(e) => { e.currentTarget.style.background = saved ? "var(--green)" : "var(--accent)"; }}
        >
          {saved ? (
            <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
              <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
              </svg>
              저장됨!
            </span>
          ) : (
            "설정 저장"
          )}
        </button>
      </div>
    </div>
  );
}

/* ─── Category Manager ─── */

function CategoryManager() {
  const [categories, setCategories] = useState<Category[]>([]);
  const [newName, setNewName] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => { load(); }, []);

  async function load() {
    try {
      const data = await api.getCategories();
      setCategories(data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      await api.createCategory({ name: newName.trim(), sort_order: categories.length });
      setNewName("");
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "추가 실패");
    }
  }

  async function remove(id: number) {
    if (!confirm("이 카테고리를 삭제하시겠습니까?")) return;
    await api.deleteCategory(id);
    load();
  }

  return (
    <section
      style={{
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "20px 24px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
        <div style={{ width: 28, height: 28, borderRadius: 6, background: "var(--amber-muted)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={1.6} stroke="var(--amber)">
            <path strokeLinecap="round" strokeLinejoin="round" d="M9.568 3H5.25A2.25 2.25 0 0 0 3 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 0 0 5.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 0 0 9.568 3Z" />
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 6h.008v.008H6V6Z" />
          </svg>
        </div>
        <div>
          <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>카테고리 관리</h2>
          <p style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 1 }}>채널 분류용 카테고리를 관리합니다</p>
        </div>
      </div>

      <form onSubmit={add} style={{ display: "flex", gap: 8, marginBottom: 14 }}>
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="새 카테고리 이름"
          style={{
            flex: 1,
            padding: "7px 10px",
            background: "var(--bg-overlay)",
            border: "1px solid var(--border)",
            borderRadius: 6,
            fontSize: 13,
            color: "var(--text-primary)",
            outline: "none",
          }}
          onFocus={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
          onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
        />
        <button
          type="submit"
          disabled={!newName.trim()}
          style={{
            padding: "7px 14px",
            background: "var(--amber)",
            color: "white",
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500,
            opacity: !newName.trim() ? 0.5 : 1,
            cursor: !newName.trim() ? "not-allowed" : "pointer",
          }}
        >
          추가
        </button>
      </form>

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "16px 0" }}>
          <div className="spinner" />
        </div>
      ) : categories.length === 0 ? (
        <p style={{ fontSize: 12, color: "var(--text-tertiary)", textAlign: "center", padding: "12px 0" }}>
          등록된 카테고리가 없습니다
        </p>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
          {categories.map((cat) => (
            <div
              key={cat.id}
              className="group"
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                background: "var(--bg-overlay)",
                border: "1px solid var(--border)",
                borderRadius: 6,
                padding: "4px 10px",
              }}
            >
              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>{cat.name}</span>
              <button
                onClick={() => remove(cat.id)}
                style={{ color: "var(--text-tertiary)", lineHeight: 0 }}
                onMouseEnter={(e) => (e.currentTarget.style.color = "var(--red)")}
                onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-tertiary)")}
              >
                <svg width="12" height="12" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

/* ─── User Manager ─── */

function UserManager({ currentUserId }: { currentUserId: number }) {
  const [users, setUsers] = useState<User[]>([]);
  const [showAdd, setShowAdd] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("worker");
  const [loading, setLoading] = useState(true);

  useEffect(() => { load(); }, []);

  async function load() {
    try {
      const data = await api.getUsers();
      setUsers(data);
    } catch { /* ignore */ }
    finally { setLoading(false); }
  }

  async function add(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password.trim()) return;
    try {
      await api.createUser({ username, password, role });
      setUsername("");
      setPassword("");
      setRole("worker");
      setShowAdd(false);
      load();
    } catch (err) {
      alert(err instanceof Error ? err.message : "사용자 추가 실패");
    }
  }

  async function toggleRole(user: User) {
    const newRole = user.role === "admin" ? "worker" : "admin";
    await api.updateUserRole(user.id, newRole);
    load();
  }

  async function remove(id: number) {
    if (!confirm("이 사용자를 삭제하시겠습니까?")) return;
    await api.deleteUser(id);
    load();
  }

  const fieldStyle: React.CSSProperties = {
    padding: "7px 10px",
    background: "var(--bg-elevated)",
    border: "1px solid var(--border)",
    borderRadius: 6,
    fontSize: 13,
    color: "var(--text-primary)",
    outline: "none",
  };

  return (
    <section
      style={{
        background: "var(--bg-elevated)",
        border: "1px solid var(--border)",
        borderRadius: 8,
        padding: "20px 24px",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 28, height: 28, borderRadius: 6, background: "var(--accent-muted)", display: "flex", alignItems: "center", justifyContent: "center" }}>
            <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={1.6} stroke="var(--accent-text)">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15 19.128a9.38 9.38 0 0 0 2.625.372 9.337 9.337 0 0 0 4.121-.952 4.125 4.125 0 0 0-7.533-2.493M15 19.128v-.003c0-1.113-.285-2.16-.786-3.07M15 19.128v.106A12.318 12.318 0 0 1 8.624 21c-2.331 0-4.512-.645-6.374-1.766l-.001-.109a6.375 6.375 0 0 1 11.964-3.07M12 6.375a3.375 3.375 0 1 1-6.75 0 3.375 3.375 0 0 1 6.75 0Zm8.25 2.25a2.625 2.625 0 1 1-5.25 0 2.625 2.625 0 0 1 5.25 0Z" />
            </svg>
          </div>
          <div>
            <h2 style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>사용자 관리</h2>
            <p style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 1 }}>작업자 계정을 관리합니다</p>
          </div>
        </div>
        <button
          onClick={() => setShowAdd(!showAdd)}
          style={{
            padding: "5px 12px",
            fontSize: 12,
            fontWeight: 500,
            background: "var(--accent-muted)",
            color: "var(--accent-text)",
            borderRadius: 6,
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(94,106,210,0.22)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "var(--accent-muted)")}
        >
          + 사용자 추가
        </button>
      </div>

      {showAdd && (
        <form
          onSubmit={add}
          style={{
            marginBottom: 14,
            padding: 14,
            background: "var(--bg-subtle)",
            borderRadius: 6,
            border: "1px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div style={{ display: "flex", gap: 8 }}>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="아이디"
              style={{ ...fieldStyle, flex: 1 }}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
            />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="비밀번호"
              style={{ ...fieldStyle, width: 140 }}
              onFocus={(e) => (e.currentTarget.style.borderColor = "var(--accent)")}
              onBlur={(e) => (e.currentTarget.style.borderColor = "var(--border)")}
            />
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              style={fieldStyle}
            >
              <option value="worker">작업자</option>
              <option value="admin">관리자</option>
            </select>
            <button
              type="submit"
              disabled={!username.trim() || !password.trim()}
              style={{
                padding: "7px 16px",
                background: "var(--accent)",
                color: "white",
                borderRadius: 6,
                fontSize: 12,
                fontWeight: 500,
                opacity: !username.trim() || !password.trim() ? 0.5 : 1,
                cursor: !username.trim() || !password.trim() ? "not-allowed" : "pointer",
              }}
            >
              추가
            </button>
          </div>
        </form>
      )}

      {loading ? (
        <div style={{ display: "flex", justifyContent: "center", padding: "16px 0" }}>
          <div className="spinner" />
        </div>
      ) : (
        <div>
          {users.map((u, i) => (
            <div
              key={u.id}
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "10px 0",
                borderBottom: i < users.length - 1 ? "1px solid var(--border)" : "none",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div
                  style={{
                    width: 30,
                    height: 30,
                    borderRadius: 6,
                    background: u.role === "admin" ? "var(--accent)" : "var(--bg-overlay)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    color: u.role === "admin" ? "white" : "var(--text-secondary)",
                    fontSize: 12,
                    fontWeight: 700,
                  }}
                >
                  {u.username.charAt(0).toUpperCase()}
                </div>
                <div>
                  <p style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)", margin: 0 }}>{u.username}</p>
                  <span style={{ fontSize: 11, color: u.role === "admin" ? "var(--accent-text)" : "var(--text-tertiary)" }}>
                    {u.role === "admin" ? "관리자" : "작업자"}
                  </span>
                </div>
              </div>
              {u.id !== currentUserId && (
                <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                  <button
                    onClick={() => toggleRole(u)}
                    style={{
                      fontSize: 11,
                      padding: "3px 8px",
                      borderRadius: 4,
                      fontWeight: 500,
                      color: "var(--accent-text)",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "var(--accent-muted)")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    {u.role === "admin" ? "작업자로" : "관리자로"}
                  </button>
                  <button
                    onClick={() => remove(u.id)}
                    style={{ padding: 4, borderRadius: 4, color: "var(--text-tertiary)" }}
                    onMouseEnter={(e) => (e.currentTarget.style.color = "var(--red)")}
                    onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-tertiary)")}
                  >
                    <svg width="13" height="13" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="m14.74 9-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" />
                    </svg>
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
