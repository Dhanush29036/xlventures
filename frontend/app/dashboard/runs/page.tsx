"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getRuns } from "@/lib/api";
import type { AgentRun } from "@/lib/types";

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "running",       label: "Running" },
  { value: "completed",     label: "Completed" },
  { value: "pending",       label: "Pending" },
  { value: "failed",        label: "Failed" },
  { value: "awaiting_hitl", label: "Awaiting Review" },
];

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge badge-${status}`}>
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
  return new Date(dateStr).toLocaleDateString();
}

export default function RunsPage() {
  const [runs, setRuns] = useState<AgentRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState<string>("");

  useEffect(() => {
    setLoading(true);
    getRuns({ status: statusFilter || undefined, page_size: 50 })
      .then((r) => setRuns(r.items))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [statusFilter]);

  const counts = STATUS_FILTERS.slice(1).reduce((acc, f) => {
    acc[f.value] = runs.filter((r) => r.status === f.value).length;
    return acc;
  }, {} as Record<string, number>);

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      {/* Header */}
      <div className="animate-fade-in" style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <div>
            <h1 style={{ fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.04em", marginBottom: "0.25rem" }}>
              Discovery Runs
            </h1>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
              All pipeline executions — track progress and explore results
            </p>
          </div>
          <Link href="/dashboard/runs/new" className="btn-primary">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            New Run
          </Link>
        </div>
      </div>

      {/* Status filter pills */}
      <div className="animate-fade-in delay-100" style={{ display: "flex", gap: "0.5rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
        {STATUS_FILTERS.map((f) => {
          const isActive = statusFilter === f.value;
          const count = f.value ? counts[f.value] : runs.length;
          return (
            <button
              key={f.value}
              onClick={() => setStatusFilter(f.value)}
              style={{
                padding: "0.375rem 0.875rem",
                borderRadius: 8,
                border: "1px solid",
                borderColor: isActive ? "rgba(139,92,246,0.5)" : "var(--border-subtle)",
                background: isActive ? "rgba(139,92,246,0.12)" : "var(--bg-elevated)",
                color: isActive ? "#c4b5fd" : "var(--text-muted)",
                cursor: "pointer",
                fontSize: "0.8rem",
                fontWeight: 500,
                transition: "all 0.15s ease",
                display: "inline-flex",
                alignItems: "center",
                gap: "0.4rem",
                fontFamily: "inherit",
              }}
              onMouseEnter={(e) => {
                if (!isActive) {
                  (e.currentTarget as HTMLElement).style.borderColor = "var(--border-default)";
                  (e.currentTarget as HTMLElement).style.color = "var(--text-secondary)";
                }
              }}
              onMouseLeave={(e) => {
                if (!isActive) {
                  (e.currentTarget as HTMLElement).style.borderColor = "var(--border-subtle)";
                  (e.currentTarget as HTMLElement).style.color = "var(--text-muted)";
                }
              }}
            >
              {f.label}
              {!loading && (
                <span style={{
                  background: isActive ? "rgba(139,92,246,0.2)" : "rgba(255,255,255,0.06)",
                  borderRadius: 4,
                  padding: "0 0.3rem",
                  fontSize: "0.68rem",
                  fontWeight: 700,
                  color: isActive ? "#c4b5fd" : "var(--text-dim)",
                }}>
                  {count ?? 0}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Table */}
      <div className="glass-card animate-fade-in-up delay-200" style={{ overflow: "hidden" }}>
        {loading ? (
          <div style={{ padding: "2rem" }}>
            {[...Array(6)].map((_, i) => (
              <div key={i} style={{
                display: "flex",
                gap: "1.5rem",
                alignItems: "center",
                padding: "0.875rem 1.125rem",
                borderBottom: i < 5 ? "1px solid var(--border-subtle)" : undefined,
              }}>
                <div className="skeleton" style={{ width: 90, height: 20, borderRadius: 5 }} />
                <div className="skeleton" style={{ width: 80, height: 22, borderRadius: 6 }} />
                <div className="skeleton" style={{ width: 120, height: 16, borderRadius: 5 }} />
                <div className="skeleton" style={{ width: 60, height: 16, marginLeft: "auto", borderRadius: 5 }} />
                <div className="skeleton" style={{ width: 50, height: 16, borderRadius: 5 }} />
                <div className="skeleton" style={{ width: 55, height: 28, borderRadius: 7 }} />
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
            }}>
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#8b5cf6" strokeWidth="1.5">
                <circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>
              </svg>
            </div>
            <h3 style={{ fontWeight: 600, fontSize: "1rem", marginBottom: "0.375rem" }}>
              {statusFilter ? `No ${statusFilter} runs` : "No runs found"}
            </h3>
            <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "1.25rem" }}>
              {statusFilter ? "Try a different filter or create a new run." : "Create your first discovery run to get started."}
            </p>
            {!statusFilter && (
              <Link href="/dashboard/runs/new" className="btn-primary">Start First Run</Link>
            )}
          </div>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                {["Run ID", "Status", "Target", "Max", "Started", "Duration", "Actions"].map((h) => (
                  <th key={h} style={{
                    padding: "0.75rem 1.125rem",
                    textAlign: "left",
                    fontSize: "0.68rem",
                    color: "var(--text-muted)",
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.07em",
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const duration = run.completed_at
                  ? Math.round((new Date(run.completed_at).getTime() - new Date(run.created_at).getTime()) / 1000)
                  : null;
                const durationStr = duration != null
                  ? duration < 60 ? `${duration}s` : `${Math.floor(duration / 60)}m ${duration % 60}s`
                  : run.status === "running" ? "running…" : "—";

                return (
                  <tr key={run.id} className="table-row">
                    <td style={{ padding: "0.875rem 1.125rem" }}>
                      <code style={{
                        fontSize: "0.78rem",
                        color: "#a78bfa",
                        background: "rgba(167,139,250,0.08)",
                        padding: "0.15rem 0.4rem",
                        borderRadius: 5,
                        border: "1px solid rgba(167,139,250,0.12)",
                      }}>
                        {run.id.slice(0, 8)}
                      </code>
                    </td>
                    <td style={{ padding: "0.875rem 1.125rem" }}>
                      <StatusBadge status={run.status} />
                    </td>
                    <td style={{ padding: "0.875rem 1.125rem", fontSize: "0.85rem", color: "var(--text-secondary)", maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {(run.plan_json as Record<string, string>)?.company_domain ?? (
                        <span style={{ color: "var(--text-dim)", fontStyle: "italic" }}>demo</span>
                      )}
                    </td>
                    <td style={{ padding: "0.875rem 1.125rem", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                      {(run.plan_json as Record<string, number>)?.max_companies ?? "—"}
                    </td>
                    <td style={{ padding: "0.875rem 1.125rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>
                      {timeAgo(run.created_at)}
                    </td>
                    <td style={{ padding: "0.875rem 1.125rem", fontSize: "0.8rem", color: "var(--text-muted)", fontFamily: "monospace" }}>
                      {durationStr}
                    </td>
                    <td style={{ padding: "0.875rem 1.125rem" }}>
                      <div style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
                        <Link
                          href={`/dashboard/runs/${run.id}`}
                          className="btn-secondary"
                          style={{ padding: "0.3rem 0.75rem", fontSize: "0.78rem" }}
                        >
                          View
                        </Link>
                        {run.status === "completed" && (
                          <Link
                            href={`/dashboard/runs/${run.id}/results`}
                            className="btn-success"
                            style={{ padding: "0.3rem 0.75rem", fontSize: "0.78rem" }}
                          >
                            Results
                          </Link>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
