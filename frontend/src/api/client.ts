import type { DataSource, Graph, GraphEdge, GraphResponse } from "./types";

const BASE = "http://127.0.0.1:8765";

export interface ApiKeyStatus {
  set: boolean;
  source: "env" | "user" | null;
}

export interface SetApiKeyResult extends ApiKeyStatus {
  persisted_path: string | null;
  persist_error: string | null;
  validated: boolean;
  validation_error: string | null;
}

export interface ClearApiKeyResult {
  set: false;
  source: null;
  removed_from: string | null;
}

export async function getApiKeyStatus(): Promise<ApiKeyStatus> {
  const r = await fetch(`${BASE}/api-key`);
  if (!r.ok) throw new Error(`api-key status failed: ${r.status}`);
  return r.json();
}

export async function setApiKey(key: string): Promise<SetApiKeyResult> {
  const r = await fetch(`${BASE}/api-key`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ key }),
  });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`set key failed: ${r.status} ${text}`);
  }
  return r.json();
}

export async function clearApiKey(): Promise<ClearApiKeyResult> {
  const r = await fetch(`${BASE}/api-key`, { method: "DELETE" });
  if (!r.ok) throw new Error(`clear key failed: ${r.status}`);
  return r.json();
}

export interface PersistedActiveSource {
  id: string;
  label: string;
  kind: "synthetic" | "csv" | "sigma";
  columns: string[];
  rows: number;
}

export async function fetchAppState(): Promise<{
  active_source: PersistedActiveSource | null;
}> {
  const r = await fetch(`${BASE}/state`);
  if (!r.ok) throw new Error(`state failed: ${r.status}`);
  return r.json();
}

export async function fetchSyntheticGraph(): Promise<GraphResponse> {
  const r = await fetch(`${BASE}/graph/synthetic`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!r.ok) throw new Error(`graph fetch failed: ${r.status}`);
  return r.json();
}

export async function listSources(): Promise<DataSource[]> {
  const r = await fetch(`${BASE}/sources`);
  if (!r.ok) throw new Error(`list sources failed: ${r.status}`);
  const d = (await r.json()) as { sources: DataSource[] };
  return d.sources;
}

export async function uploadCsv(file: File): Promise<DataSource> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${BASE}/sources/csv/upload`, {
    method: "POST",
    body: fd,
  });
  if (!r.ok) throw new Error(`upload failed: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function deleteSource(id: string): Promise<void> {
  const r = await fetch(`${BASE}/sources/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(`delete failed: ${r.status}`);
}

export async function graphFromSource(
  sourceId: string,
  columns: string[],
): Promise<{ graph: Graph; n_rows_used: number }> {
  const r = await fetch(`${BASE}/graph/from-source`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ source_id: sourceId, columns }),
  });
  if (!r.ok) throw new Error(`graph from source failed: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function setOverride(
  sourceId: string,
  varA: string,
  varB: string,
  directionFrom: string | null,
): Promise<void> {
  const r = await fetch(`${BASE}/overrides`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      source_id: sourceId,
      var_a: varA,
      var_b: varB,
      direction_from: directionFrom,
    }),
  });
  if (!r.ok) throw new Error(`set override failed: ${r.status} ${await r.text()}`);
}

export async function sigmaStatus(): Promise<{ connected: boolean }> {
  const r = await fetch(`${BASE}/sigma/status`);
  if (!r.ok) throw new Error(`sigma status failed: ${r.status}`);
  return r.json();
}

export async function sigmaConnect(): Promise<{ connected: boolean; user?: { name?: string; email?: string } }> {
  const r = await fetch(`${BASE}/sigma/connect`, { method: "POST" });
  if (!r.ok) throw new Error(`sigma connect failed: ${r.status} ${await r.text().catch(() => "")}`);
  return r.json();
}

export async function sigmaDisconnect(): Promise<void> {
  const r = await fetch(`${BASE}/sigma/disconnect`, { method: "POST" });
  if (!r.ok) throw new Error(`sigma disconnect failed: ${r.status}`);
}

export interface SigmaConfig {
  mcp_url: string;
  connected: boolean;
}

export async function sigmaConfig(): Promise<SigmaConfig> {
  const r = await fetch(`${BASE}/sigma/config`);
  if (!r.ok) throw new Error(`sigma config fetch failed: ${r.status}`);
  return r.json();
}

export async function sigmaSetConfig(mcpUrl: string): Promise<SigmaConfig> {
  const r = await fetch(`${BASE}/sigma/config`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ mcp_url: mcpUrl }),
  });
  if (!r.ok) {
    const text = await r.text().catch(() => "");
    throw new Error(`sigma config save failed: ${r.status} ${text}`);
  }
  return r.json();
}

export type SigmaPolicy = "allow_always" | "ask_always";

export interface SigmaTool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
  policy: SigmaPolicy;
}

export async function sigmaTools(): Promise<{
  tools: SigmaTool[];
  default_policy: SigmaPolicy;
}> {
  const r = await fetch(`${BASE}/sigma/tools`);
  if (!r.ok)
    throw new Error(`sigma tools failed: ${r.status} ${await r.text().catch(() => "")}`);
  return r.json();
}

export async function sigmaSetPermissions(
  policies: Record<string, SigmaPolicy>,
): Promise<{ policies: Record<string, SigmaPolicy>; default_policy: SigmaPolicy }> {
  const r = await fetch(`${BASE}/sigma/permissions`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ policies }),
  });
  if (!r.ok) throw new Error(`set permissions failed: ${r.status}`);
  return r.json();
}

export interface SigmaDocEntry {
  type: "workbook" | "dataModel" | "table" | "dataModelElement";
  inodeId: string;
  name: string;
  description?: string | null;
}

export async function sigmaDocuments(collection: string): Promise<SigmaDocEntry[]> {
  const r = await fetch(`${BASE}/sigma/documents?collection=${encodeURIComponent(collection)}&limit=20`);
  if (!r.ok) throw new Error(`sigma documents failed: ${r.status}`);
  const d = (await r.json()) as { result: unknown };
  return parseDocList(d.result);
}

function parseDocList(result: unknown): SigmaDocEntry[] {
  if (!result || typeof result !== "object") return [];
  const r = result as Record<string, unknown>;
  for (const key of ["entries", "documents", "items", "data"]) {
    const v = r[key];
    if (Array.isArray(v)) return v as SigmaDocEntry[];
  }
  return [];
}

export interface SigmaDescribeResult {
  ddl?: string;
  url?: string;
}

export async function sigmaDescribe(obj: object): Promise<SigmaDescribeResult> {
  const r = await fetch(`${BASE}/sigma/describe`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ object: obj }),
  });
  if (!r.ok) throw new Error(`sigma describe failed: ${r.status}`);
  const d = (await r.json()) as { result: SigmaDescribeResult | string };
  return typeof d.result === "string" ? { ddl: d.result } : d.result;
}

export async function sigmaIngest(args: {
  dataModelId: string;
  elementId: string;
  columns: { id: string; label: string }[];
  name: string;
  limit?: number;
}): Promise<DataSource> {
  const r = await fetch(`${BASE}/sigma/ingest`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      data_model_id: args.dataModelId,
      element_id: args.elementId,
      columns: args.columns,
      name: args.name,
      limit: args.limit ?? 5000,
    }),
  });
  if (!r.ok) throw new Error(`sigma ingest failed: ${r.status} ${await r.text().catch(() => "")}`);
  return r.json();
}

export interface ChatMessageWire {
  role: "user" | "assistant";
  content: string;
}

export interface GraphContext {
  source_label: string;
  nodes: string[];
  edges: { source: string; target: string; type: string; r: number }[];
}

export interface ChatStreamHandlers {
  onText: (chunk: string) => void;
  onToolUse: (name: string, input: Record<string, unknown>) => void;
  onToolResult: (name: string, ok: boolean, summary: string) => void;
  onSourceIngested: (info: {
    id: string;
    name: string;
    n_rows: number;
    numeric_columns: string[];
  }) => void;
  onGraphBuilt: (info: {
    graph: Graph;
    source_id: string;
    source_label: string;
    n_rows: number;
    n_rows_total: number;
  }) => void;
  onDone: () => void;
  onError: (msg: string) => void;
  signal?: AbortSignal;
}

export async function streamChat(
  messages: ChatMessageWire[],
  graphContext: GraphContext | null,
  h: ChatStreamHandlers,
): Promise<void> {
  let r: Response;
  try {
    r = await fetch(`${BASE}/chat`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: h.signal,
      body: JSON.stringify({ messages, graph_context: graphContext }),
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    h.onError(String(e));
    return;
  }
  if (!r.ok || !r.body) {
    h.onError(`chat failed: ${r.status} ${await r.text().catch(() => "")}`);
    return;
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const line = frame.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const payload = line.slice(6);
        let obj: Record<string, unknown>;
        try {
          obj = JSON.parse(payload);
        } catch {
          continue;
        }
        switch (obj.type) {
          case "text":
            h.onText(String(obj.text ?? ""));
            break;
          case "tool_use":
            h.onToolUse(
              String(obj.name ?? ""),
              (obj.input as Record<string, unknown>) ?? {},
            );
            break;
          case "tool_result":
            h.onToolResult(
              String(obj.name ?? ""),
              Boolean(obj.ok),
              String(obj.summary ?? ""),
            );
            break;
          case "source_ingested":
            h.onSourceIngested({
              id: String(obj.id),
              name: String(obj.name),
              n_rows: Number(obj.n_rows ?? 0),
              numeric_columns: (obj.numeric_columns as string[]) ?? [],
            });
            break;
          case "graph_built":
            h.onGraphBuilt({
              graph: obj.graph as Graph,
              source_id: String(obj.source_id),
              source_label: String(obj.source_label),
              n_rows: Number(obj.n_rows ?? 0),
              n_rows_total: Number(obj.n_rows_total ?? 0),
            });
            break;
          case "error":
            h.onError(String(obj.message ?? "unknown error"));
            break;
          case "done":
            h.onDone();
            return;
        }
      }
    }
    h.onDone();
  } catch (e) {
    if ((e as Error).name !== "AbortError") h.onError(String(e));
  }
}

export async function clearOverride(
  sourceId: string,
  varA: string,
  varB: string,
): Promise<void> {
  const r = await fetch(`${BASE}/overrides/clear`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ source_id: sourceId, var_a: varA, var_b: varB }),
  });
  if (!r.ok) throw new Error(`clear override failed: ${r.status}`);
}

export interface ExplainHandlers {
  onText: (chunk: string) => void;
  onDone: () => void;
  onError: (msg: string) => void;
  signal?: AbortSignal;
}

export async function streamEdgeExplanation(
  edge: GraphEdge,
  allColumns: string[],
  h: ExplainHandlers,
): Promise<void> {
  let r: Response;
  try {
    r = await fetch(`${BASE}/explain-edge`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      signal: h.signal,
      body: JSON.stringify({
        source: edge.source,
        target: edge.target,
        type: edge.type,
        pearson_r: edge.metadata.pearson_r,
        all_columns: allColumns,
      }),
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    h.onError(String(e));
    return;
  }
  if (!r.ok || !r.body) {
    h.onError(`explain failed: ${r.status} ${await r.text().catch(() => "")}`);
    return;
  }

  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let idx;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const line = frame.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const payload = line.slice(6);
        try {
          const obj = JSON.parse(payload) as
            | { text: string }
            | { done: true }
            | { error: string };
          if ("text" in obj) h.onText(obj.text);
          else if ("done" in obj) {
            h.onDone();
            return;
          } else if ("error" in obj) h.onError(obj.error);
        } catch {
          // ignore malformed frames
        }
      }
    }
    h.onDone();
  } catch (e) {
    if ((e as Error).name !== "AbortError") h.onError(String(e));
  }
}
