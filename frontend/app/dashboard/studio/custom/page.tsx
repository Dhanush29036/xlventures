"use client";

import { useState } from "react";
import { useStudio } from "@/lib/hooks/useStudio";
import Link from "next/link";
import { useRouter } from "next/navigation";

export default function CustomAgentPage() {
  const { buildCustomAgent, loading, error } = useStudio();
  const router = useRouter();
  
  const [formData, setFormData] = useState({
    name: "",
    description: "",
    inputs: "",
    outputs: "",
    tools_needed: ""
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setFormData(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const data = {
      ...formData,
      inputs: formData.inputs.split(",").map(s => s.trim()).filter(Boolean),
      outputs: formData.outputs.split(",").map(s => s.trim()).filter(Boolean),
      tools_needed: formData.tools_needed.split(",").map(s => s.trim()).filter(Boolean),
    };
    const res = await buildCustomAgent(data);
    if (res) {
      router.push("/dashboard/studio");
    }
  };

  return (
    <div style={{ maxWidth: 800, margin: "0 auto" }}>
      <div className="animate-fade-in" style={{ marginBottom: "2.5rem" }}>
        <Link href="/dashboard/studio" style={{ color: "var(--text-muted)", textDecoration: "none", fontSize: "0.85rem", display: "inline-flex", alignItems: "center", gap: 4, marginBottom: "1rem" }}>
          ← Back to Studio
        </Link>
        <h1 style={{ fontSize: "2rem", fontWeight: 800, letterSpacing: "-0.04em", lineHeight: 1.1 }}>
          Build Custom Agent
        </h1>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginTop: "0.375rem" }}>
          Define the inputs, outputs, and logic for a new custom agent.
        </p>
      </div>

      <div className="glass-card animate-fade-in-up delay-100" style={{ padding: "2rem" }}>
        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
          <div>
            <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>Agent Name</label>
            <input
              type="text"
              name="name"
              value={formData.name}
              onChange={handleChange}
              placeholder="E.g. GitHub Activity Scraper"
              required
              style={{
                width: "100%", padding: "0.75rem", background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: 8, color: "var(--text-primary)"
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>Description</label>
            <textarea
              name="description"
              value={formData.description}
              onChange={handleChange}
              placeholder="What does this agent do?"
              required
              rows={3}
              style={{
                width: "100%", padding: "0.75rem", background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: 8, color: "var(--text-primary)"
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>Required Inputs (comma separated)</label>
            <input
              type="text"
              name="inputs"
              value={formData.inputs}
              onChange={handleChange}
              placeholder="E.g. github_url, timeframe"
              required
              style={{
                width: "100%", padding: "0.75rem", background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: 8, color: "var(--text-primary)"
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>Outputs (comma separated)</label>
            <input
              type="text"
              name="outputs"
              value={formData.outputs}
              onChange={handleChange}
              placeholder="E.g. commit_count, recent_repo"
              required
              style={{
                width: "100%", padding: "0.75rem", background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: 8, color: "var(--text-primary)"
              }}
            />
          </div>

          <div>
            <label style={{ display: "block", fontSize: "0.85rem", fontWeight: 600, color: "var(--text-secondary)", marginBottom: "0.5rem" }}>Tools Needed (comma separated)</label>
            <input
              type="text"
              name="tools_needed"
              value={formData.tools_needed}
              onChange={handleChange}
              placeholder="E.g. requests, beautifulsoup4"
              style={{
                width: "100%", padding: "0.75rem", background: "var(--bg-elevated)", border: "1px solid var(--border-subtle)", borderRadius: 8, color: "var(--text-primary)"
              }}
            />
          </div>

          {error && <div style={{ color: "#ef4444", fontSize: "0.9rem" }}>{error}</div>}

          <div style={{ display: "flex", justifyContent: "flex-end", marginTop: "1rem" }}>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? "Building..." : "Build Custom Agent"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
