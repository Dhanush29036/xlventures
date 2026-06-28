"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/lib/store";
import { login } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const { setAuth } = useAuthStore();
  const [email, setEmail] = useState("demo@xlventures.ai");
  const [password, setPassword] = useState("demo123");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await login(email, password);
      setAuth(res.access_token, res.tenant_id, res.email);
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed. Please check your credentials.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      background: "var(--bg-base)",
      position: "relative",
      overflow: "hidden",
    }}>
      {/* Background decorations */}
      <div style={{
        position: "absolute",
        top: "-30%",
        right: "-15%",
        width: 600,
        height: 600,
        borderRadius: "50%",
        background: "radial-gradient(circle, rgba(124,58,237,0.12) 0%, transparent 70%)",
        pointerEvents: "none",
      }} />
      <div style={{
        position: "absolute",
        bottom: "-20%",
        left: "-10%",
        width: 500,
        height: 500,
        borderRadius: "50%",
        background: "radial-gradient(circle, rgba(59,130,246,0.08) 0%, transparent 70%)",
        pointerEvents: "none",
      }} />

      {/* Left panel - branding */}
      <div style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        justifyContent: "center",
        padding: "4rem 5rem",
        position: "relative",
      }}>
        <div className="animate-fade-in">
          {/* Logo mark */}
          <div style={{
            width: 48, height: 48, borderRadius: 14,
            background: "linear-gradient(135deg, #7c3aed 0%, #3b82f6 100%)",
            display: "flex", alignItems: "center", justifyContent: "center",
            marginBottom: "2.5rem",
            boxShadow: "0 4px 24px rgba(124,58,237,0.4)",
          }}>
            <svg width="22" height="22" viewBox="0 0 24 24" fill="white">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
            </svg>
          </div>

          <h1 style={{ fontSize: "2.75rem", fontWeight: 900, letterSpacing: "-0.05em", lineHeight: 1.05, marginBottom: "1rem", color: "var(--text-primary)" }}>
            Prospect<br />
            <span className="gradient-text">Intelligence</span>
          </h1>
          <p style={{ fontSize: "1.0625rem", color: "var(--text-secondary)", lineHeight: 1.6, maxWidth: 380 }}>
            AI-powered B2B discovery pipeline. Find the right companies, 
            enrich contacts, and accelerate your sales motion.
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.875rem", marginTop: "2.5rem" }}>
            {[
              { icon: "🎯", text: "ICP-scored prospect discovery" },
              { icon: "⚡", text: "Real-time agent pipeline execution" },
              { icon: "🤝", text: "Human-in-the-loop review gates" },
            ].map((item) => (
              <div key={item.text} style={{ display: "flex", alignItems: "center", gap: "0.75rem" }}>
                <span style={{ fontSize: "1.125rem" }}>{item.icon}</span>
                <span style={{ fontSize: "0.9rem", color: "var(--text-muted)" }}>{item.text}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Right panel - login form */}
      <div style={{
        width: 480,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "2rem",
        borderLeft: "1px solid var(--border-subtle)",
        background: "var(--bg-surface)",
      }}>
        <div className="animate-slide-right" style={{ width: "100%", maxWidth: 380 }}>
          <div style={{ marginBottom: "2rem" }}>
            <h2 style={{ fontSize: "1.625rem", fontWeight: 800, letterSpacing: "-0.03em", marginBottom: "0.375rem" }}>
              Welcome back
            </h2>
            <p style={{ fontSize: "0.875rem", color: "var(--text-muted)" }}>
              Sign in to your account to continue
            </p>
          </div>

          {error && (
            <div className="animate-scale-in" style={{
              background: "rgba(239,68,68,0.08)",
              border: "1px solid rgba(239,68,68,0.25)",
              borderRadius: 10,
              padding: "0.75rem 1rem",
              marginBottom: "1.25rem",
              color: "#fca5a5",
              fontSize: "0.875rem",
              display: "flex",
              alignItems: "center",
              gap: "0.5rem",
            }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.125rem" }}>
            <div>
              <label>Email address</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                id="email-input"
              />
            </div>
            <div>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.4rem" }}>
                <label style={{ marginBottom: 0 }}>Password</label>
              </div>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                id="password-input"
              />
            </div>

            <button
              type="submit"
              className="btn-primary"
              disabled={loading}
              style={{ width: "100%", justifyContent: "center", padding: "0.75rem", marginTop: "0.25rem", fontSize: "0.9375rem" }}
            >
              {loading ? (
                <>
                  <div className="spinner spinner-sm" />
                  Signing in…
                </>
              ) : (
                <>
                  Sign in
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <line x1="5" y1="12" x2="19" y2="12"/><polyline points="12,5 19,12 12,19"/>
                  </svg>
                </>
              )}
            </button>
          </form>

          <div style={{ marginTop: "1.5rem", padding: "0.875rem 1rem", background: "var(--bg-elevated)", borderRadius: 10, border: "1px solid var(--border-default)" }}>
            <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.375rem", fontWeight: 500 }}>
              Demo credentials
            </p>
            <code style={{ fontSize: "0.8rem", color: "#c4b5fd" }}>demo@xlventures.ai / demo123</code>
          </div>

          <p style={{ textAlign: "center", marginTop: "1.5rem", color: "var(--text-muted)", fontSize: "0.875rem" }}>
            No account?{" "}
            <Link href="/register" style={{ color: "#a78bfa", textDecoration: "none", fontWeight: 600 }}>
              Create one
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
