/**
 * DiagnosticsView — Five-tab diagnostics panel.
 *
 * Tabs: Query Tiers | Contradictions | Decisions | Anomalies | Corrections
 * Each tab fetches its endpoint on first activation (lazy load).
 */
import React, { useState, useCallback } from "react";

interface DiagnosticsViewProps {
  httpPort: number;
}

type TabId = "tiers" | "contradictions" | "decisions" | "anomalies" | "corrections";

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

function LoadingRow() {
  return (
    <tr>
      <td colSpan={10} style={{ textAlign: "center", padding: "1rem", color: "var(--text-secondary, #aaa)" }}>
        Loading...
      </td>
    </tr>
  );
}

function ErrorRow({ message }: { message: string }) {
  return (
    <tr>
      <td colSpan={10} style={{ textAlign: "center", padding: "1rem", color: "var(--error, #f87171)" }}>
        {message}
      </td>
    </tr>
  );
}

// ---------------------------------------------------------------------------
// Query Tiers Tab
// ---------------------------------------------------------------------------

interface TierInfo {
  label: string;
  description: string;
}

interface QueryClassifierData {
  tiers: Record<string, TierInfo>;
  classifier: string;
}

function QueryTiersTab({ httpPort }: { httpPort: number }) {
  const [data, setData] = useState<QueryClassifierData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetched, setFetched] = useState(false);

  const fetch_ = useCallback(async () => {
    if (fetched) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`http://127.0.0.1:${httpPort}/api/diagnostics/query-classifier`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
      setFetched(true);
    }
  }, [fetched, httpPort]);

  // Trigger on mount
  React.useEffect(() => { fetch_(); }, [fetch_]);

  const TIER_COLORS: Record<string, string> = {
    TIER_A: "#4ade80",
    TIER_B: "#60a5fa",
    TIER_C: "#f59e0b",
  };

  if (loading) return <p style={{ color: "var(--text-secondary, #aaa)" }}>Loading...</p>;
  if (error) return <p style={{ color: "var(--error, #f87171)" }}>Error: {error}</p>;
  if (!data) return null;

  return (
    <div>
      <p style={{ color: "var(--text-secondary, #aaa)", marginBottom: "1rem", fontSize: "0.85rem" }}>
        Classifier strategy: <strong>{data.classifier}</strong>
      </p>
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        {Object.entries(data.tiers).map(([key, tier]) => (
          <div
            key={key}
            style={{
              border: `1px solid ${TIER_COLORS[key] ?? "#555"}`,
              borderRadius: "8px",
              padding: "1rem 1.5rem",
              minWidth: "220px",
              flex: "1",
              background: "var(--surface, #1e1e2e)",
            }}
          >
            <div style={{ fontWeight: 700, color: TIER_COLORS[key] ?? "#fff", marginBottom: "0.4rem" }}>
              {key}
            </div>
            <div style={{ fontWeight: 600, marginBottom: "0.3rem" }}>{tier.label}</div>
            <div style={{ color: "var(--text-secondary, #aaa)", fontSize: "0.85rem" }}>{tier.description}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Contradictions Tab
// ---------------------------------------------------------------------------

interface ContradictionHealth {
  total: number;
  unresolved: number;
  resolved: number;
  by_type: Record<string, number>;
  most_contradicted_entities: string[];
  error?: string;
}

function ContradictionsTab({ httpPort }: { httpPort: number }) {
  const [data, setData] = useState<ContradictionHealth | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetched, setFetched] = useState(false);

  const fetch_ = useCallback(async () => {
    if (fetched) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`http://127.0.0.1:${httpPort}/api/diagnostics/contradiction-health`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
      setFetched(true);
    }
  }, [fetched, httpPort]);

  React.useEffect(() => { fetch_(); }, [fetch_]);

  if (loading) return <p style={{ color: "var(--text-secondary, #aaa)" }}>Loading...</p>;
  if (error) return <p style={{ color: "var(--error, #f87171)" }}>Error: {error}</p>;
  if (!data) return null;

  const unresolvedColor = (data.unresolved ?? 0) > 0 ? "#f59e0b" : "#4ade80";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {data.error && (
        <p style={{ color: "#f59e0b", fontSize: "0.85rem" }}>Warning: {data.error}</p>
      )}

      {/* Summary counts */}
      <div style={{ display: "flex", gap: "1rem", flexWrap: "wrap" }}>
        {[
          { label: "Total", value: data.total, color: "#60a5fa" },
          { label: "Resolved", value: data.resolved, color: "#4ade80" },
          { label: "Unresolved", value: data.unresolved, color: unresolvedColor },
        ].map(({ label, value, color }) => (
          <div
            key={label}
            style={{
              border: `1px solid ${color}`,
              borderRadius: "8px",
              padding: "0.75rem 1.25rem",
              minWidth: "120px",
              textAlign: "center",
              background: "var(--surface, #1e1e2e)",
            }}
          >
            <div style={{ fontSize: "1.8rem", fontWeight: 700, color }}>{value ?? 0}</div>
            <div style={{ fontSize: "0.8rem", color: "var(--text-secondary, #aaa)" }}>{label}</div>
          </div>
        ))}
      </div>

      {/* By type */}
      {data.by_type && Object.keys(data.by_type).length > 0 && (
        <div>
          <h4 style={{ marginBottom: "0.5rem", fontSize: "0.9rem" }}>By Type</h4>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border, #333)" }}>
                <th style={{ textAlign: "left", padding: "0.4rem 0.6rem" }}>Type</th>
                <th style={{ textAlign: "right", padding: "0.4rem 0.6rem" }}>Count</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.by_type).map(([type, count]) => (
                <tr key={type} style={{ borderBottom: "1px solid var(--border, #222)" }}>
                  <td style={{ padding: "0.4rem 0.6rem" }}>{type}</td>
                  <td style={{ padding: "0.4rem 0.6rem", textAlign: "right" }}>{count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Most contradicted entities */}
      {data.most_contradicted_entities && data.most_contradicted_entities.length > 0 && (
        <div>
          <h4 style={{ marginBottom: "0.5rem", fontSize: "0.9rem" }}>Most Contradicted Entities</h4>
          <ul style={{ paddingLeft: "1.2rem", fontSize: "0.85rem", color: "var(--text-secondary, #aaa)" }}>
            {data.most_contradicted_entities.map((e) => <li key={e}>{e}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Decisions Tab
// ---------------------------------------------------------------------------

interface OpenDecision {
  decision_id: string;
  action_taken: string;
  confidence: number;
  timestamp: number;
}

interface OverconfidenceEntry {
  avg_conf: number;
  avg_outcome: number;
  n: number;
}

interface DecisionMemoryData {
  open_decisions: OpenDecision[];
  overconfidence_profile: Record<string, OverconfidenceEntry>;
  error?: string;
}

function DecisionsTab({ httpPort }: { httpPort: number }) {
  const [data, setData] = useState<DecisionMemoryData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetched, setFetched] = useState(false);

  const fetch_ = useCallback(async () => {
    if (fetched) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`http://127.0.0.1:${httpPort}/api/diagnostics/decision-memory`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
      setFetched(true);
    }
  }, [fetched, httpPort]);

  React.useEffect(() => { fetch_(); }, [fetch_]);

  if (loading) return <p style={{ color: "var(--text-secondary, #aaa)" }}>Loading...</p>;
  if (error) return <p style={{ color: "var(--error, #f87171)" }}>Error: {error}</p>;
  if (!data) return null;

  const formatTs = (ts: number) =>
    ts ? new Date(ts * 1000).toLocaleString() : "-";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {data.error && (
        <p style={{ color: "#f59e0b", fontSize: "0.85rem" }}>Warning: {data.error}</p>
      )}

      <div>
        <h4 style={{ marginBottom: "0.5rem", fontSize: "0.9rem" }}>
          Open Decisions ({data.open_decisions.length})
        </h4>
        {data.open_decisions.length === 0 ? (
          <p style={{ color: "var(--text-secondary, #aaa)", fontSize: "0.85rem" }}>No open decisions.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border, #333)" }}>
                <th style={{ textAlign: "left", padding: "0.4rem 0.6rem" }}>ID</th>
                <th style={{ textAlign: "left", padding: "0.4rem 0.6rem" }}>Action</th>
                <th style={{ textAlign: "right", padding: "0.4rem 0.6rem" }}>Confidence</th>
                <th style={{ textAlign: "right", padding: "0.4rem 0.6rem" }}>Timestamp</th>
              </tr>
            </thead>
            <tbody>
              {data.open_decisions.map((d) => (
                <tr key={d.decision_id} style={{ borderBottom: "1px solid var(--border, #222)" }}>
                  <td style={{ padding: "0.4rem 0.6rem", fontFamily: "monospace", fontSize: "0.72rem", color: "var(--text-secondary, #aaa)" }}>
                    {d.decision_id.slice(0, 8)}...
                  </td>
                  <td style={{ padding: "0.4rem 0.6rem", maxWidth: "260px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {d.action_taken}
                  </td>
                  <td style={{ padding: "0.4rem 0.6rem", textAlign: "right" }}>
                    {(d.confidence * 100).toFixed(0)}%
                  </td>
                  <td style={{ padding: "0.4rem 0.6rem", textAlign: "right", color: "var(--text-secondary, #aaa)" }}>
                    {formatTs(d.timestamp)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div>
        <h4 style={{ marginBottom: "0.5rem", fontSize: "0.9rem" }}>Overconfidence Profile</h4>
        {Object.keys(data.overconfidence_profile).length === 0 ? (
          <p style={{ color: "var(--text-secondary, #aaa)", fontSize: "0.85rem" }}>No overconfidence patterns detected.</p>
        ) : (
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
            <thead>
              <tr style={{ borderBottom: "1px solid var(--border, #333)" }}>
                <th style={{ textAlign: "left", padding: "0.4rem 0.6rem" }}>Action Type</th>
                <th style={{ textAlign: "right", padding: "0.4rem 0.6rem" }}>Avg Confidence</th>
                <th style={{ textAlign: "right", padding: "0.4rem 0.6rem" }}>Avg Outcome</th>
                <th style={{ textAlign: "right", padding: "0.4rem 0.6rem" }}>Count</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.overconfidence_profile).map(([action, stats]) => (
                <tr key={action} style={{ borderBottom: "1px solid var(--border, #222)" }}>
                  <td style={{ padding: "0.4rem 0.6rem" }}>{action}</td>
                  <td style={{ padding: "0.4rem 0.6rem", textAlign: "right", color: "#f59e0b" }}>
                    {(stats.avg_conf * 100).toFixed(1)}%
                  </td>
                  <td style={{ padding: "0.4rem 0.6rem", textAlign: "right", color: "#f87171" }}>
                    {stats.avg_outcome.toFixed(2)}
                  </td>
                  <td style={{ padding: "0.4rem 0.6rem", textAlign: "right" }}>{stats.n}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Anomalies Tab
// ---------------------------------------------------------------------------

interface AnomalyDomain {
  domain: string;
  description: string;
  active: boolean;
}

interface AnomalyDomainsData {
  domains: AnomalyDomain[];
  error?: string;
}

function AnomaliesTab({ httpPort }: { httpPort: number }) {
  const [data, setData] = useState<AnomalyDomainsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetched, setFetched] = useState(false);

  const fetch_ = useCallback(async () => {
    if (fetched) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`http://127.0.0.1:${httpPort}/api/diagnostics/anomaly-domains`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
      setFetched(true);
    }
  }, [fetched, httpPort]);

  React.useEffect(() => { fetch_(); }, [fetch_]);

  if (loading) return <p style={{ color: "var(--text-secondary, #aaa)" }}>Loading...</p>;
  if (error) return <p style={{ color: "var(--error, #f87171)" }}>Error: {error}</p>;
  if (!data) return null;

  return (
    <div>
      {data.error && (
        <p style={{ color: "#f59e0b", fontSize: "0.85rem", marginBottom: "0.75rem" }}>Warning: {data.error}</p>
      )}
      <h4 style={{ marginBottom: "0.5rem", fontSize: "0.9rem" }}>
        Monitored Domains ({data.domains.length})
      </h4>
      {data.domains.length === 0 ? (
        <p style={{ color: "var(--text-secondary, #aaa)", fontSize: "0.85rem" }}>No anomaly domains registered.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border, #333)" }}>
              <th style={{ textAlign: "left", padding: "0.4rem 0.6rem" }}>Domain</th>
              <th style={{ textAlign: "left", padding: "0.4rem 0.6rem" }}>Description</th>
              <th style={{ textAlign: "center", padding: "0.4rem 0.6rem" }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {data.domains.map((d) => (
              <tr key={d.domain} style={{ borderBottom: "1px solid var(--border, #222)" }}>
                <td style={{ padding: "0.4rem 0.6rem", fontWeight: 600 }}>{d.domain}</td>
                <td style={{ padding: "0.4rem 0.6rem", color: "var(--text-secondary, #aaa)", fontSize: "0.8rem" }}>
                  {d.description || "-"}
                </td>
                <td style={{ padding: "0.4rem 0.6rem", textAlign: "center" }}>
                  <span style={{ color: d.active ? "#4ade80" : "#6b7280", fontSize: "0.78rem" }}>
                    {d.active ? "Active" : "Inactive"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Corrections Tab
// ---------------------------------------------------------------------------

interface CorrectionRecord {
  id: number;
  task_type: string;
  wrong_approach: string;
  correct_approach: string;
  session_id: string;
  timestamp: number;
}

interface SkillCorrectionsData {
  corrections: CorrectionRecord[];
  error?: string;
}

function CorrectionsTab({ httpPort }: { httpPort: number }) {
  const [data, setData] = useState<SkillCorrectionsData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fetched, setFetched] = useState(false);

  const fetch_ = useCallback(async () => {
    if (fetched) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`http://127.0.0.1:${httpPort}/api/diagnostics/skill-corrections`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setData(await r.json());
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
      setFetched(true);
    }
  }, [fetched, httpPort]);

  React.useEffect(() => { fetch_(); }, [fetch_]);

  if (loading) return <p style={{ color: "var(--text-secondary, #aaa)" }}>Loading...</p>;
  if (error) return <p style={{ color: "var(--error, #f87171)" }}>Error: {error}</p>;
  if (!data) return null;

  const formatTs = (ts: number) =>
    ts ? new Date(ts * 1000).toLocaleString() : "-";

  return (
    <div>
      {data.error && (
        <p style={{ color: "#f59e0b", fontSize: "0.85rem", marginBottom: "0.75rem" }}>Warning: {data.error}</p>
      )}
      <h4 style={{ marginBottom: "0.5rem", fontSize: "0.9rem" }}>
        Recent Corrections ({data.corrections.length})
      </h4>
      {data.corrections.length === 0 ? (
        <p style={{ color: "var(--text-secondary, #aaa)", fontSize: "0.85rem" }}>No corrections yet.</p>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.8rem" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--border, #333)" }}>
              <th style={{ textAlign: "left", padding: "0.4rem 0.6rem" }}>ID</th>
              <th style={{ textAlign: "left", padding: "0.4rem 0.6rem" }}>Task Type</th>
              <th style={{ textAlign: "left", padding: "0.4rem 0.6rem" }}>Wrong Approach</th>
              <th style={{ textAlign: "left", padding: "0.4rem 0.6rem" }}>Correct Approach</th>
              <th style={{ textAlign: "right", padding: "0.4rem 0.6rem" }}>When</th>
            </tr>
          </thead>
          <tbody>
            {data.corrections.map((c) => (
              <tr key={c.id} style={{ borderBottom: "1px solid var(--border, #222)" }}>
                <td style={{ padding: "0.4rem 0.6rem", color: "var(--text-secondary, #aaa)" }}>{c.id}</td>
                <td style={{ padding: "0.4rem 0.6rem" }}>{c.task_type}</td>
                <td style={{ padding: "0.4rem 0.6rem", maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "#f87171" }}>
                  {c.wrong_approach}
                </td>
                <td style={{ padding: "0.4rem 0.6rem", maxWidth: "200px", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "#4ade80" }}>
                  {c.correct_approach}
                </td>
                <td style={{ padding: "0.4rem 0.6rem", textAlign: "right", color: "var(--text-secondary, #aaa)", whiteSpace: "nowrap" }}>
                  {formatTs(c.timestamp)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main DiagnosticsView
// ---------------------------------------------------------------------------

const TABS: { id: TabId; label: string }[] = [
  { id: "tiers",          label: "Query Tiers" },
  { id: "contradictions", label: "Contradictions" },
  { id: "decisions",      label: "Decisions" },
  { id: "anomalies",      label: "Anomalies" },
  { id: "corrections",    label: "Corrections" },
];

export function DiagnosticsView({ httpPort }: DiagnosticsViewProps) {
  const [activeTab, setActiveTab] = useState<TabId>("tiers");

  const tabContentStyle: React.CSSProperties = {
    padding: "1.25rem",
    background: "var(--surface, #1e1e2e)",
    borderRadius: "0 0 8px 8px",
    border: "1px solid var(--border, #333)",
    borderTop: "none",
    minHeight: "300px",
  };

  return (
    <div style={{ padding: "1.5rem" }}>
      <h2 style={{ marginBottom: "1.25rem", fontSize: "1.1rem", fontWeight: 700 }}>
        Diagnostics
      </h2>

      {/* Tab bar */}
      <div style={{ display: "flex", borderBottom: "1px solid var(--border, #333)", marginBottom: "0" }}>
        {TABS.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: "0.55rem 1rem",
                background: "transparent",
                border: "none",
                borderBottom: isActive ? "2px solid #60a5fa" : "2px solid transparent",
                color: isActive ? "#60a5fa" : "var(--text-secondary, #aaa)",
                fontWeight: isActive ? 700 : 400,
                fontSize: "0.85rem",
                cursor: "pointer",
                transition: "color 0.15s",
              }}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Tab content — always mounted so lazy fetch fires on first activation */}
      <div style={tabContentStyle}>
        {activeTab === "tiers"          && <QueryTiersTab      httpPort={httpPort} />}
        {activeTab === "contradictions" && <ContradictionsTab  httpPort={httpPort} />}
        {activeTab === "decisions"      && <DecisionsTab       httpPort={httpPort} />}
        {activeTab === "anomalies"      && <AnomaliesTab       httpPort={httpPort} />}
        {activeTab === "corrections"    && <CorrectionsTab     httpPort={httpPort} />}
      </div>
    </div>
  );
}

export default DiagnosticsView;
