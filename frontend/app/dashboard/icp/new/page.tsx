"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createICPConfig } from "@/lib/api";

const FUNDING_STAGES = ["Pre-Seed", "Seed", "Series A", "Series B", "Series C", "Series D", "IPO"];
const INDUSTRIES = ["SaaS", "Fintech", "HealthTech", "Cloud Infrastructure", "DevTools", "E-commerce", "MarTech", "RegTech"];
const COUNTRIES = ["US", "UK", "EU", "CA", "AU", "SG"];

export default function NewICPPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [minHeadcount, setMinHeadcount] = useState(50);
  const [maxHeadcount, setMaxHeadcount] = useState(500);
  const [fundingStages, setFundingStages] = useState<string[]>([]);
  const [industries, setIndustries] = useState<string[]>([]);
  const [countries, setCountries] = useState<string[]>([]);
  const [minRevenue, setMinRevenue] = useState(0);
  const [targetTitles, setTargetTitles] = useState<string[]>([]);
  const [titleInput, setTitleInput] = useState("");
  const [description, setDescription] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle<T>(arr: T[], val: T): T[] {
    return arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val];
  }

  function addTitle() {
    const t = titleInput.trim();
    if (t && !targetTitles.includes(t)) { setTargetTitles((x) => [...x, t]); setTitleInput(""); }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const rules: Record<string, unknown> = {
        min_headcount: minHeadcount,
        max_headcount: maxHeadcount,
      };
      if (fundingStages.length > 0) rules.funding_stages = fundingStages;
      if (industries.length > 0) rules.industries = industries;
      if (countries.length > 0) rules.hq_countries = countries;
      if (minRevenue > 0) rules.min_revenue_usd = minRevenue;

      const persona: Record<string, unknown> = { description };
      if (targetTitles.length > 0) persona.target_titles = targetTitles;

      await createICPConfig({ name, rules_json: rules, persona_json: persona });
      router.push("/dashboard/icp");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to create ICP");
    } finally {
      setLoading(false);
    }
  }

  function MultiSelect({ label, options, selected, onChange }: { label: string; options: string[]; selected: string[]; onChange: (v: string[]) => void }) {
    return (
      <div style={{ marginBottom: "1.25rem" }}>
        <label>{label}</label>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.5rem" }}>
          {options.map((opt) => (
            <button key={opt} type="button" onClick={() => onChange(toggle(selected, opt))} style={{
              padding: "0.3rem 0.75rem", borderRadius: 999, border: "1px solid",
              borderColor: selected.includes(opt) ? "#7c3aed" : "var(--border-glass)",
              background: selected.includes(opt) ? "rgba(124,58,237,0.15)" : "transparent",
              color: selected.includes(opt) ? "#a78bfa" : "var(--text-muted)",
              cursor: "pointer", fontSize: "0.8rem",
            }}>
              {opt}
            </button>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div style={{ maxWidth: 720, margin: "0 auto" }} className="animate-fade-in">
      <div style={{ marginBottom: "2rem" }}>
        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: 4 }}>
          <Link href="/dashboard/icp" style={{ color: "#a78bfa", textDecoration: "none" }}>← ICP Configs</Link>
        </div>
        <h1 style={{ fontSize: "1.75rem", fontWeight: 800 }}><span className="gradient-text">New ICP Config</span></h1>
      </div>

      <form onSubmit={handleSubmit} className="glass-card" style={{ padding: "2rem" }}>
        {error && <div style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1.25rem", color: "#ef4444" }}>{error}</div>}

        <div style={{ marginBottom: "1.25rem" }}>
          <label>Configuration Name *</label>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. SaaS Mid-Market Engineering" required />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.25rem" }}>
          <div>
            <label>Min Headcount: <strong style={{ color: "#a78bfa" }}>{minHeadcount}</strong></label>
            <input type="range" min={10} max={1000} step={10} value={minHeadcount} onChange={(e) => setMinHeadcount(Number(e.target.value))} />
          </div>
          <div>
            <label>Max Headcount: <strong style={{ color: "#a78bfa" }}>{maxHeadcount === 10000 ? "Any" : maxHeadcount}</strong></label>
            <input type="range" min={100} max={10000} step={100} value={maxHeadcount} onChange={(e) => setMaxHeadcount(Number(e.target.value))} />
          </div>
        </div>

        <MultiSelect label="Funding Stages" options={FUNDING_STAGES} selected={fundingStages} onChange={setFundingStages} />
        <MultiSelect label="Industries" options={INDUSTRIES} selected={industries} onChange={setIndustries} />
        <MultiSelect label="HQ Countries" options={COUNTRIES} selected={countries} onChange={setCountries} />

        <div style={{ marginBottom: "1.25rem" }}>
          <label>Min Annual Revenue (USD): <strong style={{ color: "#a78bfa" }}>{minRevenue > 0 ? `$${(minRevenue / 1_000_000).toFixed(1)}M` : "None"}</strong></label>
          <input type="range" min={0} max={100_000_000} step={1_000_000} value={minRevenue} onChange={(e) => setMinRevenue(Number(e.target.value))} />
        </div>

        <div style={{ marginBottom: "1.25rem" }}>
          <label>Target Titles (Persona)</label>
          <div style={{ display: "flex", gap: "0.5rem" }}>
            <input value={titleInput} onChange={(e) => setTitleInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addTitle())} placeholder="CTO, VP Engineering..." />
            <button type="button" className="btn-secondary" onClick={addTitle} style={{ whiteSpace: "nowrap" }}>Add</button>
          </div>
          {targetTitles.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem", marginTop: "0.5rem" }}>
              {targetTitles.map((t) => (
                <span key={t} onClick={() => setTargetTitles((x) => x.filter((v) => v !== t))} style={{ background: "rgba(124,58,237,0.15)", color: "#a78bfa", borderRadius: 999, padding: "0.2rem 0.75rem", fontSize: "0.8rem", cursor: "pointer" }}>
                  {t} ×
                </span>
              ))}
            </div>
          )}
        </div>

        <div style={{ marginBottom: "1.5rem" }}>
          <label>Persona Description</label>
          <textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={2} placeholder="Describe your ideal buyer persona..." />
        </div>

        <div style={{ display: "flex", gap: "0.75rem", justifyContent: "flex-end" }}>
          <Link href="/dashboard/icp" className="btn-secondary">Cancel</Link>
          <button type="submit" className="btn-primary" disabled={loading}>{loading ? "Creating..." : "Create ICP Config"}</button>
        </div>
      </form>
    </div>
  );
}
