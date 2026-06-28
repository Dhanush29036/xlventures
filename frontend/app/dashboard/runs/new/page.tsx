"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { getICPConfigs, createRun } from "@/lib/api";
import type { ICPConfig } from "@/lib/types";

const STEPS = [
  { label: "ICP Profile", desc: "Choose your target profile" },
  { label: "Configure", desc: "Set parameters" },
  { label: "Launch", desc: "Review & start" },
];

export default function NewRunPage() {
  const router = useRouter();
  const [step, setStep] = useState(1);
  const [icps, setIcps] = useState<ICPConfig[]>([]);
  const [selectedIcp, setSelectedIcp] = useState<string>("");
  const [maxCompanies, setMaxCompanies] = useState(20);
  const [companyDomain, setCompanyDomain] = useState("");
  const [keywords, setKeywords] = useState<string[]>([]);
  const [kwInput, setKwInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [icpLoading, setIcpLoading] = useState(true);

  useEffect(() => {
    getICPConfigs()
      .then(setIcps)
      .catch(console.error)
      .finally(() => setIcpLoading(false));
  }, []);

  function addKeyword() {
    const kw = kwInput.trim();
    if (kw && !keywords.includes(kw)) {
      setKeywords((k) => [...k, kw]);
      setKwInput("");
    }
  }

  async function handleLaunch() {
    if (!selectedIcp) return;
    setLoading(true);
    setError(null);
    try {
      const run = await createRun({
        icp_config_id: selectedIcp,
        max_companies: maxCompanies,
        trigger_keywords: keywords,
        company_domain: companyDomain.trim() || undefined,
      });
      router.push(`/dashboard/runs/${run.id}`);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create run");
      setLoading(false);
    }
  }

  const selectedIcpObj = icps.find((i) => i.id === selectedIcp);

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }}>
      {/* Header */}
      <div className="animate-fade-in" style={{ marginBottom: "2rem" }}>
        <h1 style={{ fontSize: "1.75rem", fontWeight: 800, letterSpacing: "-0.04em", marginBottom: "0.25rem" }}>
          New Discovery Run
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.875rem" }}>
          Configure and launch a prospect intelligence pipeline
        </p>
      </div>

      {/* Step indicator */}
      <div className="animate-fade-in delay-100" style={{ display: "flex", alignItems: "center", marginBottom: "2rem" }}>
        {STEPS.map((s, i) => {
          const num = i + 1;
          const isDone = step > num;
          const isActive = step === num;
          return (
            <div key={s.label} style={{ display: "flex", alignItems: "center" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.625rem" }}>
                <div style={{
                  width: 30, height: 30,
                  borderRadius: "50%",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: isDone ? "0.8rem" : "0.8125rem",
                  fontWeight: 700,
                  transition: "all 0.3s ease",
                  background: isDone
                    ? "var(--green)"
                    : isActive
                      ? "linear-gradient(135deg, #7c3aed, #3b82f6)"
                      : "var(--bg-elevated)",
                  border: `1px solid ${isDone ? "var(--green)" : isActive ? "#7c3aed" : "var(--border-default)"}`,
                  color: isDone || isActive ? "white" : "var(--text-dim)",
                  boxShadow: isActive ? "0 2px 10px rgba(124,58,237,0.4)" : undefined,
                }}>
                  {isDone ? (
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3">
                      <polyline points="20,6 9,17 4,12"/>
                    </svg>
                  ) : num}
                </div>
                <div style={{ display: "flex", flexDirection: "column" }}>
                  <span style={{
                    fontSize: "0.8125rem",
                    fontWeight: isActive ? 600 : 400,
                    color: isActive ? "var(--text-primary)" : isDone ? "var(--text-secondary)" : "var(--text-muted)",
                    transition: "all 0.2s",
                  }}>
                    {s.label}
                  </span>
                  <span style={{ fontSize: "0.72rem", color: "var(--text-dim)" }}>{s.desc}</span>
                </div>
              </div>
              {i < STEPS.length - 1 && (
                <div style={{
                  flex: 1,
                  height: 1,
                  background: isDone ? "rgba(34,197,94,0.3)" : "var(--border-subtle)",
                  margin: "0 1rem",
                  minWidth: 40,
                  transition: "background 0.3s",
                }} />
              )}
            </div>
          );
        })}
      </div>

      {/* Step content */}
      <div className="glass-card animate-scale-in" style={{ padding: "2rem" }}>
        {/* Step 1: Select ICP */}
        {step === 1 && (
          <div>
            <div style={{ marginBottom: "1.5rem" }}>
              <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, marginBottom: "0.25rem" }}>
                Choose ICP Configuration
              </h2>
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Select the Ideal Customer Profile that matches your target market
              </p>
            </div>

            {icpLoading ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="skeleton" style={{ height: 72, borderRadius: 12 }} />
                ))}
              </div>
            ) : icps.length === 0 ? (
              <div style={{ textAlign: "center", padding: "2.5rem 1rem", background: "var(--bg-elevated)", borderRadius: 12, border: "1px solid var(--border-subtle)" }}>
                <div style={{ fontSize: "2rem", marginBottom: "0.75rem" }}>⚙️</div>
                <p style={{ fontWeight: 600, marginBottom: "0.375rem" }}>No ICP configs yet</p>
                <p style={{ fontSize: "0.875rem", color: "var(--text-muted)", marginBottom: "1rem" }}>
                  Create an ICP configuration first to define your ideal customer
                </p>
                <a href="/dashboard/icp/new" className="btn-primary">Create ICP Config</a>
              </div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.625rem" }}>
                {icps.map((icp) => {
                  const isSelected = selectedIcp === icp.id;
                  return (
                    <div
                      key={icp.id}
                      onClick={() => setSelectedIcp(icp.id)}
                      style={{
                        padding: "1rem 1.25rem",
                        borderRadius: 12,
                        cursor: "pointer",
                        border: "1px solid",
                        borderColor: isSelected ? "rgba(139,92,246,0.5)" : "var(--border-subtle)",
                        background: isSelected ? "rgba(139,92,246,0.08)" : "var(--bg-elevated)",
                        transition: "all 0.18s ease",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                      }}
                      onMouseEnter={(e) => {
                        if (!isSelected) {
                          (e.currentTarget as HTMLElement).style.borderColor = "var(--border-default)";
                          (e.currentTarget as HTMLElement).style.background = "rgba(255,255,255,0.04)";
                        }
                      }}
                      onMouseLeave={(e) => {
                        if (!isSelected) {
                          (e.currentTarget as HTMLElement).style.borderColor = "var(--border-subtle)";
                          (e.currentTarget as HTMLElement).style.background = "var(--bg-elevated)";
                        }
                      }}
                    >
                      <div>
                        <div style={{ fontWeight: 600, fontSize: "0.9375rem", marginBottom: 4, color: isSelected ? "#c4b5fd" : "var(--text-primary)" }}>
                          {icp.name}
                        </div>
                        <div style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                          {Object.keys(icp.rules_json ?? {}).slice(0, 3).join(" · ")}
                        </div>
                      </div>
                      <div style={{
                        width: 22, height: 22, borderRadius: "50%",
                        border: `2px solid ${isSelected ? "var(--brand-purple)" : "var(--border-default)"}`,
                        background: isSelected ? "var(--brand-purple)" : "transparent",
                        display: "flex", alignItems: "center", justifyContent: "center",
                        transition: "all 0.2s",
                        flexShrink: 0,
                      }}>
                        {isSelected && (
                          <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="3">
                            <polyline points="20,6 9,17 4,12"/>
                          </svg>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <div style={{ marginTop: "1.75rem", display: "flex", justifyContent: "flex-end" }}>
              <button className="btn-primary" onClick={() => setStep(2)} disabled={!selectedIcp}>
                Continue
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12,5 19,12 12,19"/>
                </svg>
              </button>
            </div>
          </div>
        )}

        {/* Step 2: Configure */}
        {step === 2 && (
          <div>
            <div style={{ marginBottom: "1.5rem" }}>
              <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, marginBottom: "0.25rem" }}>Run Parameters</h2>
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Configure scope and targeting for this discovery run
              </p>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
              {/* Companies slider */}
              <div style={{ padding: "1.25rem", background: "var(--bg-elevated)", borderRadius: 12, border: "1px solid var(--border-subtle)" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "1rem" }}>
                  <label style={{ marginBottom: 0, fontSize: "0.875rem", color: "var(--text-secondary)", fontWeight: 600 }}>
                    Max Companies
                  </label>
                  <span style={{
                    fontSize: "1.5rem",
                    fontWeight: 800,
                    background: "linear-gradient(135deg, #a78bfa, #38bdf8)",
                    WebkitBackgroundClip: "text",
                    WebkitTextFillColor: "transparent",
                    backgroundClip: "text",
                    letterSpacing: "-0.04em",
                  }}>
                    {maxCompanies}
                  </span>
                </div>
                <input
                  type="range"
                  min={10}
                  max={200}
                  step={10}
                  value={maxCompanies}
                  onChange={(e) => setMaxCompanies(Number(e.target.value))}
                />
                <div style={{ display: "flex", justifyContent: "space-between", fontSize: "0.72rem", color: "var(--text-dim)", marginTop: "0.375rem" }}>
                  <span>10</span><span>200</span>
                </div>
              </div>

              {/* Target domain */}
              <div>
                <label>Target Domain</label>
                <input
                  value={companyDomain}
                  onChange={(e) => setCompanyDomain(e.target.value)}
                  placeholder="e.g. stripe.com, openai.com"
                />
                <p style={{ color: "var(--text-muted)", fontSize: "0.75rem", marginTop: "0.375rem", display: "flex", alignItems: "center", gap: "0.3rem" }}>
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
                  </svg>
                  Leave empty to use demo companies. Provide a domain for targeted discovery.
                </p>
              </div>

              {/* Keywords */}
              <div>
                <label>Trigger Keywords <span style={{ color: "var(--text-dim)", fontWeight: 400 }}>(optional)</span></label>
                <div style={{ display: "flex", gap: "0.625rem" }}>
                  <input
                    value={kwInput}
                    onChange={(e) => setKwInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addKeyword())}
                    placeholder="e.g. Series B, AI adoption, hiring..."
                  />
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={addKeyword}
                    style={{ flexShrink: 0 }}
                  >
                    Add
                  </button>
                </div>
                {keywords.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem", marginTop: "0.625rem" }}>
                    {keywords.map((kw) => (
                      <button
                        key={kw}
                        type="button"
                        className="chip"
                        onClick={() => setKeywords((k) => k.filter((x) => x !== kw))}
                      >
                        {kw}
                        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            <div style={{ marginTop: "2rem", display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
              <button className="btn-secondary" onClick={() => setStep(1)}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12,19 5,12 12,5"/>
                </svg>
                Back
              </button>
              <button className="btn-primary" onClick={() => setStep(3)}>
                Review
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12,5 19,12 12,19"/>
                </svg>
              </button>
            </div>
          </div>
        )}

        {/* Step 3: Review */}
        {step === 3 && (
          <div>
            <div style={{ marginBottom: "1.5rem" }}>
              <h2 style={{ fontSize: "1.0625rem", fontWeight: 700, marginBottom: "0.25rem" }}>Review & Launch</h2>
              <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                Confirm your configuration before starting the pipeline
              </p>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.5rem", marginBottom: "1.75rem" }}>
              {[
                { label: "ICP Config", value: selectedIcpObj?.name ?? "—", icon: "⚙️" },
                { label: "Target Domain", value: companyDomain.trim() || "Demo companies", icon: "🌐" },
                { label: "Max Companies", value: String(maxCompanies), icon: "🏢" },
                { label: "Keywords", value: keywords.length > 0 ? keywords.join(", ") : "None", icon: "🔍" },
              ].map((row, i) => (
                <div key={row.label} className="animate-fade-in" style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "0.875rem",
                  padding: "0.875rem 1rem",
                  background: "var(--bg-elevated)",
                  borderRadius: 10,
                  border: "1px solid var(--border-subtle)",
                  animationDelay: `${i * 60}ms`,
                }}>
                  <span style={{ fontSize: "1.1rem", flexShrink: 0 }}>{row.icon}</span>
                  <span style={{ fontSize: "0.8125rem", color: "var(--text-muted)", flex: 1 }}>{row.label}</span>
                  <span style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--text-primary)", textAlign: "right", maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {row.value}
                  </span>
                </div>
              ))}
            </div>

            {/* Pipeline preview */}
            <div style={{ marginBottom: "1.5rem", padding: "1rem", background: "rgba(139,92,246,0.04)", border: "1px solid rgba(139,92,246,0.12)", borderRadius: 10 }}>
              <div style={{ fontSize: "0.75rem", fontWeight: 700, color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.07em", marginBottom: "0.625rem" }}>
                Pipeline Stages
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "0.375rem" }}>
                {["Trigger Monitor", "ICP Scorer", "Contact Enrichment", "Persona Finder", "Validation", "Summary"].map((stage, i) => (
                  <span key={stage} style={{
                    fontSize: "0.75rem",
                    color: "#c4b5fd",
                    background: "rgba(139,92,246,0.12)",
                    border: "1px solid rgba(139,92,246,0.2)",
                    borderRadius: 6,
                    padding: "0.2rem 0.6rem",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                  }}>
                    <span style={{ color: "var(--text-dim)", fontSize: "0.65rem" }}>{i + 1}.</span>
                    {stage}
                  </span>
                ))}
              </div>
            </div>

            {error && (
              <div style={{
                background: "rgba(239,68,68,0.08)",
                border: "1px solid rgba(239,68,68,0.25)",
                borderRadius: 8,
                padding: "0.75rem 1rem",
                color: "#fca5a5",
                fontSize: "0.875rem",
                marginBottom: "1rem",
              }}>
                {error}
              </div>
            )}

            <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
              <button className="btn-secondary" onClick={() => setStep(2)}>
                <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12,19 5,12 12,5"/>
                </svg>
                Back
              </button>
              <button className="btn-primary" onClick={handleLaunch} disabled={loading} style={{ minWidth: 140, justifyContent: "center" }}>
                {loading ? (
                  <>
                    <div className="spinner spinner-sm" />
                    Launching…
                  </>
                ) : (
                  <>
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <polygon points="5,3 19,12 5,21"/>
                    </svg>
                    Launch Run
                  </>
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
