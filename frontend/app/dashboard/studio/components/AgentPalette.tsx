"use client";

import { useState } from "react";

type Agent = {
  agent_id: string;
  name: string;
  description: string;
  capabilities: string[];
  icon: string;
  is_core: boolean;
};

type AgentPaletteProps = {
  agents: Agent[];
  onAddAgent: (agent: Agent) => void;
};

const AGENT_ICONS: Record<string, string> = {
  company_icp_agent:         "🎯",
  signal_detection_agent:    "📡",
  contact_enrichment_agent:  "👤",
  outreach_copy_agent:       "✉️",
  web_research_agent:        "🌐",
  default:                   "⚙️",
};

export default function AgentPalette({ agents, onAddAgent }: AgentPaletteProps) {
  const [search, setSearch] = useState("");

  const filtered = agents.filter(a =>
    a.name.toLowerCase().includes(search.toLowerCase()) ||
    a.description.toLowerCase().includes(search.toLowerCase())
  );

  const coreAgents   = filtered.filter(a => a.is_core);
  const customAgents = filtered.filter(a => !a.is_core);

  const handleDragStart = (e: React.DragEvent, agent: Agent) => {
    e.dataTransfer.setData("application/agent", JSON.stringify(agent));
    e.dataTransfer.effectAllowed = "copy";
  };

  return (
    <div style={{
      width: 240,
      height: "100%",
      background: "var(--bg-surface, #161b2e)",
      borderRight: "1px solid rgba(255,255,255,0.07)",
      display: "flex",
      flexDirection: "column",
      flexShrink: 0,
      overflow: "hidden",
    }}>
      {/* Header */}
      <div style={{ padding: "1rem 1rem 0.5rem" }}>
        <div style={{ fontWeight: 700, fontSize: "0.8rem", color: "#94a3b8", letterSpacing: "0.08em", textTransform: "uppercase", marginBottom: "0.75rem" }}>
          Agent Palette
        </div>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search agents..."
          style={{
            width: "100%",
            padding: "0.5rem 0.75rem",
            background: "rgba(255,255,255,0.05)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 8,
            color: "#f1f5f9",
            fontSize: "0.8rem",
            outline: "none",
            boxSizing: "border-box",
          }}
        />
      </div>

      {/* Agent list */}
      <div style={{ flex: 1, overflowY: "auto", padding: "0.5rem 0.75rem 1rem" }}>

        {/* Core agents section */}
        {coreAgents.length > 0 && (
          <>
            <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "#7c3aed", letterSpacing: "0.08em", textTransform: "uppercase", margin: "0.75rem 0 0.4rem 0.25rem" }}>
              Core Agents
            </div>
            {coreAgents.map(agent => (
              <PaletteCard key={agent.agent_id} agent={agent} onDragStart={handleDragStart} onAdd={onAddAgent} />
            ))}
          </>
        )}

        {/* Custom agents section */}
        {customAgents.length > 0 && (
          <>
            <div style={{ fontSize: "0.65rem", fontWeight: 700, color: "#3b82f6", letterSpacing: "0.08em", textTransform: "uppercase", margin: "0.75rem 0 0.4rem 0.25rem" }}>
              Custom Agents
            </div>
            {customAgents.map(agent => (
              <PaletteCard key={agent.agent_id} agent={agent} onDragStart={handleDragStart} onAdd={onAddAgent} />
            ))}
          </>
        )}

        {filtered.length === 0 && (
          <div style={{ color: "#64748b", fontSize: "0.8rem", textAlign: "center", marginTop: "2rem" }}>
            No agents found
          </div>
        )}
      </div>

      {/* Tip */}
      <div style={{ padding: "0.75rem 1rem", borderTop: "1px solid rgba(255,255,255,0.06)", fontSize: "0.72rem", color: "#475569" }}>
        💡 Drag to canvas or click + to add
      </div>
    </div>
  );
}

function PaletteCard({ agent, onDragStart, onAdd }: { agent: Agent; onDragStart: (e: React.DragEvent, a: Agent) => void; onAdd: (a: Agent) => void }) {
  const icon = AGENT_ICONS[agent.agent_id] ?? AGENT_ICONS.default;
  const [hovered, setHovered] = useState(false);

  return (
    <div
      draggable
      onDragStart={e => onDragStart(e, agent)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "0.6rem 0.75rem",
        borderRadius: 10,
        marginBottom: 4,
        background: hovered ? "rgba(124,58,237,0.1)" : "transparent",
        border: `1px solid ${hovered ? "rgba(124,58,237,0.25)" : "transparent"}`,
        cursor: "grab",
        transition: "all 0.15s",
      }}
    >
      <div style={{
        width: 32, height: 32, borderRadius: 8,
        background: "rgba(124,58,237,0.15)",
        display: "flex", alignItems: "center", justifyContent: "center",
        fontSize: 15, flexShrink: 0,
      }}>
        {icon}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: "0.78rem", color: "#e2e8f0", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {agent.name}
        </div>
        <div style={{ fontSize: "0.68rem", color: "#64748b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
          {agent.description.slice(0, 40)}…
        </div>
      </div>
      <button
        onClick={() => onAdd(agent)}
        style={{
          width: 24, height: 24, borderRadius: 6,
          background: hovered ? "rgba(124,58,237,0.3)" : "rgba(255,255,255,0.05)",
          border: "1px solid rgba(255,255,255,0.1)",
          color: "#a78bfa",
          fontWeight: 700, fontSize: "1rem",
          cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0, lineHeight: 1,
          transition: "all 0.15s",
        }}
        title={`Add ${agent.name}`}
      >
        +
      </button>
    </div>
  );
}
