"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getICPConfigs, deleteICPConfig } from "@/lib/api";
import type { ICPConfig } from "@/lib/types";

export default function ICPListPage() {
  const [icps, setIcps] = useState<ICPConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    getICPConfigs().then(setIcps).catch(console.error).finally(() => setLoading(false));
  }, []);

  async function handleDelete(id: string) {
    if (!confirm("Deactivate this ICP config? This cannot be undone.")) return;
    setDeletingId(id);
    try {
      await deleteICPConfig(id);
      setIcps((prev) => prev.filter((i) => i.id !== id));
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      {/* Header */}
      <div className="animate-fade-in" style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1 style={{ fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.04em", marginBottom: "0.25rem" }}>
              ICP Configurations
            </h1>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
              Define your Ideal Customer Profiles to target the right companies
            </p>
          </div>
          <Link href="/dashboard/icp/new" className="btn-primary">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New ICP
          </Link>
        </div>
      </div>

      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {[...Array(4)].map((_, i) => (
            <div key={i} className="skeleton" style={{ height: 100, borderRadius: 14 }} />
          ))}
        </div>
      ) : icps.length === 0 ? (
        <div className="glass-card animate-scale-in" style={{ padding: "4rem 2rem", textAlign: "center" }}>
          <div style={{
            width: 56, height: 56,
            borderRadius: 16,
            background: "rgba(139,92,246,0.1)",
            border: "1px solid rgba(139,92,246,0.2)",
            display: "flex", alignItems: "center", justifyContent: "center",
            margin: "0 auto 1rem",
            animation: "float 3s ease-in-out infinite",
          }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="1.5">
              <circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
            </svg>
          </div>
          <h3 style={{ fontWeight: 600, fontSize: "1rem", marginBottom: "0.375rem" }}>No ICP configs yet</h3>
          <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "1.25rem", maxWidth: 340, margin: "0 auto 1.25rem" }}>
            Create your first Ideal Customer Profile to start discovering and scoring prospects
          </p>
          <Link href="/dashboard/icp/new" className="btn-primary">
            Create First ICP
          </Link>
        </div>
      ) : (
        <div className="animate-fade-in-up" style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {icps.map((icp, i) => (
            <div
              key={icp.id}
              className="glass-card animate-fade-in"
              style={{
                padding: "1.25rem 1.5rem",
                transition: "all 0.2s ease",
                animationDelay: `${i * 70}ms`,
              }}
              onMouseEnter={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor = "var(--border-default)";
                (e.currentTarget as HTMLElement).style.transform = "translateY(-1px)";
                (e.currentTarget as HTMLElement).style.boxShadow = "var(--shadow-md)";
              }}
              onMouseLeave={(e) => {
                (e.currentTarget as HTMLElement).style.borderColor = "var(--border-subtle)";
                (e.currentTarget as HTMLElement).style.transform = "";
                (e.currentTarget as HTMLElement).style.boxShadow = "";
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: "1rem" }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.625rem", marginBottom: "0.625rem" }}>
                    <div style={{
                      width: 36, height: 36, borderRadius: 9,
                      background: "rgba(139,92,246,0.1)",
                      border: "1px solid rgba(139,92,246,0.2)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      color: "#8b5cf6",
                      flexShrink: 0,
                    }}>
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <circle cx="12" cy="12" r="3"/><path d="M19.07 4.93a10 10 0 0 1 0 14.14M4.93 4.93a10 10 0 0 0 0 14.14"/>
                      </svg>
                    </div>
                    <div>
                      <div style={{ fontWeight: 700, fontSize: "0.9375rem", color: "var(--text-primary)" }}>
                        {icp.name}
                      </div>
                      <span className={`badge ${icp.is_active ? "badge-completed" : "badge-cancelled"}`} style={{ marginTop: 2 }}>
                        {icp.is_active ? "Active" : "Inactive"}
                      </span>
                    </div>
                  </div>

                  {/* Rule chips */}
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem", paddingLeft: "0.25rem" }}>
                    {Object.entries(icp.rules_json ?? {}).map(([k, v]) => (
                      <span key={k} className="chip" style={{ cursor: "default" }}>
                        <span style={{ color: "var(--text-dim)", fontSize: "0.7rem" }}>{k}:</span>
                        <span>{Array.isArray(v) ? (v as string[]).slice(0, 2).join(", ") : String(v)}</span>
                      </span>
                    ))}
                  </div>
                </div>

                <div style={{ display: "flex", gap: "0.5rem", flexShrink: 0 }}>
                  <Link
                    href={`/dashboard/icp/${icp.id}`}
                    className="btn-secondary"
                    style={{ padding: "0.375rem 0.875rem", fontSize: "0.8rem" }}
                  >
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/>
                    </svg>
                    Edit
                  </Link>
                  <button
                    onClick={() => handleDelete(icp.id)}
                    className="btn-danger"
                    disabled={deletingId === icp.id}
                    style={{ padding: "0.375rem 0.875rem", fontSize: "0.8rem" }}
                  >
                    {deletingId === icp.id ? (
                      <div className="spinner spinner-sm" />
                    ) : (
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <polyline points="3,6 5,6 21,6"/><path d="M19,6v14a2,2,0,0,1-2,2H7a2,2,0,0,1-2-2V6m3,0V4a2,2,0,0,1,2-2h4a2,2,0,0,1,2,2v2"/>
                      </svg>
                    )}
                    Delete
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
