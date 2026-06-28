"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getRuns, getHITLItems } from "@/lib/api";
import { useUIStore, useAuthStore } from "@/lib/store";
import type { AgentRun, HITLItem } from "@/lib/types";

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    completed: "#22c55e",
    running: "#3b82f6",
    failed: "#ef4444",
    pending: "#f59e0b",
    awaiting_hitl: "#8b5cf6",
    cancelled: "#64748b",
  };
  return (
    <span style={{
      display: "inline-block",
      width: 7,
      height: 7,
      borderRadius: "50%",
      background: colors[status] ?? "#64748b",
      boxShadow: status === "running" ? `0 0 8px ${colors.running}` : undefined,
      animation: status === "running" ? "pulse 1.5s ease-in-out infinite" : undefined,
      flexShrink: 0,
    }} />
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge badge-${status}`} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
      <StatusDot status={status} />
      {status.replace(/_/g, " ")}
    </span>
  );
}

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const min = Math.floor(diff / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${min}m ago`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr}h ago`;
  return `${Math.floor(hr / 24)}d ago`;
}

export default function DashboardPage() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [hitlItems, setHitlItems] = useState<HITLItem[]>([]);
  const [loading, setLoading] = useState(true);
  const { setHitlCount } = useUIStore();
  const { email } = useAuthStore();

  useEffect(() => {
    Promise.all([getRuns({ page_size: 10 }), getHITLItems()])
      .then(([runsRes, hitl]) => {
        setRuns(runsRes.items);
        setHitlItems(hitl);
        setHitlCount(hitl.filter((h) => h.status === "pending").length);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [setHitlCount]);

  const completed = runs.filter((r) => r.status === "completed").length;
  const running = runs.filter((r) => r.status === "running").length;
  const pending = hitlItems.filter((h) => h.status === "pending").length;
  const failed = runs.filter((r) => r.status === "failed").length;

  const firstName = email?.split("@")[0]?.split(".")[0];
  const greeting = firstName ? `${firstName.charAt(0).toUpperCase() + firstName.slice(1)}` : "there";

  const stats = [
    {
      label: "Total Runs",
      value: runs.length,
      change: null,
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polygon points="5,3 19,12 5,21"/>
        </svg>
      ),
      color: "#8b5cf6",
    },
    {
      label: "Completed",
      value: completed,
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="20,6 9,17 4,12"/>
        </svg>
      ),
      color: "#22c55e",
    },
    {
      label: "Active Now",
      value: running,
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/>
        </svg>
      ),
      color: "#3b82f6",
    },
    {
      label: "Needs Review",
      value: pending,
      icon: (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M18 11V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v0"/><path d="M14 10V4a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v2"/><path d="M10 10.5V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>
        </svg>
      ),
      color: "#f59e0b",
    },
  ];

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      {/* Header */}
      <div className="animate-fade-in" style={{ marginBottom: "2.5rem" }}>
        <p style={{ fontSize: "0.8125rem", color: "var(--text-muted)", marginBottom: "0.25rem", letterSpacing: "0.02em" }}>
          Good day, {greeting} 👋
        </p>
        <h1 style={{ fontSize: "2rem", fontWeight: 800, letterSpacing: "-0.04em", lineHeight: 1.1 }}>
          Prospect Intelligence
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginTop: "0.375rem" }}>
          Real-time B2B discovery pipeline across your defined ICPs
        </p>
      </div>

      {/* Stats row */}
      <div className="animate-fade-in-up delay-100" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: "1rem", marginBottom: "2rem" }}>
        {stats.map((stat, i) => (
          <div
            key={stat.label}
            className="stat-card"
            style={{ animationDelay: `${i * 80}ms` }}
          >
            <div style={{ 
              display: "flex", 
              justifyContent: "space-between", 
              alignItems: "flex-start",
              marginBottom: "0.5rem",
            }}>
              <div style={{
                width: 34, height: 34, borderRadius: 9,
                background: `${stat.color}18`,
                border: `1px solid ${stat.color}30`,
                display: "flex", alignItems: "center", justifyContent: "center",
                color: stat.color,
              }}>
                {stat.icon}
              </div>
            </div>
            <div className="stat-value" style={{
              background: `linear-gradient(135deg, ${stat.color}, ${stat.color}aa)`,
              WebkitBackgroundClip: "text",
              WebkitTextFillColor: "transparent",
              backgroundClip: "text",
            }}>
              {loading ? (
                <div className="skeleton" style={{ width: 40, height: 32 }} />
              ) : stat.value}
            </div>
            <div className="stat-label">{stat.label}</div>
          </div>
        ))}
      </div>

      {/* HITL banner */}
      {!loading && pending > 0 && (
        <div className="animate-fade-in glass-card" style={{
          marginBottom: "1.5rem",
          padding: "1rem 1.25rem",
          border: "1px solid rgba(245,158,11,0.25)",
          background: "rgba(245,158,11,0.06)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div style={{
              width: 36, height: 36, borderRadius: 9,
              background: "rgba(245,158,11,0.15)",
              border: "1px solid rgba(245,158,11,0.3)",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "#f59e0b",
            }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 11V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v0"/><path d="M14 10V4a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v2"/><path d="M10 10.5V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>
              </svg>
            </div>
            <div>
              <div style={{ fontWeight: 600, fontSize: "0.9rem", color: "var(--text-primary)" }}>
                {pending} item{pending > 1 ? "s" : ""} waiting for your review
              </div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: 2 }}>
                Pipeline execution is paused until approval
              </div>
            </div>
          </div>
          <Link href="/dashboard/hitl" className="btn-primary" style={{ flexShrink: 0 }}>
            Review Now
          </Link>
        </div>
      )}

      {/* Runs section */}
      <div className="animate-fade-in-up delay-200">
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
          <div>
            <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, letterSpacing: "-0.02em" }}>Recent Runs</h2>
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: 2 }}>Latest pipeline executions</p>
          </div>
          <Link href="/dashboard/runs/new" className="btn-primary">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New Run
          </Link>
        </div>

        <div className="glass-card" style={{ overflow: "hidden" }}>
          {loading ? (
            <div style={{ padding: "2rem" }}>
              {[...Array(4)].map((_, i) => (
                <div key={i} style={{ display: "flex", gap: "1rem", alignItems: "center", padding: "0.75rem 1rem", borderBottom: i < 3 ? "1px solid var(--border-subtle)" : undefined }}>
                  <div className="skeleton" style={{ width: 80, height: 16 }} />
                  <div className="skeleton" style={{ width: 70, height: 20 }} />
                  <div className="skeleton" style={{ width: 40, height: 16, marginLeft: "auto" }} />
                  <div className="skeleton" style={{ width: 50, height: 16 }} />
                </div>
              ))}
            </div>
          ) : runs.length === 0 ? (
            <div style={{ padding: "4rem 2rem", textAlign: "center" }}>
              <div style={{ 
                width: 56, height: 56, borderRadius: 16,
                background: "rgba(139,92,246,0.1)",
                border: "1px solid rgba(139,92,246,0.2)",
                display: "flex", alignItems: "center", justifyContent: "center",
                margin: "0 auto 1rem",
                animation: "float 3s ease-in-out infinite",
              }}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="1.5">
                  <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
                </svg>
              </div>
              <h3 style={{ fontWeight: 600, fontSize: "1rem", marginBottom: "0.375rem" }}>No runs yet</h3>
              <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "1.25rem" }}>
                Launch your first discovery pipeline to start finding prospects
              </p>
              <Link href="/dashboard/runs/new" className="btn-primary">
                Start First Run
              </Link>
            </div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  {["Run", "Status", "Domain", "Created", ""].map((h) => (
                    <th key={h} style={{
                      padding: "0.75rem 1.125rem",
                      textAlign: "left",
                      fontSize: "0.7rem",
                      color: "var(--text-muted)",
                      fontWeight: 600,
                      textTransform: "uppercase",
                      letterSpacing: "0.07em",
                    }}>
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.id} className="table-row">
                    <td style={{ padding: "0.875rem 1.125rem" }}>
                      <code style={{ 
                        fontSize: "0.78rem", 
                        color: "#a78bfa",
                        background: "rgba(167,139,250,0.1)",
                        padding: "0.15rem 0.4rem",
                        borderRadius: 5,
                        border: "1px solid rgba(167,139,250,0.15)",
                      }}>
                        {run.id.slice(0, 8)}
                      </code>
                    </td>
                    <td style={{ padding: "0.875rem 1.125rem" }}>
                      <StatusBadge status={run.status} />
                    </td>
                    <td style={{ padding: "0.875rem 1.125rem", color: "var(--text-secondary)", fontSize: "0.85rem" }}>
                      {(run.plan_json as Record<string, string>)?.company_domain ?? (
                        <span style={{ color: "var(--text-dim)", fontStyle: "italic", fontSize: "0.8rem" }}>demo companies</span>
                      )}
                    </td>
                    <td style={{ padding: "0.875rem 1.125rem", color: "var(--text-muted)", fontSize: "0.8rem" }}>
                      {timeAgo(run.created_at)}
                    </td>
                    <td style={{ padding: "0.875rem 1.125rem", textAlign: "right" }}>
                      <Link
                        href={`/dashboard/runs/${run.id}`}
                        style={{
                          color: "var(--text-secondary)",
                          fontSize: "0.8rem",
                          textDecoration: "none",
                          fontWeight: 500,
                          display: "inline-flex",
                          alignItems: "center",
                          gap: 4,
                          padding: "0.25rem 0.625rem",
                          borderRadius: 6,
                          border: "1px solid var(--border-subtle)",
                          background: "var(--bg-elevated)",
                          transition: "all 0.15s",
                        }}
                        onMouseEnter={(e) => {
                          (e.currentTarget as HTMLElement).style.borderColor = "rgba(139,92,246,0.4)";
                          (e.currentTarget as HTMLElement).style.color = "#c4b5fd";
                        }}
                        onMouseLeave={(e) => {
                          (e.currentTarget as HTMLElement).style.borderColor = "var(--border-subtle)";
                          (e.currentTarget as HTMLElement).style.color = "var(--text-secondary)";
                        }}
                      >
                        View
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                          <polyline points="9,18 15,12 9,6"/>
                        </svg>
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        {!loading && runs.length > 0 && (
          <div style={{ textAlign: "center", marginTop: "0.875rem" }}>
            <Link href="/dashboard/runs" style={{ 
              color: "var(--text-muted)", 
              fontSize: "0.8rem", 
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: 4,
              transition: "color 0.15s",
            }}
              onMouseEnter={(e) => (e.currentTarget.style.color = "#c4b5fd")}
              onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
            >
              View all runs
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12,5 19,12 12,19"/>
              </svg>
            </Link>
          </div>
        )}
      </div>
    </div>
  );
}
