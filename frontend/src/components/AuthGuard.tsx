"use client";

import { useEffect, useState, useCallback } from "react";
import { usePathname, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useAppStore } from "@/lib/store";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const setUser = useAppStore((s) => s.setUser);
  const [status, setStatus] = useState<"loading" | "authed" | "unauthed">("loading");

  const check = useCallback(async () => {
    setStatus("loading");
    try {
      const user = await api.getMe();
      setUser(user);
      setStatus("authed");
    } catch {
      setUser(null);
      setStatus("unauthed");
    }
  }, [setUser]);

  useEffect(() => {
    check();
  }, [pathname, check]);

  const isPublic = pathname === "/login";

  // Redirect logic
  useEffect(() => {
    if (status === "loading") return;
    if (status === "authed" && isPublic) {
      router.replace("/");
    } else if (status === "unauthed" && !isPublic) {
      router.replace("/login");
    }
  }, [status, isPublic, router]);

  if (status === "loading") {
    return (
      <div style={{ minHeight: "100vh", display: "flex", alignItems: "center", justifyContent: "center", background: "var(--bg-app)" }}>
        <div className="spinner" />
      </div>
    );
  }

  // Show login page if unauthed, show app if authed
  if (status === "unauthed" && !isPublic) return null;
  if (status === "authed" && isPublic) return null;

  return <>{children}</>;
}
