"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useAuthStore } from "@/lib/store";
import { register } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const { setAuth } = useAuthStore();
  const [form, setForm] = useState({ email: "", password: "", tenantName: "" });
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  function update(field: string) {
    return (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [field]: e.target.value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const res = await register(form.email, form.password, form.tenantName);
      setAuth(res.access_token, res.tenant_id, res.email);
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "radial-gradient(ellipse at 40% 60%, rgba(37,99,235,0.1) 0%, transparent 60%), var(--bg-primary)",
    }}>
      <div className="glass-card animate-fade-in" style={{ width: "100%", maxWidth: 420, padding: "2.5rem" }}>
        <div style={{ textAlign: "center", marginBottom: "2rem" }}>
          <div style={{
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            width: 56, height: 56, borderRadius: 16,
            background: "linear-gradient(135deg, #7c3aed, #2563eb)",
            marginBottom: "1rem",
          }}>
            <span style={{ fontSize: "1.5rem" }}>⚡</span>
          </div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: 800 }} className="gradient-text">
            Create Account
          </h1>
          <p style={{ color: "var(--text-muted)", fontSize: "0.875rem", marginTop: 4 }}>
            Start your free trial today
          </p>
        </div>

        {error && (
          <div style={{
            background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.3)",
            borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1.25rem",
            color: "#ef4444", fontSize: "0.875rem",
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div>
            <label>Company / Team Name</label>
            <input value={form.tenantName} onChange={update("tenantName")} placeholder="Acme Corp" required />
          </div>
          <div>
            <label>Email</label>
            <input type="email" value={form.email} onChange={update("email")} placeholder="you@company.com" required />
          </div>
          <div>
            <label>Password</label>
            <input type="password" value={form.password} onChange={update("password")} placeholder="Min. 8 characters" required minLength={6} />
          </div>

          <button type="submit" className="btn-primary" disabled={loading} style={{ marginTop: "0.5rem", padding: "0.75rem" }}>
            {loading ? <div className="spinner" style={{ margin: "0 auto" }} /> : "Create Account"}
          </button>
        </form>

        <p style={{ textAlign: "center", marginTop: "1.5rem", color: "var(--text-muted)", fontSize: "0.875rem" }}>
          Already have an account?{" "}
          <Link href="/login" style={{ color: "#a78bfa", textDecoration: "none", fontWeight: 600 }}>
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
