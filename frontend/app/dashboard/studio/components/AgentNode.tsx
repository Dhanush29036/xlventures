"use client";

import { memo } from "react";
import { Handle, Position, NodeProps } from "@xyflow/react";

// ── Status colours ──────────────────────────────────────────
const STATUS_COLORS: Record<string, string> = {
  idle:    "rgba(100,116,139,0.6)",
  running: "#f59e0b",
  done:    "#22c55e",
  error:   "#ef4444",
};

// ── Agent icons by type ──────────────────────────────────────
const AGENT_ICONS: Record<string, string> = {
  company_icp_agent:         "🎯",
  signal_detection_agent:    "📡",
  contact_enrichment_agent:  "👤",
  outreach_copy_agent:       "✉️",
  web_research_agent:        "🌐",
  default:                   "⚙️",
};

export type AgentNodeData = {
  agentId: string;
  name: string;
  description: string;
  capabilities: string[];
  status?: "idle" | "running" | "done" | "error";
  selected?: boolean;
};

function AgentNode({ data, selected }: NodeProps) {
  const d = data as AgentNodeData;
  const status = d.status ?? "idle";
  const color  = STATUS_COLORS[status];
  const icon   = AGENT_ICONS[d.agentId] ?? AGENT_ICONS.default;
  const isCore = !d.agentId.includes("custom");

  return (
    <div
      style={{
        minWidth: 220,
        background: "var(--bg-surface, #161b2e)",
        border: `2px solid ${selected ? "#7c3aed" : color}`,
        borderRadius: 14,
        boxShadow: selected
          ? "0 0 0 3px rgba(124,58,237,0.25), 0 8px 24px rgba(0,0,0,0.4)"
          : "0 4px 16px rgba(0,0,0,0.35)",
        padding: "14px 16px",
        fontFamily: "Inter, system-ui, sans-serif",
        transition: "border-color 0.2s, box-shadow 0.2s",
        cursor: "grab",
        userSelect: "none",
      }}
    >
      {/* Input handle — left */}
      <Handle
        type="target"
        position={Position.Left}
        style={{
          width: 12, height: 12,
          background: "#475569",
          border: "2px solid #1e293b",
          left: -6,
        }}
      />

      {/* Header row */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
        {/* Icon circle */}
        <div style={{
          width: 38, height: 38, borderRadius: 10,
          background: "linear-gradient(135deg, rgba(124,58,237,0.25), rgba(59,130,246,0.15))",
          border: "1px solid rgba(124,58,237,0.3)",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 18, flexShrink: 0,
        }}>
          {icon}
        </div>

        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontWeight: 700, fontSize: "0.85rem",
            color: "#f1f5f9",
            whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
          }}>
            {d.name}
          </div>
          {isCore && (
            <div style={{
              fontSize: "0.65rem", fontWeight: 600,
              color: "#7c3aed",
              background: "rgba(124,58,237,0.12)",
              borderRadius: 4, padding: "1px 5px",
              display: "inline-block", marginTop: 2,
            }}>
              CORE
            </div>
          )}
        </div>

        {/* Status indicator */}
        <div style={{
          width: 10, height: 10, borderRadius: "50%",
          background: color,
          boxShadow: status === "running"
            ? `0 0 8px ${color}`
            : status === "done"
            ? `0 0 6px ${color}`
            : "none",
          animation: status === "running" ? "pulse 1s infinite" : "none",
          flexShrink: 0,
        }} />
      </div>

      {/* Description */}
      <div style={{
        fontSize: "0.75rem", color: "#94a3b8", lineHeight: 1.4,
        borderTop: "1px solid rgba(255,255,255,0.06)",
        paddingTop: 8, marginTop: 4,
      }}>
        {d.description.slice(0, 72)}{d.description.length > 72 ? "…" : ""}
      </div>

      {/* Capabilities chips */}
      {d.capabilities?.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 8 }}>
          {d.capabilities.slice(0, 3).map((cap) => (
            <span key={cap} style={{
              fontSize: "0.62rem", fontWeight: 600,
              background: "rgba(59,130,246,0.12)",
              color: "#60a5fa",
              borderRadius: 4, padding: "2px 6px",
              textTransform: "uppercase", letterSpacing: "0.04em",
            }}>
              {cap}
            </span>
          ))}
        </div>
      )}

      {/* Output handle — right */}
      <Handle
        type="source"
        position={Position.Right}
        style={{
          width: 12, height: 12,
          background: "#7c3aed",
          border: "2px solid #1e293b",
          right: -6,
        }}
      />
    </div>
  );
}

export default memo(AgentNode);
