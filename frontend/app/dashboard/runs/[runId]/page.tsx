"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { getRun } from "@/lib/api";
import { useSSE } from "@/lib/useSSE";
import type { AgentRun, AgentEvent, AgentStep } from "@/lib/types";

const AGENT_ORDER = [
  { name: "trigger_monitor",   label: "Trigger Monitor",   desc: "Detect market signals & buying intent" },
  { name: "icp_scorer",        label: "ICP Scorer",         desc: "Score against ideal customer profile" },
  { name: "contact_enrichment",label: "Contact Enrichment", desc: "Find & enrich decision-maker data" },
  { name: "persona_finder",    label: "Persona Finder",     desc: "Classify contacts by persona type" },
  { name: "validation",        label: "Validation",         desc: "Quality check & human-in-the-loop gate" },
  { name: "summary",           label: "Summary",            desc: "Generate outreach recommendation" },
];

function buildSteps(events: AgentEvent[]): AgentStep[] {
  const steps: AgentStep[] = AGENT_ORDER.map((a) => ({ name: a.name, status: "pending" as const }));
  for (const evt of events) {
    if (evt.event === "agent_started" && evt.agent) {
      const s = steps.find((s) => s.name === evt.agent);
      if (s) { s.status = "running"; s.startedAt = evt.timestamp; }
    }
    if (evt.event === "agent_completed" && evt.agent) {
      const s = steps.find((s) => s.name === evt.agent);
      if (s) { s.status = "completed"; s.completedAt = evt.timestamp; s.summary = evt.result_summary as Record<string, unknown>; }
    }
    if (evt.event === "run_failed") {
      const running = steps.find((s) => s.status === "running");
      if (running) { running.status = "failed"; }
    }
  }
  return steps;
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

const AGENT_ICONS: Record<string, React.ReactNode> = {
  trigger_monitor: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polygon points="11,5 2,17 22,17"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>,
  icp_scorer: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/></svg>,
  contact_enrichment: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>,
  persona_finder: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>,
  validation: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="9,11 12,14 22,4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>,
  summary: <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10,9 9,9 8,9"/></svg>,
};

export default function RunDetailPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const [run, setRun] = useState<AgentRun | null>(null);
  const { events, isConnected } = useSSE(runId);

  useEffect(() => {
    getRun(runId).then(setRun).catch(console.error);
    const poll = setInterval(() => {
      getRun(runId).then(setRun).catch(console.error);
    }, 5000);
    return () => clearInterval(poll);
  }, [runId]);

  const steps = buildSteps(events);
  const hitlEvent = events.find((e) => e.event === "hitl_required");
  const completedEvent = events.find((e) => e.event === "run_completed");
  const failedEvent = events.find((e) => e.event === "run_failed");

  const completedCount = steps.filter((s) => s.status === "completed").length;
  const progress = Math.round((completedCount / AGENT_ORDER.length) * 100);
  const domain = (run?.plan_json as Record<string, string>)?.company_domain;

  const runStatus = run?.status ?? "pending";

  const statusColors: Record<string, string> = {
    completed: "var(--green)",
    running: "#3b82f6",
    failed: "var(--red)",
    pending: "var(--amber)",
    awaiting_hitl: "var(--brand-purple)",
  };

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      {/* Breadcrumb & Header */}
      <div className="animate-fade-in" style={{ marginBottom: "2rem" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>
          <Link href="/dashboard/runs" style={{ color: "var(--text-muted)", textDecoration: "none", display: "inline-flex", alignItems: "center", gap: 4, transition: "color 0.15s" }}
            onMouseEnter={(e) => (e.currentTarget.style.color = "#c4b5fd")}
            onMouseLeave={(e) => (e.currentTarget.style.color = "var(--text-muted)")}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12,19 5,12 12,5"/>
            </svg>
            Runs
          </Link>
          <span>/</span>
          <span>{runId.slice(0, 8)}</span>
        </div>

        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
              <h1 style={{ fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.04em" }}>
                {domain ? (
                  <span>{domain}</span>
                ) : (
                  <span className="gradient-text">Pipeline Run</span>
                )}
              </h1>
              {run && (
                <span className={`badge badge-${run.status}`}>
                  {run.status.replace(/_/g, " ")}
                </span>
              )}
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "0.875rem", marginTop: "0.375rem" }}>
              <code style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "monospace" }}>
                {runId}
              </code>
              {run && (
                <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                  Started {timeAgo(run.created_at)}
                </span>
              )}
            </div>
          </div>

          <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
            {isConnected && (
              <div style={{ display: "flex", alignItems: "center", gap: 6, padding: "0.375rem 0.75rem", borderRadius: 8, background: "rgba(34,197,94,0.08)", border: "1px solid rgba(34,197,94,0.2)" }}>
                <div className="status-dot live" />
                <span style={{ fontSize: "0.78rem", color: "var(--green)", fontWeight: 500 }}>Live</span>
              </div>
            )}
            {completedEvent && (
              <Link href={`/dashboard/runs/${runId}/results`} className="btn-success">
                View Results
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12,5 19,12 12,19"/>
                </svg>
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Status banners */}
      {hitlEvent && (
        <div className="glass-card animate-scale-in" style={{
          padding: "1rem 1.25rem",
          marginBottom: "1.5rem",
          border: "1px solid rgba(139,92,246,0.4)",
          background: "rgba(139,92,246,0.06)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "1rem",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
            <div style={{ width: 36, height: 36, borderRadius: 9, background: "rgba(139,92,246,0.15)", border: "1px solid rgba(139,92,246,0.3)", display: "flex", alignItems: "center", justifyContent: "center", color: "#c4b5fd", animation: "glow-pulse 2s ease-in-out infinite" }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 11V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v0"/><path d="M14 10V4a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v2"/><path d="M10 10.5V6a2 2 0 0 0-2-2v0a2 2 0 0 0-2 2v8"/><path d="M18 8a2 2 0 1 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/>
              </svg>
            </div>
            <div>
              <div style={{ fontWeight: 600, color: "#c4b5fd" }}>Human approval required</div>
              <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: 2 }}>Pipeline is paused — review to continue execution</div>
            </div>
          </div>
          <Link href={`/dashboard/hitl/${hitlEvent.hitl_id}`} className="btn-primary">Review Now</Link>
        </div>
      )}

      {completedEvent && (
        <div className="glass-card animate-scale-in" style={{
          padding: "1rem 1.25rem",
          marginBottom: "1.5rem",
          border: "1px solid rgba(34,197,94,0.3)",
          background: "rgba(34,197,94,0.06)",
          display: "flex",
          alignItems: "center",
          gap: "0.875rem",
        }}>
          <div style={{ width: 36, height: 36, borderRadius: 9, background: "rgba(34,197,94,0.15)", border: "1px solid rgba(34,197,94,0.25)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--green)" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <polyline points="20,6 9,17 4,12"/>
            </svg>
          </div>
          <div>
            <div style={{ fontWeight: 600, color: "var(--green)" }}>Run completed successfully</div>
            <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: 2 }}>All {AGENT_ORDER.length} agents finished — results are ready</div>
          </div>
        </div>
      )}

      {failedEvent && (
        <div className="glass-card animate-scale-in" style={{
          padding: "1rem 1.25rem",
          marginBottom: "1.5rem",
          border: "1px solid rgba(239,68,68,0.3)",
          background: "rgba(239,68,68,0.06)",
          display: "flex",
          alignItems: "center",
          gap: "0.875rem",
        }}>
          <div style={{ width: 36, height: 36, borderRadius: 9, background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.25)", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--red)" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
            </svg>
          </div>
          <div>
            <div style={{ fontWeight: 600, color: "var(--red)" }}>Run failed</div>
            <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: 2 }}>
              {(failedEvent as Record<string, string>)?.error ?? "An error occurred during execution"}
            </div>
          </div>
        </div>
      )}

      {/* Main grid */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 300px", gap: "1.5rem" }}>
        {/* Agent pipeline */}
        <div className="glass-card animate-fade-in-up delay-100" style={{ padding: "1.5rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <h2 style={{ fontSize: "0.9375rem", fontWeight: 700, letterSpacing: "-0.02em" }}>Agent Pipeline</h2>
            <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
              {completedCount} / {AGENT_ORDER.length} complete
            </span>
          </div>

          {/* Progress bar */}
          <div className="confidence-bar" style={{ marginBottom: "1.5rem" }}>
            <div className="confidence-fill" style={{ width: `${progress}%` }} />
          </div>

          <div style={{ display: "flex", flexDirection: "column" }}>
            {steps.map((step, i) => {
              const meta = AGENT_ORDER.find((a) => a.name === step.name)!;
              const isLast = i === steps.length - 1;
              const stepColors: Record<string, string> = {
                running: "#3b82f6",
                completed: "var(--green)",
                failed: "var(--red)",
                pending: "var(--text-dim)",
              };
              const textColor = stepColors[step.status];

              return (
                <div key={step.name} style={{ display: "flex", gap: "1rem", position: "relative", paddingBottom: isLast ? 0 : "1.5rem" }}>
                  {/* Timeline connector */}
                  {!isLast && (
                    <div style={{
                      position: "absolute",
                      left: 5,
                      top: 18,
                      bottom: 0,
                      width: 1,
                      background: step.status === "completed"
                        ? "linear-gradient(to bottom, rgba(34,197,94,0.3), rgba(34,197,94,0.08))"
                        : "linear-gradient(to bottom, var(--border-subtle), transparent)",
                    }} />
                  )}

                  <div className={`agent-step-dot ${step.status}`} />

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                        <span style={{
                          display: "inline-flex",
                          alignItems: "center",
                          justifyContent: "center",
                          width: 24, height: 24, borderRadius: 6,
                          background: step.status === "pending" ? "rgba(255,255,255,0.04)" : `${textColor}18`,
                          color: step.status === "pending" ? "var(--text-dim)" : textColor,
                          border: `1px solid ${step.status === "pending" ? "var(--border-subtle)" : `${textColor}30`}`,
                          transition: "all 0.3s",
                        }}>
                          {AGENT_ICONS[step.name]}
                        </span>
                        <span style={{
                          fontWeight: step.status === "pending" ? 400 : 600,
                          fontSize: "0.875rem",
                          color: step.status === "pending" ? "var(--text-muted)" : textColor,
                          transition: "color 0.3s",
                        }}>
                          {meta.label}
                        </span>
                      </div>
                      <span style={{
                        fontSize: "0.68rem",
                        color: step.status === "pending" ? "var(--text-dim)" : textColor,
                        fontWeight: 600,
                        textTransform: "uppercase",
                        letterSpacing: "0.05em",
                      }}>
                        {step.status === "running" ? "•••" : step.status}
                      </span>
                    </div>

                    <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.2rem" }}>
                      {meta.desc}
                    </div>

                    {/* Summary data */}
                    {step.summary && step.status === "completed" && (
                      <div style={{
                        marginTop: "0.5rem",
                        padding: "0.5rem 0.75rem",
                        background: "rgba(34,197,94,0.04)",
                        border: "1px solid rgba(34,197,94,0.12)",
                        borderRadius: 8,
                        display: "flex",
                        flexWrap: "wrap",
                        gap: "0.75rem",
                      }}>
                        {Object.entries(step.summary as Record<string, unknown>).slice(0, 3).map(([k, v]) => (
                          <span key={k} style={{ fontSize: "0.75rem" }}>
                            <span style={{ color: "var(--text-muted)" }}>{k.replace(/_/g, " ")}:</span>{" "}
                            <span style={{ color: "var(--text-primary)", fontWeight: 600 }}>{String(v)}</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Right panel */}
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {/* Run info */}
          <div className="glass-card animate-slide-right" style={{ padding: "1.125rem" }}>
            <h3 style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: "0.875rem" }}>
              Run Info
            </h3>
            <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
              {[
                { label: "Status",  value: <span className={`badge badge-${runStatus}`}>{runStatus.replace(/_/g, " ")}</span> },
                { label: "Domain",  value: domain ?? <span style={{ color: "var(--text-dim)", fontStyle: "italic" }}>demo</span> },
                { label: "Events",  value: <code style={{ color: "#a78bfa", fontFamily: "monospace", fontSize: "0.85rem" }}>{events.length}</code> },
                { label: "Started", value: run ? timeAgo(run.created_at) : "—" },
              ].map(({ label, value }) => (
                <div key={label} style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>{label}</span>
                  <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)", fontWeight: 500, textAlign: "right" }}>
                    {value}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Live event log */}
          <div className="glass-card animate-slide-right delay-100" style={{ padding: "1.125rem", flex: 1 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.875rem" }}>
              <h3 style={{ fontSize: "0.8125rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
                Event Log
              </h3>
              {events.length > 0 && (
                <span style={{
                  background: "rgba(139,92,246,0.12)",
                  border: "1px solid rgba(139,92,246,0.2)",
                  borderRadius: 5,
                  padding: "0.1rem 0.4rem",
                  fontSize: "0.68rem",
                  fontWeight: 700,
                  color: "#c4b5fd",
                }}>
                  {events.length}
                </span>
              )}
            </div>
            <div style={{ maxHeight: 280, overflowY: "auto" }}>
              {events.length === 0 ? (
                <div style={{ padding: "1rem 0", textAlign: "center" }}>
                  <div style={{ fontSize: "1.5rem", marginBottom: "0.5rem" }}>⏳</div>
                  <p style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                    {isConnected ? "Waiting for events…" : "Connecting to stream…"}
                  </p>
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column" }}>
                  {[...events].reverse().map((evt, i) => {
                    const evtColors: Record<string, string> = {
                      agent_started: "#3b82f6",
                      agent_completed: "var(--green)",
                      run_completed: "var(--green)",
                      run_failed: "var(--red)",
                      hitl_required: "#8b5cf6",
                    };
                    const evtColor = evtColors[evt.event] ?? "var(--text-muted)";
                    return (
                      <div key={i} className="animate-fade-in" style={{
                        padding: "0.4rem 0",
                        borderBottom: i < events.length - 1 ? "1px solid var(--border-subtle)" : undefined,
                        display: "flex",
                        alignItems: "flex-start",
                        gap: "0.5rem",
                      }}>
                        <div style={{ width: 6, height: 6, borderRadius: "50%", background: evtColor, marginTop: 5, flexShrink: 0 }} />
                        <div>
                          <span style={{ fontSize: "0.75rem", color: evtColor, fontWeight: 600 }}>
                            {evt.event.replace(/_/g, " ")}
                          </span>
                          {evt.agent && (
                            <span style={{ fontSize: "0.73rem", color: "var(--text-muted)", marginLeft: 4 }}>
                              — {evt.agent.replace(/_/g, " ")}
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
