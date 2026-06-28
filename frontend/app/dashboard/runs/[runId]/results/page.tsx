"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { getResults, exportCSV, approveCompany, rejectCompany } from "@/lib/api";
import type { ResultsResponse, CompanyResult } from "@/lib/types";

function ConfidenceBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
      <div className="confidence-bar" style={{ flex: 1 }}>
        <div className="confidence-fill" style={{ width: `${pct}%` }} />
      </div>
      <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", width: 30 }}>{pct}%</span>
    </div>
  );
}

function CompanyRow({ company, runId }: { company: CompanyResult; runId: string }) {
  const [expanded, setExpanded] = useState(false);
  const [actionDone, setActionDone] = useState<string | null>(null);

  return (
    <>
      <tr className="table-row" onClick={() => setExpanded(!expanded)} style={{ cursor: "pointer" }}>
        <td style={{ padding: "0.875rem 1rem" }}>
          <div style={{ fontWeight: 600, fontSize: "0.875rem" }}>{company.name}</div>
          <div style={{ fontSize: "0.75rem", color: "#a78bfa" }}>{company.domain}</div>
        </td>
        <td style={{ padding: "0.875rem 1rem", width: 150 }}><ConfidenceBar score={company.icp_score} /></td>
        <td style={{ padding: "0.875rem 1rem" }}>
          <span className={`badge badge-${company.recommended_action}`}>{company.recommended_action}</span>
        </td>
        <td style={{ padding: "0.875rem 1rem", fontSize: "0.875rem", color: "var(--text-muted)" }}>{company.funding_stage || "—"}</td>
        <td style={{ padding: "0.875rem 1rem", fontSize: "0.875rem", color: "var(--text-muted)" }}>{company.headcount || "—"}</td>
        <td style={{ padding: "0.875rem 1rem", fontSize: "0.875rem", color: "var(--text-muted)" }}>{company.people.length}</td>
        <td style={{ padding: "0.875rem 1rem", fontSize: "0.875rem", color: "var(--text-muted)" }}>{company.signals.length}</td>
        <td style={{ padding: "0.875rem 1rem" }}>
          {actionDone ? (
            <span style={{ fontSize: "0.8rem", color: "#10b981" }}>✓ {actionDone}</span>
          ) : (
            <div style={{ display: "flex", gap: "0.375rem" }} onClick={(e) => e.stopPropagation()}>
              <button className="btn-success" style={{ padding: "0.3rem 0.625rem", fontSize: "0.75rem" }}
                onClick={() => approveCompany(runId, company.domain).then(() => setActionDone("approved"))}>
                ✓ Approve
              </button>
              <button className="btn-danger" style={{ padding: "0.3rem 0.625rem", fontSize: "0.75rem" }}
                onClick={() => rejectCompany(runId, company.domain).then(() => setActionDone("rejected"))}>
                ✗ Reject
              </button>
            </div>
          )}
        </td>
      </tr>
      {expanded && (
        <tr>
          <td colSpan={8} style={{ padding: "0 1rem 1rem" }}>
            <div style={{ background: "rgba(255,255,255,0.03)", borderRadius: 8, padding: "1rem" }}>
              <div style={{ fontWeight: 600, marginBottom: "0.75rem", fontSize: "0.875rem" }}>👥 Contacts ({company.people.length})</div>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(250px, 1fr))", gap: "0.5rem" }}>
                {company.people.map((p) => (
                  <div key={p.email} style={{ padding: "0.75rem", background: "var(--bg-glass)", borderRadius: 8, border: "1px solid var(--border-glass)" }}>
                    <div style={{ fontWeight: 600, fontSize: "0.8rem" }}>{p.name}</div>
                    <div style={{ fontSize: "0.75rem", color: "#a78bfa" }}>{p.title}</div>
                    <div style={{ fontSize: "0.72rem", color: "var(--text-muted)" }}>{p.email}</div>
                    {p.is_decision_maker && <span style={{ fontSize: "0.7rem", color: "#10b981" }}>⭐ Decision Maker</span>}
                  </div>
                ))}
              </div>
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

export default function ResultsPage() {
  const params = useParams<{ runId: string }>();
  const runId = params.runId;
  const [results, setResults] = useState<ResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [minScore, setMinScore] = useState(0);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    getResults(runId).then(setResults).catch(console.error).finally(() => setLoading(false));
  }, [runId]);

  async function handleExport() {
    setExporting(true);
    try {
      const blob = await exportCSV(runId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `results_${runId.slice(0, 8)}.csv`;
      a.click();
    } finally {
      setExporting(false);
    }
  }

  const filtered = results?.companies.filter((c) => c.icp_score >= minScore / 100) ?? [];

  return (
    <div style={{ maxWidth: 1200, margin: "0 auto" }} className="animate-fade-in">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: "2rem" }}>
        <div>
          <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: 4 }}>
            <Link href={`/dashboard/runs/${runId}`} style={{ color: "#a78bfa", textDecoration: "none" }}>← Run Detail</Link>
          </div>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 800 }}><span className="gradient-text">Results</span></h1>
        </div>
        <button className="btn-secondary" onClick={handleExport} disabled={exporting}>
          {exporting ? "Exporting..." : "⬇ Export CSV"}
        </button>
      </div>

      {loading ? (
        <div style={{ textAlign: "center", padding: "4rem" }}><div className="spinner" style={{ margin: "0 auto" }} /></div>
      ) : !results ? (
        <div style={{ textAlign: "center", padding: "4rem", color: "var(--text-muted)" }}>No results found</div>
      ) : (
        <>
          {/* Summary stats */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "1rem", marginBottom: "1.5rem" }}>
            {[
              { label: "Companies", value: results.total_companies, icon: "🏢" },
              { label: "Contacts", value: results.total_contacts, icon: "👥" },
              { label: "Signals", value: results.total_signals, icon: "📡" },
            ].map((s) => (
              <div key={s.label} className="stat-card">
                <div style={{ fontSize: "1.25rem" }}>{s.icon}</div>
                <div className="stat-value">{s.value}</div>
                <div className="stat-label">{s.label}</div>
              </div>
            ))}
          </div>

          {/* Filter */}
          <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginBottom: "1rem" }}>
            <label style={{ whiteSpace: "nowrap" }}>Min ICP Score: <strong style={{ color: "#a78bfa" }}>{minScore}%</strong></label>
            <input type="range" min={0} max={100} step={5} value={minScore} onChange={(e) => setMinScore(Number(e.target.value))} style={{ flex: 1, maxWidth: 200 }} />
            <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>Showing {filtered.length} / {results.total_companies}</span>
          </div>

          {/* Table */}
          <div className="glass-card" style={{ overflow: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-glass)" }}>
                  {["Company", "ICP Score", "Action", "Stage", "Headcount", "Contacts", "Signals", ""].map((h) => (
                    <th key={h} style={{ padding: "0.875rem 1rem", textAlign: "left", fontSize: "0.75rem", color: "var(--text-muted)", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {filtered.map((company) => <CompanyRow key={company.domain} company={company} runId={runId} />)}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
