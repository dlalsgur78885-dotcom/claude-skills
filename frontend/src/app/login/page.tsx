"use client";

import { useState } from "react";
import { api } from "@/lib/api";

export default function LoginPage() {
  const [isSignup, setIsSignup] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (!username.trim() || !password.trim()) {
      setError("아이디와 비밀번호를 입력하세요");
      return;
    }

    if (isSignup && password !== confirmPassword) {
      setError("비밀번호가 일치하지 않습니다");
      return;
    }

    setLoading(true);
    try {
      if (isSignup) {
        await api.signup(username, password);
      }
      await api.login(username, password);
      // Restore the page the user was on when their session expired
      const params = typeof window !== "undefined" ? new URLSearchParams(window.location.search) : null;
      const next = params?.get("next");
      window.location.href = next && next.startsWith("/") ? next : "/";
    } catch (err) {
      setError(err instanceof Error ? err.message : "요청에 실패했습니다");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center px-4"
      style={{ background: "var(--bg-app)" }}
    >
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-8">
          <div
            className="flex items-center justify-center mx-auto mb-4"
            style={{
              width: 40,
              height: 40,
              background: "var(--accent)",
              borderRadius: 10,
            }}
          >
            <svg width="20" height="20" fill="none" viewBox="0 0 24 24" strokeWidth={2.2} stroke="white">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6A2.25 2.25 0 0 1 6 3.75h2.25A2.25 2.25 0 0 1 10.5 6v2.25a2.25 2.25 0 0 1-2.25 2.25H6a2.25 2.25 0 0 1-2.25-2.25V6ZM13.5 15.75a2.25 2.25 0 0 1 2.25-2.25H18a2.25 2.25 0 0 1 2.25 2.25V18A2.25 2.25 0 0 1 18 20.25h-2.25a2.25 2.25 0 0 1-2.25-2.25v-2.25Z" />
            </svg>
          </div>
          <h1 style={{ fontSize: 16, fontWeight: 600, color: "var(--text-primary)", letterSpacing: "-0.01em" }}>
            Carousel Studio
          </h1>
          <p style={{ fontSize: 13, color: "var(--text-tertiary)", marginTop: 4 }}>
            Instagram Carousel Automation
          </p>
        </div>

        {/* Form Card */}
        <div
          style={{
            background: "var(--bg-elevated)",
            border: "1px solid var(--border)",
            borderRadius: 10,
            padding: "24px",
          }}
        >
          <h2 style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)", marginBottom: 4 }}>
            {isSignup ? "회원가입" : "로그인"}
          </h2>
          <p style={{ fontSize: 12, color: "var(--text-tertiary)", marginBottom: 20 }}>
            {isSignup ? "새 계정을 만들어 시작하세요" : "계정에 로그인하세요"}
          </p>

          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div>
              <label style={{ display: "block", fontSize: 11, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 6 }}>
                아이디
              </label>
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="아이디를 입력하세요"
                autoComplete="username"
                style={{
                  width: "100%",
                  padding: "8px 12px",
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
            </div>

            <div>
              <label style={{ display: "block", fontSize: 11, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 6 }}>
                비밀번호
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="비밀번호"
                autoComplete={isSignup ? "new-password" : "current-password"}
                style={{
                  width: "100%",
                  padding: "8px 12px",
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
            </div>

            {isSignup && (
              <div>
                <label style={{ display: "block", fontSize: 11, fontWeight: 500, color: "var(--text-secondary)", marginBottom: 6 }}>
                  비밀번호 확인
                </label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="비밀번호 재입력"
                  autoComplete="new-password"
                  style={{
                    width: "100%",
                    padding: "8px 12px",
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
              </div>
            )}

            {error && (
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 8,
                  fontSize: 12,
                  color: "var(--red)",
                  background: "var(--red-muted)",
                  borderRadius: 6,
                  padding: "8px 12px",
                }}
              >
                <svg width="14" height="14" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor" style={{ flexShrink: 0 }}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 1 1-18 0 9 9 0 0 1 18 0Zm-9 3.75h.008v.008H12v-.008Z" />
                </svg>
                {error}
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              style={{
                width: "100%",
                padding: "9px",
                background: "var(--accent)",
                color: "white",
                borderRadius: 6,
                fontSize: 13,
                fontWeight: 500,
                opacity: loading ? 0.7 : 1,
                cursor: loading ? "not-allowed" : "pointer",
                marginTop: 4,
              }}
              onMouseEnter={(e) => { if (!loading) e.currentTarget.style.background = "var(--accent-hover)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "var(--accent)"; }}
            >
              {loading ? (
                <div className="spinner mx-auto" style={{ width: 16, height: 16 }} />
              ) : isSignup ? (
                "계정 만들기"
              ) : (
                "로그인"
              )}
            </button>
          </form>
        </div>

        {/* Toggle */}
        <p style={{ textAlign: "center", fontSize: 12, color: "var(--text-tertiary)", marginTop: 16 }}>
          {isSignup ? "이미 계정이 있으신가요?" : "계정이 없으신가요?"}{" "}
          <button
            onClick={() => {
              setIsSignup(!isSignup);
              setError("");
            }}
            style={{ color: "var(--accent-text)", fontWeight: 500 }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "var(--accent)")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--accent-text)")}
          >
            {isSignup ? "로그인" : "회원가입"}
          </button>
        </p>
      </div>
    </div>
  );
}
