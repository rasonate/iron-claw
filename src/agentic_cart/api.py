

import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from pathlib import Path
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field
from nemoguardrails import LLMRails, RailsConfig
from nat.runtime.loader import load_workflow

NAT_CONFIG_PATH = "configs/multi_agent.yml"
RAILS_CONFIG_DIR = "configs/guardrails"


# --- Request / Response Schemas ---
class AgentQueryRequest(BaseModel):
    query: str = Field(..., min_length=3, max_length=4000, description="Financial analysis or compliance prompt")
    session_id: Optional[str] = Field(default=None, description="Optional client correlation ID")


class AgentQueryResponse(BaseModel):
    request_id: str
    session_id: str
    status: str
    response: str
    latency_ms: float


# --- FastAPI Lifespan (Keeps NeMo Workflow & Guardrails Warm) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.rails = LLMRails(RailsConfig.from_path(RAILS_CONFIG_DIR))
    async with load_workflow(NAT_CONFIG_PATH) as workflow:
        app.state.workflow = workflow
        yield


app = FastAPI(
    title="NVIDIA FinTech Multi-Agent API",
    description="100% NVIDIA-native Supervisor/Specialist Multi-Agent powered by NIM, NeMo Agent Toolkit, and NeMo Guardrails.",
    version="1.0.0",
    lifespan=lifespan,
)

STATIC_DIR = Path(__file__).resolve().parents[2] / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --- Health Check Endpoint (For Docker / Kubernetes Probes) ---
@app.get("/health", tags=["Operations"])
async def health_check():
    return {"status": "healthy", "engine": "nvidia-nim-nemo"}

@app.get("/", include_in_schema=False)
async def serve_frontend():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/v1/agent/query", response_model=AgentQueryResponse, tags=["FinTech Multi-Agent"])
async def query_fintech_agent(
    payload: AgentQueryRequest,
    x_api_key: Optional[str] = Header(default=None, description="Optional internal service API key"),
):
    start_time = time.perf_counter()
    request_id = str(uuid.uuid4())
    session_id = payload.session_id or request_id

    try:
        # 1. Input Compliance & Security Screening via NeMo Guardrails
        guard_result = await app.state.rails.generate_async(
            messages=[{"role": "user", "content": payload.query}]
        )
        guard_text = guard_result.get("content", "")
        if "I cannot" in guard_text or "blocked" in guard_text.lower():
            latency = (time.perf_counter() - start_time) * 1000
            return AgentQueryResponse(
                request_id=request_id,
                session_id=session_id,
                status="blocked_by_guardrails",
                response=guard_text,
                latency_ms=round(latency, 2),
            )

        # 2. Execute NVIDIA NeMo Supervisor -> Specialist Multi-Agent Workflow
        async with app.state.workflow.run(payload.query) as runner:
            final_output = await runner.result(to_type=str)

        latency = (time.perf_counter() - start_time) * 1000
        return AgentQueryResponse(
            request_id=request_id,
            session_id=session_id,
            status="success",
            response=final_output,
            latency_ms=round(latency, 2),
        )

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {str(exc)}") from exc
