"use client";

import { useEffect, useState } from "react";
import { useStudio } from "@/lib/hooks/useStudio";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function StudioPage() {
  const { agents, workflowPlan, loading, error, fetchAgents, parseIntent, executeWorkflow, setWorkflowPlan } = useStudio();
  const [prompt, setPrompt] = useState("");
  const router = useRouter();

  useEffect(() => {
    fetchAgents();
  }, [fetchAgents]);

  const handleParse = (e: React.FormEvent) => {
    e.preventDefault();
    if (!prompt.trim()) return;
    parseIntent(prompt);
  };

  const handleExecute = async () => {
    if (!workflowPlan) return;
    // We just execute with the recommended agents for now
    const res = await executeWorkflow(workflowPlan.recommended_agents);
    if (res?.run_id) {
      router.push(`/dashboard/runs/${res.run_id}`);
    }
  };

  return (
    <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      <div className="animate-fade-in" style={{ marginBottom: "2.5rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <h1 style={{ fontSize: "2rem", fontWeight: 800, letterSpacing: "-0.04em", lineHeight: 1.1 }}>
            Agent Studio
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginTop: "0.375rem" }}>
            Build intelligence pipelines — visually or from a prompt.
          </p>
        </div>
        <Link href="/dashboard/studio/custom" className="btn-primary" style={{ background: "transparent", border: "1px solid var(--border-subtle)", color: "var(--text-primary)" }}>
          Build Custom Agent
        </Link>
      </div>

      {/* ── Visual Builder CTA ── */}
      <Link href="/dashboard/studio/pipeline" style={{ textDecoration: "none", display: "block", marginBottom: "2rem" }}>
        <div className="glass-card animate-fade-in" style={{
          padding: "1.75rem 2rem",
          background: "linear-gradient(135deg, rgba(124,58,237,0.12) 0%, rgba(59,130,246,0.08) 100%)",
          border: "1px solid rgba(124,58,237,0.25)",
          borderRadius: 16,
          display: "flex",
          alignItems: "center",
          gap: "1.5rem",
          transition: "all 0.2s",
          cursor: "pointer",
        }}
        onMouseOver={e => (e.currentTarget.style.borderColor = "rgba(124,58,237,0.5)")}
        onMouseOut={e => (e.currentTarget.style.borderColor = "rgba(124,58,237,0.25)")}
        >
          <div style={{
            width: 56, height: 56, borderRadius: 14, flexShrink: 0,
            background: "linear-gradient(135deg, #7c3aed, #3b82f6)",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "1.75rem",
            boxShadow: "0 4px 20px rgba(124,58,237,0.4)",
          }}>
            🔗
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 4 }}>
              <span style={{ fontWeight: 800, fontSize: "1.1rem", color: "#f1f5f9" }}>Visual Pipeline Builder</span>
              <span style={{
                fontSize: "0.65rem", fontWeight: 700, background: "linear-gradient(135deg,#7c3aed,#3b82f6)",
                color: "white", borderRadius: 5, padding: "2px 7px", letterSpacing: "0.05em",
              }}>NEW</span>
            </div>
            <p style={{ color: "#94a3b8", fontSize: "0.875rem", margin: 0 }}>
              Drag-and-drop agents, connect them like n8n, and run your intelligence pipeline live — with real-time status on every node.
            </p>
          </div>
          <div style={{ color: "#7c3aed", fontSize: "1.5rem", flexShrink: 0 }}>→</div>
        </div>
      </Link>

      <div className="glass-card animate-fade-in-up" style={{ padding: "2rem", marginBottom: "2rem" }}>
        <form onSubmit={handleParse}>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            placeholder="E.g. Find me fast growing devops companies that raised Series A recently, and get the emails for their engineering VPs."
            style={{
              width: "100%",
              minHeight: 120,
              background: "var(--bg-elevated)",
              border: "1px solid var(--border-subtle)",
              borderRadius: 12,
              padding: "1rem",
              color: "var(--text-primary)",
              fontSize: "1rem",
              fontFamily: "inherit",
              resize: "vertical",
              marginBottom: "1rem"
            }}
          />
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Powered by Claude 3.5 Sonnet</span>
            <button
              type="submit"
              className="btn-primary"
              disabled={loading || !prompt.trim()}
            >
              {loading ? "Analyzing..." : "Generate Workflow"}
            </button>
          </div>
        </form>
        {error && <div style={{ color: "#ef4444", marginTop: "1rem", fontSize: "0.9rem" }}>{error}</div>}
      </div>

      {workflowPlan && (
        <div className="animate-fade-in-up delay-100">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1rem" }}>
            <h2 style={{ fontSize: "1.2rem", fontWeight: 700 }}>Proposed Pipeline</h2>
            <button onClick={handleExecute} className="btn-primary" disabled={loading}>
              {loading ? "Starting..." : "Execute Pipeline"}
            </button>
          </div>
          
          <div className="glass-card" style={{ padding: "2rem" }}>
            <p style={{ color: "var(--text-secondary)", marginBottom: "1.5rem" }}>
              {workflowPlan.intent_summary}
            </p>
            
            <div style={{ display: "flex", flexWrap: "wrap", gap: "1rem" }}>
              {workflowPlan.recommended_agents.map((agentId, i) => {
                const agentDef = agents.find(a => a.agent_id === agentId);
                return (
                  <div key={agentId} style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "1rem",
                    padding: "1rem",
                    background: "var(--bg-elevated)",
                    border: "1px solid var(--border-subtle)",
                    borderRadius: 12,
                    flex: "1 1 200px",
                  }}>
                    <div style={{
                      width: 40, height: 40, borderRadius: 10,
                      background: "rgba(139,92,246,0.15)",
                      display: "flex", alignItems: "center", justifyContent: "center",
                      color: "#a78bfa",
                      fontWeight: 600
                    }}>
                      {i + 1}
                    </div>
                    <div>
                      <div style={{ fontWeight: 600 }}>{agentDef ? agentDef.name : agentId}</div>
                      {agentDef && <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: 4 }}>
                        {agentDef.description.slice(0, 60)}...
                      </div>}
                    </div>
                  </div>
                );
              })}
            </div>
            
            {workflowPlan.icp_config_extracted && Object.keys(workflowPlan.icp_config_extracted).length > 0 && (
              <div style={{ marginTop: "2rem" }}>
                <h3 style={{ fontSize: "0.9rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: "0.5rem" }}>
                  Extracted ICP Rules
                </h3>
                <pre style={{ 
                  background: "rgba(0,0,0,0.2)", 
                  padding: "1rem", 
                  borderRadius: 8,
                  fontSize: "0.85rem",
                  color: "#a78bfa"
                }}>
                  {JSON.stringify(workflowPlan.icp_config_extracted, null, 2)}
                </pre>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
