# Causality

A local web app for **causal inference on Net Dollar Retention** (NDR) data.
Pulls rows from Sigma Computing or a CSV upload, runs the **PC algorithm**
(`causal-learn`'s constraint-based discovery) over the variables you select,
renders the resulting DAG with typed edges, and lets a Claude-powered agent
(the *Causality Agent*) help you find data and interpret the relationships
the algorithm surfaces.

The intended workflow is: ask the agent in plain language to find a Sigma
data model → it ingests the right numeric columns into a local Parquet store
→ runs PC → renders a DAG. You inspect each edge, override directions where
domain knowledge disagrees with the algorithm, and use the agent to talk
through the causal interpretation.

---

## What you can do
<img width="2879" height="1413" alt="image" src="https://github.com/user-attachments/assets/78295a97-83d7-47e7-a1e9-9f7ff2a25514" />

- **Ingest from Sigma Computing** via OAuth + the Sigma MCP server. Browse
  data models, search by name through the chat agent, pull up to 1,000,000
  rows with automatic pagination.
- **Ingest from CSV** with streaming uploads up to ~5M rows.
- **Run PC causal discovery** on any local data source. Edges are typed:
  - `causal_directed` — PC inferred a direction
  - `causal_undirected` — PC found a link but couldn't orient it
    (Markov equivalence)
  - `correlation` — variables are associated but PC found a separating set
  - `user_override` — you set the direction by hand
- **Override edge directions** by right-clicking an edge: set A → B,
  B → A, mark "no causal link," or revert. Overrides persist per source.
- **Per-edge AI explanation** — click any edge, get a streamed
  Claude-generated interpretation in the bottom panel.
- **Causality Agent chat** (left side panel) — natural-language interface
  to the Sigma MCP tools and the PC algorithm. It can find Sigma objects,
  pick relevant columns, ingest, run PC, and explain the resulting graph.
- **Per-tool MCP permissions** — configure which Sigma capabilities run
  silently vs. require approval (currently a UI surface; enforcement is
  reserved for a follow-up).
- **Persistent state** — your Sigma OAuth tokens, ingested data sources,
  edge overrides, and last-active graph view all survive backend restarts
  and browser reloads.

---

## Architecture

```
                     ┌──────────────────────────────────────────────┐
                     │  Browser (React + Vite + Cytoscape)          │
                     │                                              │
                     │  ┌──────────┐  ┌────────────────┐  ┌──────┐  │
                     │  │ Chat     │  │ DAG view       │  │Admin │  │
                     │  │ Panel    │  │ (Cytoscape)    │  │Panel │  │
                     │  └─────┬────┘  └───────┬────────┘  └──┬───┘  │
                     │        │       Edge   │ Right-click   │      │
                     │        │       click  │ override      │      │
                     │  ┌─────┴───────────────┴───────────────┴───┐ │
                     │  │  Bottom inference panel (per-edge AI)    │ │
                     │  └──────────────────────────────────────────┘ │
                     └──────────┬───────────────────────────────────┘
                                │  HTTP + SSE (CORS allow localhost)
                                ▼
       ┌────────────────────────────────────────────────────────────┐
       │  FastAPI backend (uvicorn @ 8765)                          │
       │                                                            │
       │  ┌─────────────┐ ┌────────────┐ ┌──────────────────────┐   │
       │  │ /chat (SSE) │ │ /graph/*   │ │ /sigma/*  /sources/* │   │
       │  └──────┬──────┘ └─────┬──────┘ └──────┬───────────────┘   │
       │         │              │               │                    │
       │  ┌──────▼────┐   ┌─────▼──────┐  ┌─────▼──────────┐         │
       │  │ Anthropic │   │ causal/pc  │  │ Sigma MCP      │         │
       │  │  SDK      │   │ (PC algo)  │  │  client (OAuth)│         │
       │  └───────────┘   └─────┬──────┘  └─────┬──────────┘         │
       │                        │               │                    │
       │                  ┌─────▼───────────────▼────┐               │
       │                  │  data/tabular_store      │               │
       │                  │  (Parquet + JSON catalog)│               │
       │                  └──────────────────────────┘               │
       └────────────────────────────────────────────────────────────┘
                │                          │                  │
                ▼                          ▼                  ▼
        api.anthropic.com          api.staging.sigmacomputing.io   ~/.config/causality/
        (Messages API)             /mcp/v2 (Streamable HTTP)        (tokens, permissions)
```

### Layers

- **Frontend** ([`frontend/src/`](frontend/src/)) — Vite + React + TypeScript.
  Cytoscape (with `cytoscape-dagre`) renders the DAG. State lives in
  React; long-running AI responses come over SSE.
- **Backend** ([`backend/`](backend/)) — FastAPI on uvicorn. Async where it
  matters (chat, Sigma MCP), sync for PC. Single-process, single-user.
- **Data plane** — Apache Parquet files under `backend/.tabular/` with a
  small JSON catalog. PyArrow handles streaming reads/writes; pandas is
  used only inside the PC pipeline.
- **AI layer** — Anthropic Messages API (Claude Opus 4.7 by default) with
  prompt caching, adaptive thinking, and SSE streaming. Sigma access via
  the `mcp` Python SDK over Streamable HTTP with PKCE OAuth (dynamic
  client registration).

### Backend module map

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI routes, CORS, request validation |
| `agent/chat.py` | Chat agent loop — Claude tool use over Sigma MCP + local PC |
| `agent/explain.py` | Per-edge inference explanations (streamed) |
| `agent/secret_store.py` | In-memory Anthropic key + `~/.zshrc` persistence |
| `agent/validate.py` | Quick `count_tokens` validation when a key is set |
| `causal/pc.py` | PC wrapper: imputation, collinearity drop, edge typing |
| `causal/synthetic.py` | Synthetic 9-variable NDR DAG for the default view |
| `data/tabular_store.py` | Parquet-backed source catalog (CSV + Sigma) |
| `data/sigma_client.py` | MCP client + OAuth + paginated `query` |
| `data/sigma_permissions.py` | Per-tool `allow_always`/`ask_always` policy |
| `data/overrides.py` | Per-source edge-direction overrides (SQLite) |
| `data/app_state.py` | Last active source for view restoration |

---

## Prerequisites

| Tool | Version | Why |
|---|---|---|
| Python | 3.11 or newer | FastAPI + `causal-learn` + pyarrow |
| Node.js | 20.x or 22.x | Vite, modern React |
| Anthropic API key | `sk-ant-api03-...` | Causality Agent and per-edge explanations |
| Sigma Computing account | optional | only if you want to ingest from Sigma |

You **don't** need Sigma to try the app — it ships with a synthetic
9-variable NDR DAG and supports CSV upload.

---

## Setup

```bash
# 1. Clone
git clone <your-fork-url> Causality
cd Causality

# 2. Backend
cd backend
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

# 3. Frontend
cd ../frontend
npm install
```

### API key

The Causality Agent and per-edge explanations need an Anthropic key.
Two ways to provide it:

- **Env var (recommended)** — `export ANTHROPIC_API_KEY=sk-ant-...` in
  your shell (or add it to `~/.zshrc`). The header badge will show
  *"Anthropic API key · env"* in solid green.
- **In-app** — leave the badge red, click it, paste the key, hit Save.
  The app validates the key by calling `count_tokens` and writes it
  to your shell rc (`~/.zshrc` or `~/.bash_profile`) so it survives
  backend restarts. It's also stored in process memory so the current
  session works immediately.

The graph and PC features run with no key at all — only the AI features
need it.

---

## Running

Open two terminals.

```bash
# Terminal 1 — backend (port 8765)
cd backend
.venv/bin/uvicorn main:app --host 127.0.0.1 --port 8765 --log-level warning

# Terminal 2 — frontend (port 5173)
cd frontend
npm run dev
```

Open http://localhost:5173.

### First-run sanity check

```bash
# Verify the PC pipeline on synthetic data
cd backend
.venv/bin/python scripts/verify_pc.py
```

You should see all 9 ground-truth edges recovered with 100% precision/recall.

---

## Usage

### Synthetic data (no setup needed)

The default graph on first load is a 9-variable synthetic NDR DAG —
contract value, onboarding score, support tickets, expansion revenue,
churn risk, NDR, etc. Useful for getting a feel for the edge types and
override flow before connecting real data.

### CSV upload

1. Click **⚙ Data sources** in the header.
2. Under **Upload CSV**, choose a file (any size up to ~5M rows).
3. The new source appears under **Data sources** with a column count.
4. Click the source row to select it; the column picker expands below.
5. Tick numeric columns, click **Run PC**. The DAG re-renders.

CSVs are parsed with PyArrow (streaming, low-memory) and stored as
zstd-compressed Parquet at `backend/.tabular/<id>.parquet`.

### Sigma Computing

1. **⚙ Data sources → Sigma Computing → Connect**. A browser tab opens
   for OAuth (the app registers itself dynamically as a public PKCE
   client). After you sign in, the tab says "Sigma connected" and the
   row turns green.
2. **Talk to the agent**. In the left chat panel, ask something like
   *"Find data models about NDR"*. The agent calls `sigma_search`,
   summarizes the matches, and offers to load one.
3. **Ingest**. Tell the agent which data model and element to pull
   (e.g., *"Pull MRR + engagement signals from MONTHLY_RECURRING_REVENUE
   into Chroma"*). It runs `sigma_describe_element`, picks a generous
   numeric column set, calls `sigma_ingest_element` (paginated), and
   then auto-runs PC.
4. **The graph appears** in the main view. The header source label
   updates. The agent summarizes the most interesting causal_directed
   edges in chat.

### Reviewing the graph

- **Click an edge** → the bottom panel streams a Claude-generated
  explanation: what the edge type means, what the Pearson correlation
  implies, what could confound it, and a one-line takeaway.
- **Right-click an edge** → context menu. Set the direction either way,
  mark as "no causal link," or clear an override. Overrides persist
  per source in `backend/overrides.sqlite3`.
- **Hover the legend** → tooltip with the precise definition of each
  edge type.
- **Edge thickness** scales with `|Pearson r|` (range `[0.8, 6]px`),
  so strong ties read heavier.

### MCP capabilities + permissions

Open **⚙ Data sources → Sigma → Configure** to see the full list of
Sigma MCP tools the agent has access to (`begin_session`, `search`,
`list_documents`, `describe`, `query`, `create_workbook`). Per-tool
permission toggles between "Allow always" (silent) and "Ask always"
(future: prompt before running). Permissions persist in
`~/.config/causality/sigma_permissions.json`.

---

## Configuration & runtime state

| Path | Contents | Sensitive? |
|---|---|---|
| `~/.config/causality/sigma_tokens.json` | Sigma OAuth access + refresh tokens | **Yes — never share** |
| `~/.config/causality/sigma_permissions.json` | Per-tool `allow_always`/`ask_always` map | No |
| `~/.zshrc` (or `~/.bash_profile`) | `export ANTHROPIC_API_KEY=...` if you used Save | **Yes — never share** |
| `backend/.tabular/catalog.json` | Source registry (names, columns, row counts) | Workspace-shape only |
| `backend/.tabular/<id>.parquet` | Ingested rows from CSV/Sigma | **Yes — your customer data** |
| `backend/.tabular/app_state.json` | Last active source for view restoration | No |
| `backend/overrides.sqlite3` | Edge-direction overrides per source | Mildly (your hypotheses) |

All of those except the two `~/.config/causality/` files are inside the
repo tree, so the [.gitignore](.gitignore) excludes them.

### Environment variables

| Var | Effect |
|---|---|
| `ANTHROPIC_API_KEY` | Picked up by `secret_store` at backend start; surfaces as the green "env" badge |

The Sigma MCP URL defaults to staging
(`https://api.staging.sigmacomputing.io/mcp/v2`). To point at a different
server, open **⚙ Data sources → Sigma → Configure**, edit the **MCP server URL**
field, and click Save. The new URL persists to
`~/.config/causality/sigma_config.json` and survives backend restarts.
Saving a new URL clears the OAuth tokens (they're scoped to the previous
server), so you'll need to reconnect once.

---

## Tech stack

**Backend** (Python 3.11+):

- FastAPI + uvicorn (HTTP + SSE)
- `causal-learn` (PC algorithm, Fisher's Z conditional independence test)
- `pandas` + `numpy` (tabular ops)
- `pyarrow` (Parquet read/write, streaming CSV)
- `anthropic` SDK (Claude Messages API, async + sync)
- `mcp` SDK (Streamable HTTP transport, OAuth client provider)

**Frontend** (Node 20+):

- Vite + React + TypeScript
- Cytoscape.js + `cytoscape-dagre` (graph rendering, layered layout)

**Data**:

- Apache Parquet for source storage (zstd-compressed)
- SQLite for overrides
- JSON for catalogs and runtime state

---

## Security & privacy

- **Single local user.** No multi-tenancy; CORS allows only
  `http://localhost:5173`, `http://127.0.0.1:5173`, and the IPv6
  equivalent.
- **No secrets in source.** API keys live in env or in process memory
  (with optional `~/.zshrc` echo). OAuth tokens live under
  `~/.config/causality/`. None of this is in the repo.
- **Customer data stays local.** Parquet files in `backend/.tabular/`
  never leave your machine, and they're gitignored.
- **Anthropic API calls** include the Causality Agent's system prompt,
  the current chat conversation, the current graph context (node names
  + edge types + Pearson r values), and the active data source's
  *column names* (not row data) — except when the agent runs `run_pc`
  on its own behalf, in which case only the resulting graph (also
  metadata-only) is sent on the next turn.
- **Sigma row data is not sent to Anthropic.** Sigma rows go to
  `backend/.tabular/`; only column-level summaries reach Claude.

---

## Project structure

```
.
├── backend/
│   ├── agent/                   # Claude integrations
│   │   ├── chat.py              # Causality Agent (tool use + SSE)
│   │   ├── explain.py           # Per-edge interpretation
│   │   ├── secret_store.py      # API key memory + ~/.zshrc persistence
│   │   └── validate.py          # count_tokens validation on save
│   ├── causal/
│   │   ├── pc.py                # PC algorithm wrapper
│   │   └── synthetic.py         # Default 9-variable NDR DAG
│   ├── data/
│   │   ├── tabular_store.py     # Parquet + JSON catalog (CSV/Sigma sources)
│   │   ├── sigma_client.py      # MCP + OAuth + paginated query
│   │   ├── sigma_permissions.py # Per-tool policy store
│   │   ├── overrides.py         # SQLite override store
│   │   └── app_state.py         # Last-active-source persistence
│   ├── scripts/verify_pc.py     # Smoke test on synthetic data
│   ├── main.py                  # FastAPI app
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── client.ts        # All HTTP/SSE calls to the backend
│   │   │   └── types.ts         # Shared types (Graph, GraphEdge, etc.)
│   │   ├── graph/
│   │   │   ├── DagView.tsx      # Cytoscape canvas + interactions
│   │   │   ├── Legend.tsx       # Edge-type legend with hover tooltip
│   │   │   ├── EdgeContextMenu.tsx  # Right-click override menu
│   │   │   └── edgeStyles.ts    # Color / arrow / dash per edge type
│   │   ├── panels/
│   │   │   ├── ChatPanel.tsx    # Causality Agent chat
│   │   │   ├── AdminPanel.tsx   # Data sources drawer
│   │   │   ├── SigmaSection.tsx # Connect/disconnect + Configure
│   │   │   ├── SigmaConfigurator.tsx  # MCP tool list + permission toggles
│   │   │   ├── ApiKeyBadge.tsx  # Header API-key UI
│   │   │   └── InferencePanel.tsx     # Bottom per-edge AI panel
│   │   ├── App.tsx              # Top-level layout & state
│   │   └── main.tsx             # Vite entry
│   ├── index.html
│   └── package.json
└── .gitignore
```

---

## Troubleshooting

**"Anthropic API key not set"** — set the env var or use the badge in
the header. The badge validates the key against Anthropic before
turning green.

**Sigma "Connect" hangs** — make sure your browser actually opened the
OAuth tab; some popup blockers swallow `webbrowser.open`. The OAuth
flow times out after 5 minutes.

**Run PC returns "Only N rows after dropping non-numeric/NA"** — your
selection includes only sparsely-populated columns. The pipeline now
imputes NaN with 0 by default for SaaS engagement metrics; if you're
seeing this on a CSV, the columns probably aren't numeric (check your
header row).

**Run PC returns "correlation matrix is singular"** — two or more of
your columns are linearly dependent (e.g., `MRR` and `Prev_MRR` on a
short window, or `Total = A + B + C` along with all of A, B, C). The
algorithm auto-drops obvious cases (`|r| ≥ 0.999`); when it can't, it
returns a 400 naming the suspect columns. Pick a subset that's not
collinear and re-run.

**Chat hangs with a blinking cursor and no text** — almost always a
network blip mid-stream or an Anthropic auth failure. Stop, re-send.
If it persists, check the backend log; the SDK's exception text appears
in chat as an inline error after a one-shot retry.

**"TypeError: Failed to fetch"** — backend is down or CORS is blocking.
Confirm uvicorn is on port 8765, then check that you're hitting the
frontend at one of `localhost:5173`, `127.0.0.1:5173`, or `[::1]:5173`
(those are the three allowed origins).

---

## License

MIT — see [LICENSE](LICENSE).
