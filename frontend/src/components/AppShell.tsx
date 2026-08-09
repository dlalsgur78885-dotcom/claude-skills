"use client";

import { usePathname } from "next/navigation";
import { AuthGuard } from "./AuthGuard";
import { Sidebar } from "./Sidebar";

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isLoginPage = pathname === "/login";

  return (
    <AuthGuard>
      {isLoginPage ? (
        children
      ) : (
        <div className="flex min-h-full">
          <Sidebar />
          <main className="flex-1" style={{ marginLeft: 220 }}>{children}</main>
        </div>
      )}
    </AuthGuard>
  );
}
