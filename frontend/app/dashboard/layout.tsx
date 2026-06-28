"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuthStore, useUIStore } from "@/lib/store";
import { useEffect, useState } from "react";

const navItems = [
  { href: "/dashboard", label: "Overview", icon: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/>
    </svg>
  )},
  { href: "/dashboard/runs", label: "Runs", icon: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="5,3 19,12 5,21"/><line x1="19" y1="3" x2="19" y2="21"/>
    </svg>
  )},
  { href: "/dashboard/studio", label: "Agent Studio", icon: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/>
    </svg>
  ), highlight: true},
  { href: "/dashboard/studio/pipeline", label: "Pipeline Builder", icon: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="5" cy="12" r="2"/><circle cx="19" cy="5" r="2"/><circle cx="19" cy="19" r="2"/>
      <line x1="7" y1="11.5" x2="17" y2="6.5"/><line x1="7" y1="12.5" x2="17" y2="17.5"/>
    </svg>
  ), indent: true},
  { href: "/dashboard/hitl", label: "Review Queue", icon: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 11V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v0"/><path d="M14 10V4a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v2"/><path d="M10 10.5V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>
    </svg>
  ), badge: true},
  { href: "/dashboard/icp", label: "ICP Configs", icon: (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
    </svg>
  )},
];

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { email, clearAuth, isAuthenticated } = useAuthStore();
  const { hitlCount } = useUIStore();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    if (mounted && !isAuthenticated()) {
      router.replace("/login");
    }
  }, [isAuthenticated, router, mounted]);

  const showContent = mounted && isAuthenticated();
  const userInitial = email ? email[0].toUpperCase() : "?";

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--bg-base)" }}>
      {/* Sidebar */}
      <aside style={{
        width: 230,
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border-subtle)",
        display: "flex",
        flexDirection: "column",
        padding: "1.25rem 0.875rem",
        flexShrink: 0,
        position: "sticky",
        top: 0,
        height: "100vh",
        zIndex: 10,
      }}>
        {/* Logo */}
        <div style={{ 
          display: "flex", 
          alignItems: "center", 
          gap: "0.625rem", 
          marginBottom: "1.75rem", 
          paddingLeft: "0.5rem",
          paddingRight: "0.5rem",
        }}>
          <div style={{
            width: 34, height: 34, borderRadius: 10,
            background: "linear-gradient(135deg, #7c3aed 0%, #3b82f6 100%)",
            display: "flex", alignItems: "center", justifyContent: "center",
            flexShrink: 0,
            boxShadow: "0 2px 12px rgba(124,58,237,0.4)",
          }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="white">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
            </svg>
          </div>
          <div>
            <div style={{ fontWeight: 800, fontSize: "0.875rem", letterSpacing: "-0.02em", color: "var(--text-primary)" }}>
              XL Ventures
            </div>
            <div style={{ fontSize: "0.68rem", color: "var(--text-muted)", letterSpacing: "0.02em", marginTop: 1 }}>
              Prospect Intelligence
            </div>
          </div>
        </div>

        {/* Nav section label */}
        <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "var(--text-dim)", letterSpacing: "0.1em", textTransform: "uppercase", paddingLeft: "0.875rem", marginBottom: "0.5rem" }}>
          Navigation
        </div>

        {/* Nav */}
        <nav style={{ display: "flex", flexDirection: "column", gap: "0.15rem", flex: 1 }}>
          {navItems.map((item) => {
            const isActive = item.href === "/dashboard"
              ? pathname === "/dashboard"
              : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`sidebar-link ${isActive ? "active" : ""}`}
                style={{
                  ...(item.indent ? { paddingLeft: "2rem", marginLeft: "0.5rem" } : {}),
                  ...(item.highlight && !isActive ? {
                    background: "linear-gradient(135deg, rgba(139,92,246,0.12) 0%, rgba(59,130,246,0.08) 100%)",
                    border: "1px solid rgba(139,92,246,0.2)",
                    borderRadius: 8,
                  } : {}),
                }}
              >
                <span style={{
                  opacity: isActive ? 1 : (item.highlight ? 0.85 : 0.6),
                  transition: "opacity 0.15s",
                  display: "flex",
                  alignItems: "center",
                  color: item.highlight && !isActive ? "#a78bfa" : "inherit",
                }}>
                  {item.icon}
                </span>
                <span style={{
                  flex: 1,
                  color: item.highlight && !isActive ? "#a78bfa" : "inherit",
                  fontWeight: item.highlight ? 600 : undefined,
                }}>{item.label}</span>
                {item.highlight && !isActive && (
                  <span style={{
                    background: "linear-gradient(135deg, #7c3aed, #3b82f6)",
                    color: "white",
                    borderRadius: "5px",
                    padding: "0.1rem 0.4rem",
                    fontSize: "0.62rem",
                    fontWeight: 700,
                    letterSpacing: "0.05em",
                  }}>
                    NEW
                  </span>
                )}
                {item.badge && showContent && hitlCount > 0 && (
                  <span style={{
                    background: "var(--brand-purple)",
                    color: "white",
                    borderRadius: "6px",
                    padding: "0.1rem 0.4rem",
                    fontSize: "0.68rem",
                    fontWeight: 700,
                    minWidth: 18,
                    textAlign: "center",
                    boxShadow: "0 2px 6px rgba(139,92,246,0.4)",
                  }}>
                    {hitlCount}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Divider */}
        <div style={{ height: 1, background: "var(--border-subtle)", margin: "0.75rem 0" }} />

        {/* User info */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: "0.625rem",
          padding: "0.625rem 0.5rem",
          borderRadius: 10,
          cursor: "default",
        }}>
          {/* Avatar */}
          <div style={{
            width: 30, height: 30,
            borderRadius: 8,
            background: "linear-gradient(135deg, rgba(139,92,246,0.3), rgba(59,130,246,0.3))",
            border: "1px solid rgba(139,92,246,0.3)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "0.75rem",
            fontWeight: 700,
            color: "#c4b5fd",
            flexShrink: 0,
          }}>
            {showContent ? userInitial : "?"}
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: "0.75rem", color: "var(--text-secondary)", fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {showContent ? email : ""}
            </div>
            <button
              onClick={() => { clearAuth(); router.push("/login"); }}
              style={{
                background: "none",
                border: "none",
                color: "var(--text-muted)",
                fontSize: "0.7rem",
                cursor: "pointer",
                padding: 0,
                transition: "color 0.15s",
                fontFamily: "inherit",
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "var(--red)")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
            >
              Sign out
            </button>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main style={{ 
        flex: 1, 
        padding: "2.5rem 2.75rem", 
        overflowY: "auto", 
        minHeight: "100vh",
        background: "var(--bg-base)",
        maxWidth: "calc(100vw - 230px)",
      }}>
        {showContent ? children : (
          <div style={{ display: "flex", justifyContent: "center", alignItems: "center", height: "60vh" }}>
            <div className="spinner" style={{ width: 32, height: 32 }} />
          </div>
        )}
      </main>
    </div>
  );
}
