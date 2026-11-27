# Iron Claw — NVIDIA FinTech Multi-Agent System

A local-first, NVIDIA-native **FinTech Multi-Agent Assistant** built with **NVIDIA NIM**, **NeMo Agent Toolkit (`nvidia-nat`)**, **NeMo Guardrails**, **Qdrant**, and **FastAPI**.

It provides a dark-themed web console and REST API where incoming financial analysis and compliance queries are screened for safety, delegated by a Supervisor agent to specialized ReAct agents, and backed by deterministic financial tools plus a vector-search + reranking RAG pipeline.

---


## Project Structure

```text
iron-claw/
├── config/
│   ├── config.yml                  # NeMo Agent Toolkit (NAT) LLM, tool, and agent config
│   └── guardrails/
│       └── config.yml              # NeMo Guardrails input/output safety flows
├── src/agentic_cart/
│   ├── __init__.py
│   ├── api.py                      # FastAPI app, /health, /v1/agent/query, static UI serving
│   ├── main.py                     # Standalone CLI orchestrator runner
│   ├── tools.py                    # Quantitative risk (Sharpe/VaR) & AML/KYC audit tools
│   └── rag_tools.py                # Qdrant + NeMo Embed/Rerank policy RAG tool
├── static/
│   └── index.html                  # Web console UI with preset test prompts
├── docker-compose.yml              # Qdrant + Nemotron, Embed, and Rerank NIM services
├── Dockerfile                      # Container build for FastAPI app (Python 3.14 + uv)
├── pyproject.toml                  # Project metadata and Python dependencies
└── uv.lock                         # Locked dependency graph
```

---

## Prerequisites

- **Python** `>= 3.14` (pinned in `.python-version`) and **[uv](https://docs.astral.sh/uv/)**
- **Docker** & **Docker Compose** with **NVIDIA Container Toolkit** (for GPU-accelerated NIM containers)
- **NVIDIA NGC API Key** (`NGC_API_KEY`) to pull and run NIM images from `nvcr.io`

---

## Getting Started

### 1. Configure Environment Variables

Ensure your `.env` file in the repository root sets your NGC API key:

```env
NGC_API_KEY=your_ngc_api_key_here
```

### 2. Start Supporting Services (Qdrant & NVIDIA NIMs)

```bash
docker compose up -d
```

This launches:
| Service | Image | Host Port(s) | Purpose |
|---|---|---|---|
| `qdrant` | `qdrant/qdrant:latest` | `6333`, `6334` | Vector store (`./qdrant_storage`) |
| `nemotron-nim` | `nvcr.io/nim/nvidia/nemotron-mini-4b-instruct:latest` | `8000` | Supervisor, specialist & guardrail LLM |
| `nemo-embed-nim` | `nvcr.io/nim/nvidia/llama-3.2-nv-embedqa-1b-v2:latest` | `8001` | Policy & query embeddings |
| `nemo-rerank-nim` | `nvcr.io/nim/nvidia/llama-3.2-nv-rerankqa-1b-v2:latest` | `8002` | Passage reranking |

### 3. Install Dependencies

```bash
uv sync --frozen
```

### 4. Run the Application

**Option A — Standalone Script (`src/agentic_cart/main.py`):**

Runs a sample multi-part prompt through NeMo Guardrails and the `config/config.yml` workflow:

```bash
uv run python -m agentic_cart.main
```

**Option B — FastAPI Web Server & UI (`src/agentic_cart/api.py`):**

```bash
uv run uvicorn agentic_cart.api:app --host 0.0.0.0 --port 8080
```

Then open [http://localhost:8080](http://localhost:8080) to use the web console.

**Option C — Build & Run the App Container:**

```bash
docker build -t iron-claw-api .
docker run --rm -p 8080:8080 iron-claw-api
```

---

## API Reference

### `GET /`
Serves the interactive web console from `static/index.html`.

### `GET /health`
Health probe used by Docker/Kubernetes and the UI status badge.
```json
{
  "status": "healthy",
  "engine": "nvidia-nim-nemo"
}
```

### `POST /v1/agent/query`
Screens the prompt with NeMo Guardrails and executes the NAT Supervisor → Specialist workflow.

**Request body:**
```json
{
  "query": "Evaluate a portfolio worth 5,000,000 with 14% expected return and 18% volatility, and audit an incoming wire transfer of 1,500,000 from a KYC-verified account.",
  "session_id": "optional-correlation-id"
}
```

**Response body:**
```json
{
  "request_id": "uuid",
  "session_id": "uuid-or-provided",
  "status": "success",
  "response": "...",
  "latency_ms": 1234.56
}
```
- `status` is `"blocked_by_guardrails"` if input screening rejects the prompt, or `"success"` when processed by the supervisor agent.
- Accepts an optional `x-api-key` header.

---

## Configuration

- **Agent & Tool Config (`config/config.yml`)**:
  - `portfolio_risk_tool`: `risk_free_rate` defaults to `0.065` (6.5%).
  - `aml_audit_tool`: `high_value_threshold` defaults to `1000000.0`.
  - `policy_rag_tool`: `embed_url` (`http://localhost:8001/v1/embeddings`), `rerank_url` (`http://localhost:8002/v1/ranking`), `top_k_retrieve: 4`, `top_n_rerank: 2`.
  - `function_groups.fintech_mcp_data`: Optional `streamable-http` MCP client configured for `http://localhost:9901/mcp`.
- **Guardrails (`config/guardrails/config.yml`)**:
  - Points to `http://localhost:8000/v1` using `nvidia/nemotron-mini-4b-instruct`.

---

## Known Issues / Work in Progress

A few rough edges currently exist in the codebase and should be addressed before production use:

1. **Config path mismatch in `api.py`**: `src/agentic_cart/api.py` sets `NAT_CONFIG_PATH = "configs/multi_agent.yml"` and `RAILS_CONFIG_DIR = "configs/guardrails"`, whereas the repository stores them at `config/config.yml` and `config/guardrails`.
2. **Policy RAG tool schema/format bugs in `rag_tools.py`**:
   - `PolicyRagConfig` does not yet declare `qdrant_url` or `collection_name` fields referenced inside `search_regulatory_policies_tool`.
   - `POLICY_DOCUMENTS` is currently a list of plain strings while the indexing block reads `doc["text"]` and `doc["section"]`.
   - Query embedding lookup reads `q_resp.json()["data"]["embedding"]` instead of `q_resp.json()["data"][0]["embedding"]`.
3. **Package script entrypoint**: `pyproject.toml` defines `agentic-cart = "agentic_cart:main"`, while `src/agentic_cart/__init__.py` does not yet export a `main` function.
4. **GPU resource sharing in `docker-compose.yml`**: All three NIM services reserve `count: all` GPUs without per-container memory limits, which requires sufficient total VRAM to host all models simultaneously.
