"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { getHITLItem, approveHITL, rejectHITL, editHITL } from "@/lib/api";
import type { HITLItem } from "@/lib/types";

export default function HITLDetailPage() {
  const params = useParams<{ hitlId: string }>();
  const router = useRouter();
  const [item, setItem] = useState<HITLItem | null>(null);
  const [loading, setLoading] = useState(true);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [rejectReason, setRejectReason] = useState("");
  const [editedPayload, setEditedPayload] = useState("");
  const [actionLoading, setActionLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getHITLItem(params.hitlId).then((data) => {
      setItem(data);
      setEditedPayload(JSON.stringify(data.payload_json, null, 2));
    }).catch(console.error).finally(() => setLoading(false));
  }, [params.hitlId]);

  async function handleApprove() {
    setActionLoading(true);
    try {
      await approveHITL(params.hitlId);
      router.push("/dashboard/hitl");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to approve");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleReject() {
    if (!rejectReason.trim()) return;
    setActionLoading(true);
    try {
      await rejectHITL(params.hitlId, rejectReason);
      router.push("/dashboard/hitl");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to reject");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleEditApprove() {
    setActionLoading(true);
    try {
      const parsed = JSON.parse(editedPayload);
      await editHITL(params.hitlId, parsed);
      router.push("/dashboard/hitl");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Invalid JSON or request failed");
    } finally {
      setActionLoading(false);
    }
  }

  if (loading) return <div style={{ textAlign: "center", padding: "4rem" }}><div className="spinner" style={{ margin: "0 auto" }} /></div>;
  if (!item) return <div style={{ textAlign: "center", padding: "4rem", color: "var(--text-muted)" }}>Item not found</div>;

  const payload = item.payload_json;
  const isPending = item.status === "pending";

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }} className="animate-fade-in">
      <div style={{ marginBottom: "2rem" }}>
        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginBottom: 4 }}>
          <Link href="/dashboard/hitl" style={{ color: "#a78bfa", textDecoration: "none" }}>← HITL Inbox</Link>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
          <h1 style={{ fontSize: "1.75rem", fontWeight: 800 }}>
            <span className="gradient-text">Review Item</span>
          </h1>
          <span className={`badge badge-${item.status}`} style={{ fontSize: "0.8rem" }}>{item.status}</span>
        </div>
        <div style={{ fontSize: "0.8rem", color: "var(--text-muted)", marginTop: 4 }}>
          Agent: <strong>{item.agent_name}</strong> · Run: <strong style={{ color: "#a78bfa" }}>{item.run_id.slice(0, 8)}...</strong>
        </div>
      </div>

      {error && (
        <div style={{ background: "rgba(239,68,68,0.12)", border: "1px solid rgba(239,68,68,0.3)", borderRadius: 8, padding: "0.75rem 1rem", marginBottom: "1rem", color: "#ef4444", fontSize: "0.875rem" }}>
          {error}
        </div>
      )}

      {/* Payload cards */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "1rem", marginBottom: "1.5rem" }}>
        <div className="glass-card" style={{ padding: "1.25rem" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>Company</div>
          {[
            ["Name", (payload?.name as string) || (payload?.domain as string)],
            ["Domain", payload?.domain as string],
            ["ICP Score", payload?.icp_score !== undefined ? `${Math.round((payload.icp_score as number) * 100)}%` : "—"],
            ["Funding Stage", payload?.funding_stage as string],
            ["Headcount", payload?.headcount as string],
          ].map(([k, v]) => v && (
            <div key={k} style={{ display: "flex", justifyContent: "space-between", padding: "0.375rem 0", borderBottom: "1px solid var(--border-glass)", fontSize: "0.8rem" }}>
              <span style={{ color: "var(--text-muted)" }}>{k}</span>
              <span style={{ fontWeight: 600 }}>{String(v)}</span>
            </div>
          ))}
        </div>

        <div className="glass-card" style={{ padding: "1.25rem" }}>
          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>Issues / Context</div>
          {Array.isArray(payload?.issues) ? (
            (payload.issues as string[]).map((issue, i) => (
              <div key={i} style={{ display: "flex", alignItems: "center", gap: "0.5rem", padding: "0.375rem 0", fontSize: "0.8rem", color: "#f59e0b" }}>
                <span>⚠</span> {issue}
              </div>
            ))
          ) : (
            <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>No issues reported</p>
          )}
        </div>
      </div>

      {/* Raw payload */}
      <div className="glass-card" style={{ padding: "1.25rem", marginBottom: "1.5rem" }}>
        <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", marginBottom: "0.75rem", textTransform: "uppercase", letterSpacing: "0.05em" }}>Full Payload</div>
        <pre style={{ fontSize: "0.75rem", color: "#a78bfa", overflow: "auto", maxHeight: 200, lineHeight: 1.5 }}>
          {JSON.stringify(payload, null, 2)}
        </pre>
      </div>

      {/* Actions */}
      {isPending && (
        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button className="btn-success" onClick={handleApprove} disabled={actionLoading} style={{ flex: 1, padding: "0.875rem" }}>
            ✓ Approve & Resume
          </button>
          <button
            onClick={() => setShowEditModal(true)}
            style={{ flex: 1, padding: "0.875rem", background: "rgba(37,99,235,0.15)", color: "#60a5fa", border: "1px solid rgba(37,99,235,0.3)", borderRadius: 8, fontWeight: 600, cursor: "pointer" }}
          >
            ✏ Edit & Approve
          </button>
          <button className="btn-danger" onClick={() => setShowRejectModal(true)} disabled={actionLoading} style={{ flex: 1, padding: "0.875rem" }}>
            ✗ Reject
          </button>
        </div>
      )}

      {/* Reject Modal */}
      {showRejectModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
          <div className="glass-card" style={{ padding: "2rem", width: "90%", maxWidth: 480 }}>
            <h3 style={{ fontWeight: 700, marginBottom: "1rem" }}>Reject Item</h3>
            <label>Rejection Reason</label>
            <textarea value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} rows={3} placeholder="Explain why this was rejected..." />
            <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}>
              <button className="btn-secondary" onClick={() => setShowRejectModal(false)} style={{ flex: 1 }}>Cancel</button>
              <button className="btn-danger" onClick={handleReject} disabled={!rejectReason.trim() || actionLoading} style={{ flex: 1 }}>Submit Rejection</button>
            </div>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {showEditModal && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.7)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100 }}>
          <div className="glass-card" style={{ padding: "2rem", width: "90%", maxWidth: 600 }}>
            <h3 style={{ fontWeight: 700, marginBottom: "1rem" }}>Edit Payload & Approve</h3>
            <label>Edit JSON Payload</label>
            <textarea value={editedPayload} onChange={(e) => setEditedPayload(e.target.value)} rows={12} style={{ fontFamily: "monospace", fontSize: "0.8rem" }} />
            <div style={{ display: "flex", gap: "0.75rem", marginTop: "1rem" }}>
              <button className="btn-secondary" onClick={() => setShowEditModal(false)} style={{ flex: 1 }}>Cancel</button>
              <button className="btn-success" onClick={handleEditApprove} disabled={actionLoading} style={{ flex: 1 }}>Approve with Edits</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
