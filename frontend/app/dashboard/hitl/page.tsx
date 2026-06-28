"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getHITLItems } from "@/lib/api";
import { useUIStore } from "@/lib/store";
import type { HITLItem } from "@/lib/types";

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return new Date(dateStr).toLocaleDateString();
}

export default function HITLPage() {
  const [items, setItems] = useState<HITLItem[]>([]);
  const [loading, setLoading] = useState(true);
  const { setHitlCount } = useUIStore();

  useEffect(() => {
    getHITLItems().then((data) => {
      setItems(data);
      setHitlCount(data.filter((h) => h.status === "pending").length);
    }).catch(console.error).finally(() => setLoading(false));
  }, [setHitlCount]);

  const pending = items.filter((i) => i.status === "pending");
  const reviewed = items.filter((i) => i.status !== "pending");

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      {/* Header */}
      <div className="animate-fade-in" style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1 style={{ fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.04em", marginBottom: "0.25rem" }}>
              Review Queue
            </h1>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
              Pipeline decisions that need your judgment before continuing
            </p>
          </div>
          {pending.length > 0 && (
            <div style={{
              padding: "0.375rem 0.875rem",
              background: "rgba(245,158,11,0.1)",
              border: "1px solid rgba(245,158,11,0.25)",
              borderRadius: 8,
              display: "flex",
              alignItems: "center",
              gap: "0.4rem",
            }}>
              <div style={{ width: 7, height: 7, borderRadius: "50%", background: "#f59e0b", animation: "pulse 1.5s infinite" }} />
              <span style={{ fontSize: "0.8rem", color: "#f59e0b", fontWeight: 600 }}>
                {pending.length} pending
              </span>
            </div>
          )}
        </div>
      </div>

      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          {[...Array(3)].map((_, i) => (
            <div key={i} className="skeleton" style={{ height: 88, borderRadius: 14 }} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <div className="glass-card animate-scale-in" style={{ padding: "4rem 2rem", textAlign: "center" }}>
          <div style={{
            width: 56, height: 56,
            borderRadius: 16,
            background: "rgba(34,197,94,0.1)",
            border: "1px solid rgba(34,197,94,0.2)",
            display: "flex", alignItems: "center", justifyContent: "center",
            margin: "0 auto 1rem",
          }}>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#22c55e" strokeWidth="2">
              <polyline points="20,6 9,17 4,12"/>
            </svg>
          </div>
          <h3 style={{ fontWeight: 600, fontSize: "1rem", color: "var(--text-primary)", marginBottom: "0.375rem" }}>
            All clear
          </h3>
          <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>
            No items waiting for review right now
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          {/* Pending items */}
          {pending.length > 0 && (
            <div className="animate-fade-in-up">
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: "0.625rem", paddingLeft: "0.25rem" }}>
                Awaiting Review — {pending.length}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
                {pending.map((item, i) => (
                  <Link key={item.id} href={`/dashboard/hitl/${item.id}`} style={{ textDecoration: "none" }}>
                    <div
                      className="glass-card animate-fade-in"
                      style={{
                        padding: "1.125rem 1.25rem",
                        border: "1px solid rgba(245,158,11,0.25)",
                        background: "rgba(245,158,11,0.04)",
                        cursor: "pointer",
                        transition: "all 0.2s ease",
                        animationDelay: `${i * 80}ms`,
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLElement).style.borderColor = "rgba(245,158,11,0.5)";
                        (e.currentTarget as HTMLElement).style.background = "rgba(245,158,11,0.08)";
                        (e.currentTarget as HTMLElement).style.transform = "translateY(-1px)";
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLElement).style.borderColor = "rgba(245,158,11,0.25)";
                        (e.currentTarget as HTMLElement).style.background = "rgba(245,158,11,0.04)";
                        (e.currentTarget as HTMLElement).style.transform = "";
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "1rem" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.875rem" }}>
                          <div style={{
                            width: 38, height: 38, borderRadius: 10,
                            background: "rgba(245,158,11,0.12)",
                            border: "1px solid rgba(245,158,11,0.25)",
                            display: "flex", alignItems: "center", justifyContent: "center",
                            color: "#f59e0b",
                            flexShrink: 0,
                          }}>
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <path d="M18 11V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v0"/><path d="M14 10V4a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v2"/><path d="M10 10.5V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>
                            </svg>
                          </div>
                          <div>
                            <div style={{ fontWeight: 600, color: "var(--text-primary)", marginBottom: 3 }}>
                              {(item.payload_json?.name as string) || (item.payload_json?.domain as string) || "Review Required"}
                            </div>
                            <div style={{ display: "flex", gap: "0.75rem", fontSize: "0.78rem", color: "var(--text-muted)" }}>
                              <span>{item.agent_name.replace(/_/g, " ")}</span>
                              <span>·</span>
                              <code style={{ color: "#a78bfa", fontSize: "0.75rem" }}>{item.run_id.slice(0, 8)}</code>
                            </div>
                          </div>
                        </div>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexShrink: 0 }}>
                          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            {item.created_at ? timeAgo(item.created_at) : ""}
                          </span>
                          <div style={{
                            padding: "0.3rem 0.75rem",
                            background: "rgba(245,158,11,0.12)",
                            border: "1px solid rgba(245,158,11,0.25)",
                            borderRadius: 7,
                            fontSize: "0.78rem",
                            color: "#f59e0b",
                            fontWeight: 600,
                            display: "flex",
                            alignItems: "center",
                            gap: 4,
                          }}>
                            Review
                            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <polyline points="9,18 15,12 9,6"/>
                            </svg>
                          </div>
                        </div>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}

          {/* Reviewed items */}
          {reviewed.length > 0 && (
            <div className="animate-fade-in-up delay-200">
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: "0.625rem", paddingLeft: "0.25rem" }}>
                Reviewed — {reviewed.length}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                {reviewed.map((item) => (
                  <Link key={item.id} href={`/dashboard/hitl/${item.id}`} style={{ textDecoration: "none" }}>
                    <div
                      className="glass-card"
                      style={{
                        padding: "0.875rem 1.25rem",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                      }}
                      onMouseEnter={(e) => {
                        (e.currentTarget as HTMLElement).style.borderColor = "var(--border-default)";
                      }}
                      onMouseLeave={(e) => {
                        (e.currentTarget as HTMLElement).style.borderColor = "var(--border-subtle)";
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                          <div style={{
                            width: 30, height: 30, borderRadius: 8,
                            background: item.status === "approved" ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
                            border: `1px solid ${item.status === "approved" ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`,
                            display: "flex", alignItems: "center", justifyContent: "center",
                            color: item.status === "approved" ? "var(--green)" : "var(--red)",
                            flexShrink: 0,
                          }}>
                            {item.status === "approved" ? (
                              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                                <polyline points="20,6 9,17 4,12"/>
                              </svg>
                            ) : (
                              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                              </svg>
                            )}
                          </div>
                          <div>
                            <div style={{ fontSize: "0.875rem", fontWeight: 500, color: "var(--text-secondary)" }}>
                              {(item.payload_json?.name as string) || (item.payload_json?.domain as string) || "Review"}
                            </div>
                            <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                              {item.agent_name.replace(/_/g, " ")}
                            </div>
                          </div>
                        </div>
                        <span style={{
                          fontSize: "0.78rem",
                          fontWeight: 600,
                          color: item.status === "approved" ? "var(--green)" : "var(--red)",
                        }}>
                          {item.status === "approved" ? "Approved" : "Rejected"}
                        </span>
                      </div>
                    </div>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
