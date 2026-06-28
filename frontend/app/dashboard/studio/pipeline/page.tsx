"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Edge,
  type Node,
  type ReactFlowInstance,
  BackgroundVariant,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import AgentNode, { type AgentNodeData } from "../components/AgentNode";
import AgentPalette from "../components/AgentPalette";
import Link from "next/link";

// ── types ────────────────────────────────────────────────────
type Agent = {
  agent_id: string;
  name: string;
  description: string;
  capabilities: string[];
  icon: string;
  is_core: boolean;
  required_inputs: string[];
  outputs: string[];
};

type WorkflowPlan = {
  intent_summary: string;
  recommended_agents: string[];
  icp_config_extracted: Record<string, string>;
};

// ── ReactFlow node types ─────────────────────────────────────
const NODE_TYPES = { agent: AgentNode };

// ── helpers ──────────────────────────────────────────────────
function getToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem("xlventures-auth");
    if (!raw) return null;
    return JSON.parse(raw)?.state?.token ?? null;
  } catch { return null; }
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Topological sort (Kahn's algorithm)
function topoSort(nodes: Node[], edges: Edge[]): string[] {
  const inDegree: Record<string, number> = {};
  const adj: Record<string, string[]> = {};
  nodes.forEach(n => { inDegree[n.id] = 0; adj[n.id] = []; });
  edges.forEach(e => {
    adj[e.source].push(e.target);
    inDegree[e.target] = (inDegree[e.target] ?? 0) + 1;
  });
  const queue = nodes.filter(n => inDegree[n.id] === 0).map(n => n.id);
  const result: string[] = [];
  while (queue.length) {
    const cur = queue.shift()!;
    result.push(cur);
    adj[cur].forEach(nxt => {
      inDegree[nxt]--;
      if (inDegree[nxt] === 0) queue.push(nxt);
    });
  }
  return result;
}

// ── Main page ────────────────────────────────────────────────
export default function PipelinePage() {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [rfInstance, setRfInstance] = useState<ReactFlowInstance | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [pipelineName, setPipelineName] = useState("My Pipeline");
  const [prompt, setPrompt] = useState("");
  const [showPrompt, setShowPrompt] = useState(false);
  const [running, setRunning] = useState(false);
  const [nodeStatuses, setNodeStatuses] = useState<Record<string, string>>({});
  const [runError, setRunError] = useState("");
  const [runId, setRunId] = useState<string | null>(null);
  const nodeIdRef = useRef(0);

  // Load agents
  useEffect(() => {
    fetch(`${API}/studio/agents`, { headers: authHeaders() })
      .then(r => r.json())
      .then(setAgents)
      .catch(console.error);
  }, []);

  // Sync node statuses into node data
  useEffect(() => {
    if (!Object.keys(nodeStatuses).length) return;
    setNodes(nds => nds.map(n => ({
      ...n,
      data: { ...n.data, status: nodeStatuses[n.id] ?? n.data.status },
    })));
  }, [nodeStatuses, setNodes]);

  // SSE listener when pipeline is running
  useEffect(() => {
    if (!runId) return;
    const token = getToken();
    const url = `${API}/api/v1/stream/${runId}`;
    const src = new EventSource(token ? `${url}?token=${token}` : url);
    src.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data);
        if (data.agent_id && data.status) {
          setNodeStatuses(prev => ({ ...prev, [data.agent_id]: data.status }));
        }
        if (data.status === "completed" || data.status === "failed") {
          setRunning(false);
          src.close();
        }
      } catch { /* ignore */ }
    };
    src.onerror = () => { src.close(); setRunning(false); };
    return () => src.close();
  }, [runId]);

  // ── Callbacks ─────────────────────────────────────────────
  const onConnect = useCallback((params: Connection) => {
    setEdges(eds => addEdge({
      ...params,
      animated: true,
      markerEnd: { type: MarkerType.ArrowClosed, color: "#7c3aed" },
      style: { stroke: "#7c3aed", strokeWidth: 2 },
    }, eds));
  }, [setEdges]);

  // Drag-and-drop from palette
  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    if (!rfInstance) return;
    const raw = e.dataTransfer.getData("application/agent");
    if (!raw) return;
    const agent: Agent = JSON.parse(raw);
    const pos = rfInstance.screenToFlowPosition({ x: e.clientX - 240, y: e.clientY - 60 });
    spawnNode(agent, pos);
  }, [rfInstance, agents]); // eslint-disable-line

  const onDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
  };

  function spawnNode(agent: Agent, position = { x: 200 + nodeIdRef.current * 260, y: 160 }) {
    nodeIdRef.current += 1;
    const id = `${agent.agent_id}-${nodeIdRef.current}`;
    const newNode: Node = {
      id,
      type: "agent",
      position,
      data: {
        agentId: agent.agent_id,
        name: agent.name,
        description: agent.description,
        capabilities: agent.capabilities,
        status: "idle",
      } as AgentNodeData,
    };
    setNodes(nds => [...nds, newNode]);
    return id;
  }

  // Auto-connect agents in sequence
  function autoConnect(nodeIds: string[]) {
    const newEdges: Edge[] = [];
    for (let i = 0; i < nodeIds.length - 1; i++) {
      newEdges.push({
        id: `e-${nodeIds[i]}-${nodeIds[i + 1]}`,
        source: nodeIds[i],
        target: nodeIds[i + 1],
        animated: true,
        markerEnd: { type: MarkerType.ArrowClosed, color: "#7c3aed" },
        style: { stroke: "#7c3aed", strokeWidth: 2 },
      });
    }
    setEdges(eds => [...eds, ...newEdges]);
  }

  // Generate from prompt
  const handleGenerateFromPrompt = async () => {
    if (!prompt.trim()) return;
    setRunning(true);
    setRunError("");
    try {
      const res = await fetch(`${API}/studio/parse-intent`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ prompt, context: {} }),
      });
      const plan: WorkflowPlan = await res.json();

      // Clear canvas and place recommended agents
      setNodes([]);
      setEdges([]);
      nodeIdRef.current = 0;

      const spawnedIds: string[] = [];
      for (let i = 0; i < plan.recommended_agents.length; i++) {
        const agentId = plan.recommended_agents[i];
        const agentDef = agents.find(a => a.agent_id === agentId);
        if (!agentDef) continue;
        const id = spawnNode(agentDef, { x: 80 + i * 280, y: 180 });
        spawnedIds.push(id);
      }

      // Auto-wire in sequence after a tick (so nodes are in state)
      setTimeout(() => autoConnect(spawnedIds), 50);
      setPipelineName(plan.intent_summary.slice(0, 40) || "Generated Pipeline");
      setShowPrompt(false);
    } catch (err) {
      setRunError("Failed to parse prompt");
    } finally {
      setRunning(false);
    }
  };

  // Run pipeline
  const handleRunPipeline = async () => {
    if (!nodes.length) { setRunError("Add at least one agent to the canvas first."); return; }
    setRunning(true);
    setRunError("");

    // Mark all nodes as idle again
    setNodeStatuses({});
    setNodes(nds => nds.map(n => ({ ...n, data: { ...n.data, status: "idle" } })));

    // Topological order
    const orderedIds = topoSort(nodes, edges);
    const agentIds = orderedIds
      .map(id => nodes.find(n => n.id === id)?.data?.agentId as string)
      .filter(Boolean);

    try {
      // First create an ICP config to associate with the run
      const icpRes = await fetch(`${API}/api/v1/icp`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          name: pipelineName,
          rules_json: { pipeline: agentIds },
          persona_json: {},
        }),
      });
      if (!icpRes.ok) throw new Error(await icpRes.text());
      const icp = await icpRes.json();

      // Execute via studio endpoint
      const execRes = await fetch(`${API}/studio/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          workflow_plan: {
            intent_summary: pipelineName,
            recommended_agents: agentIds,
            icp_config_extracted: {},
            suggested_steps: agentIds.map(id => `Run ${id}`),
          },
          selected_agent_ids: agentIds,
          max_companies: 5,
          icp_config_id: icp.id,
        }),
      });
      if (!execRes.ok) throw new Error(await execRes.text());
      const exec = await execRes.json();
      setRunId(exec.run_id ?? exec.id);

      // Mark first node as running
      if (orderedIds[0]) {
        setNodeStatuses({ [orderedIds[0]]: "running" });
      }
    } catch (err) {
      setRunError(String(err));
      setRunning(false);
    }
  };

  // Clear canvas
  const handleClear = () => {
    setNodes([]);
    setEdges([]);
    setRunId(null);
    setRunError("");
    setNodeStatuses({});
    nodeIdRef.current = 0;
  };

  // ── Render ────────────────────────────────────────────────
  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 0px)", position: "fixed", inset: 0, left: 230, zIndex: 5 }}>

      {/* ── Top Toolbar ── */}
      <div style={{
        height: 58,
        background: "var(--bg-surface, #161b2e)",
        borderBottom: "1px solid rgba(255,255,255,0.07)",
        display: "flex",
        alignItems: "center",
        padding: "0 1.25rem",
        gap: "0.75rem",
        flexShrink: 0,
        zIndex: 10,
      }}>
        {/* Back */}
        <Link href="/dashboard/studio" style={{ color: "#64748b", textDecoration: "none", fontSize: "0.8rem", display: "flex", alignItems: "center", gap: 4 }}>
          ← Studio
        </Link>
        <div style={{ width: 1, height: 20, background: "rgba(255,255,255,0.1)" }} />

        {/* Pipeline name */}
        <input
          value={pipelineName}
          onChange={e => setPipelineName(e.target.value)}
          style={{
            background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 8, padding: "0.3rem 0.75rem", color: "#f1f5f9",
            fontSize: "0.85rem", fontWeight: 600, width: 220, outline: "none",
          }}
        />

        <div style={{ flex: 1 }} />

        {/* From Prompt */}
        <button
          onClick={() => setShowPrompt(p => !p)}
          style={{
            padding: "0.4rem 0.9rem", borderRadius: 8, fontSize: "0.8rem",
            background: showPrompt ? "rgba(124,58,237,0.2)" : "rgba(255,255,255,0.05)",
            border: `1px solid ${showPrompt ? "rgba(124,58,237,0.4)" : "rgba(255,255,255,0.1)"}`,
            color: showPrompt ? "#a78bfa" : "#94a3b8", cursor: "pointer",
            display: "flex", alignItems: "center", gap: 6,
          }}
        >
          ✨ From Prompt
        </button>

        {/* Clear */}
        <button
          onClick={handleClear}
          style={{
            padding: "0.4rem 0.9rem", borderRadius: 8, fontSize: "0.8rem",
            background: "rgba(255,255,255,0.05)", border: "1px solid rgba(255,255,255,0.1)",
            color: "#94a3b8", cursor: "pointer",
          }}
        >
          Clear
        </button>

        {/* Run */}
        <button
          onClick={handleRunPipeline}
          disabled={running || !nodes.length}
          style={{
            padding: "0.4rem 1.1rem", borderRadius: 8, fontSize: "0.85rem", fontWeight: 700,
            background: running
              ? "rgba(124,58,237,0.3)"
              : "linear-gradient(135deg, #7c3aed, #3b82f6)",
            border: "none", color: "white", cursor: running ? "not-allowed" : "pointer",
            display: "flex", alignItems: "center", gap: 6,
            boxShadow: !running && nodes.length ? "0 2px 12px rgba(124,58,237,0.4)" : "none",
            transition: "all 0.2s",
            opacity: !nodes.length ? 0.5 : 1,
          }}
        >
          {running ? (
            <><span style={{ animation: "spin 1s linear infinite", display: "inline-block" }}>⟳</span> Running…</>
          ) : (
            <>▶ Run Pipeline</>
          )}
        </button>
      </div>

      {/* ── Prompt overlay ── */}
      {showPrompt && (
        <div style={{
          position: "absolute", top: 58, left: 240, right: 0, zIndex: 20,
          background: "rgba(11,15,30,0.97)",
          borderBottom: "1px solid rgba(124,58,237,0.3)",
          padding: "1rem 1.5rem",
          display: "flex", gap: "0.75rem", alignItems: "flex-start",
        }}>
          <textarea
            value={prompt}
            onChange={e => setPrompt(e.target.value)}
            placeholder="E.g. Find Series B SaaS companies hiring engineers, then enrich their VP contacts..."
            rows={2}
            style={{
              flex: 1, background: "rgba(255,255,255,0.05)", border: "1px solid rgba(124,58,237,0.3)",
              borderRadius: 10, padding: "0.6rem 0.875rem", color: "#f1f5f9",
              fontSize: "0.875rem", fontFamily: "inherit", resize: "none", outline: "none",
            }}
          />
          <button
            onClick={handleGenerateFromPrompt}
            disabled={running || !prompt.trim()}
            style={{
              padding: "0.6rem 1.25rem", borderRadius: 10, fontSize: "0.875rem", fontWeight: 700,
              background: "linear-gradient(135deg, #7c3aed, #3b82f6)",
              border: "none", color: "white", cursor: "pointer", whiteSpace: "nowrap",
              opacity: !prompt.trim() ? 0.5 : 1,
            }}
          >
            {running ? "Generating…" : "✨ Generate"}
          </button>
        </div>
      )}

      {/* ── Main area: palette + canvas ── */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>

        {/* Palette */}
        <AgentPalette
          agents={agents}
          onAddAgent={(agent) => spawnNode(agent)}
        />

        {/* Canvas */}
        <div style={{ flex: 1, position: "relative" }}>
          {runError && (
            <div style={{
              position: "absolute", top: 12, left: "50%", transform: "translateX(-50%)",
              background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.4)",
              borderRadius: 10, padding: "0.5rem 1.25rem", zIndex: 15,
              color: "#fca5a5", fontSize: "0.85rem",
            }}>
              {runError}
              <button onClick={() => setRunError("")} style={{ marginLeft: 10, background: "none", border: "none", color: "#fca5a5", cursor: "pointer" }}>×</button>
            </div>
          )}

          {nodes.length === 0 && (
            <div style={{
              position: "absolute", inset: 0, display: "flex", flexDirection: "column",
              alignItems: "center", justifyContent: "center", zIndex: 1, pointerEvents: "none",
            }}>
              <div style={{ fontSize: "3rem", marginBottom: "1rem", opacity: 0.3 }}>🔗</div>
              <div style={{ color: "#475569", fontSize: "1rem", fontWeight: 600, marginBottom: "0.5rem" }}>
                Your canvas is empty
              </div>
              <div style={{ color: "#334155", fontSize: "0.85rem" }}>
                Drag agents from the palette · or use ✨ From Prompt
              </div>
            </div>
          )}

          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onInit={setRfInstance}
            onDrop={onDrop}
            onDragOver={onDragOver}
            nodeTypes={NODE_TYPES}
            fitView
            deleteKeyCode="Delete"
            style={{ background: "transparent" }}
            defaultEdgeOptions={{
              animated: true,
              markerEnd: { type: MarkerType.ArrowClosed, color: "#7c3aed" },
              style: { stroke: "#7c3aed", strokeWidth: 2 },
            }}
          >
            <Background
              variant={BackgroundVariant.Dots}
              color="rgba(255,255,255,0.06)"
              gap={24}
              size={1.5}
            />
            <Controls
              style={{
                background: "rgba(22,27,46,0.9)",
                border: "1px solid rgba(255,255,255,0.1)",
                borderRadius: 10,
              }}
            />
            <MiniMap
              nodeColor={() => "#7c3aed"}
              maskColor="rgba(0,0,0,0.7)"
              style={{
                background: "rgba(22,27,46,0.95)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 10,
              }}
            />
          </ReactFlow>
        </div>
      </div>

      {/* ── Inline styles for animations ── */}
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
        .react-flow__controls button {
          background: rgba(22,27,46,0.9) !important;
          border-color: rgba(255,255,255,0.1) !important;
          color: #94a3b8 !important;
        }
        .react-flow__controls button:hover {
          background: rgba(124,58,237,0.2) !important;
        }
        .react-flow__edge-path { stroke: #7c3aed !important; }
      `}</style>
    </div>
  );
}
