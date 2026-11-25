import uuid
import httpx
import numpy as np
from pydantic import Field
from nat.builder.builder import Builder
from nat.builder.framework_enum import LLMFrameworkEnum
from nat.builder.function_info import FunctionInfo
from nat.cli.register_workflow import register_function
from nat.data_models.function import FunctionBaseConfig

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

# Sample regulatory & credit policy corpus (replace with PDF/database loader in production)
POLICY_DOCUMENTS = [
    "Credit Policy Section 4.1: Corporate term loans exceeding INR 50,00,000 require a minimum Debt Service Coverage Ratio (DSCR) of 1.35x and audited financials for the past 3 fiscal years.",
    "Credit Policy Section 4.2: Unsecured working capital facilities are capped at 20% of annual verified turnover for borrowers with internal credit rating BBB or higher.",
    "Regulatory Filing Rule 7.3 (AML/KYC): Cross-border wire transfers above USD 10,000 or equivalent require Enhanced Due Diligence (EDD), beneficial ownership verification, and source-of-funds documentation.",
    "Regulatory Filing Rule 9.1 (Liquidity): Institutions must maintain a minimum Liquidity Coverage Ratio (LCR) of 100% against 30-day stressed net cash outflows.",
    "Credit Policy Section 6.4 (Collateral): Commercial real estate collateral is subject to a maximum Loan-to-Value (LTV) haircut of 60%."
]


class PolicyRagConfig(FunctionBaseConfig, name="search_regulatory_policies"):
    embed_url: str = Field(default="http://localhost:8001/v1/embeddings")
    rerank_url: str = Field(default="http://localhost:8002/v1/ranking")
    embed_model: str = Field(default="nvidia/llama-3.2-nv-embedqa-1b-v2")
    rerank_model: str = Field(default="nvidia/llama-3.2-nv-rerankqa-1b-v2")
    top_k_retrieve: int = Field(default=4)
    top_n_rerank: int = Field(default=2)

@register_function(config_type=PolicyRagConfig, framework_wrappers=[LLMFrameworkEnum.NONE])
async def search_regulatory_policies_tool(config: PolicyRagConfig, builder: Builder):
    qdrant = AsyncQdrantClient(url=config.qdrant_url)

    # 1. Create collection and index documents once if not already persisted in Qdrant
    if not await qdrant.collection_exists(config.collection_name):
        async with httpx.AsyncClient(timeout=30.0) as client:
            doc_resp = await client.post(
                config.embed_url,
                json={
                    "input": [doc["text"] for doc in POLICY_DOCUMENTS],
                    "model": config.embed_model,
                    "input_type": "passage",
                },
            )
            doc_resp.raise_for_status()
            embeddings = [item["embedding"] for item in doc_resp.json()["data"]]

        vector_dim = len(embeddings[0])
        await qdrant.create_collection(
            collection_name=config.collection_name,
            vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
        )

        points = [
            PointStruct(
                id=str(uuid.uuid5(uuid.NAMESPACE_DNS, doc["section"])),
                vector=vec,
                payload={"section": doc["section"], "text": doc["text"]},
            )
            for doc, vec in zip(POLICY_DOCUMENTS, embeddings)
        ]
        await qdrant.upsert(collection_name=config.collection_name, points=points)

    # 2. Query Qdrant + Rerank with NeMo Retriever Reranking NIM
    async def _search_policies(query: str) -> str:
        """Retrieves policy chunks from Qdrant and reranks them using NVIDIA NeMo Retriever."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Embed query
            q_resp = await client.post(
                config.embed_url,
                json={
                    "input": [query],
                    "model": config.embed_model,
                    "input_type": "query",
                },
            )
            q_resp.raise_for_status()
            query_vector = q_resp.json()["data"]["embedding"]

            # Vector search in Qdrant
            search_hits = await qdrant.query_points(
                collection_name=config.collection_name,
                query=query_vector,
                limit=config.top_k_retrieve,
                with_payload=True,
            )

            if not search_hits.points:
                return "No matching policy sections found in Qdrant."

            candidates = [{"text": hit.payload["text"]} for hit in search_hits.points]

            # Rerank via NeMo Retriever Reranking NIM
            r_resp = await client.post(
                config.rerank_url,
                json={
                    "model": config.rerank_model,
                    "query": {"text": query},
                    "passages": candidates,
                    "truncate": "END",
                },
            )
            r_resp.raise_for_status()
            rankings = r_resp.json()["rankings"][: config.top_n_rerank]

        results = []
        for rank in rankings:
            idx = rank["index"]
            score = rank["logit"]
            results.append(f"[Rerank Score: {score:.2f}] {candidates[idx]['text']}")

        return "\n".join(results)

    yield FunctionInfo.from_fn(
        _search_policies,
        description="Search internal credit policies and regulatory filings stored in Qdrant using NeMo Retriever."
    )