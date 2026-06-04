from __future__ import annotations

GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_DATA_SOURCE_ID = "gen_ai.data_source.id"
GEN_AI_AGENT_NAME = "gen_ai.agent.name"
GEN_AI_AGENT_ID = "gen_ai.agent.id"
GEN_AI_TOOL_NAME = "gen_ai.tool.name"
GEN_AI_EVALUATION_NAME = "gen_ai.evaluation.name"
GEN_AI_EVALUATION_SCORE = "gen_ai.evaluation.score"
ERROR_TYPE = "error.type"

MCP_METHOD_NAME = "mcp.method.name"
MCP_SESSION_ID = "mcp.session.id"
MCP_PROTOCOL_VERSION = "mcp.protocol.version"
JSONRPC_REQUEST_ID = "jsonrpc.request.id"
NETWORK_TRANSPORT = "network.transport"
NETWORK_PROTOCOL_NAME = "network.protocol.name"

QUIMERA_AGENT_ID = "quimera.agent_id"
QUIMERA_SESSION_ID = "quimera.session_id"
QUIMERA_TASK_ID = "quimera.task_id"
QUIMERA_STAGE = "quimera.stage"
QUIMERA_PROFILE_NAME = "quimera.profile_name"
QUIMERA_SCHEMA_VERSION = "quimera.schema_version"
HYBRID_BACKEND = "hybrid.backend"
HYBRID_FUSION_BACKEND = "hybrid.fusion.backend"
RETRIEVAL_CACHE_HIT = "retrieval.cache_hit"
RETRIEVAL_CACHE_BYPASS = "retrieval.cache_bypass"
RETRIEVAL_TOP_K = "retrieval.top_k"
RETRIEVAL_RESULT_COUNT = "retrieval.result_count"
RETRIEVAL_RERANK_ENABLED = "retrieval.rerank.enabled"
RETRIEVAL_RRF_K = "retrieval.rrf.k"
CACHE_BACKEND = "cache.backend"
CACHE_COLLECTION = "cache.collection"
CACHE_HIT = "cache.hit"
CACHE_SCHEMA_VERSION = "cache.schema_version"
LATENCY_EMBED_MS = "latency.embed_ms"
LATENCY_RETRIEVAL_MS = "latency.retrieval_ms"
LATENCY_RRF_MS = "latency.rrf_ms"
LATENCY_RERANK_MS = "latency.rerank_ms"
LATENCY_PG_MS = "latency.pg_ms"
LATENCY_LLM_MS = "latency.llm_ms"
LATENCY_TOTAL_MS = "latency.total_ms"

GENAI_ATTRS = frozenset(
    {
        GEN_AI_OPERATION_NAME,
        GEN_AI_PROVIDER_NAME,
        GEN_AI_REQUEST_MODEL,
        GEN_AI_RESPONSE_MODEL,
        GEN_AI_DATA_SOURCE_ID,
        GEN_AI_AGENT_NAME,
        GEN_AI_AGENT_ID,
        GEN_AI_TOOL_NAME,
        GEN_AI_EVALUATION_NAME,
        GEN_AI_EVALUATION_SCORE,
        ERROR_TYPE,
    }
)

MCP_ATTRS = frozenset(
    {
        MCP_METHOD_NAME,
        MCP_SESSION_ID,
        MCP_PROTOCOL_VERSION,
        JSONRPC_REQUEST_ID,
        NETWORK_TRANSPORT,
        NETWORK_PROTOCOL_NAME,
    }
)

QUIMERA_ATTRS = frozenset(
    {
        QUIMERA_AGENT_ID,
        QUIMERA_SESSION_ID,
        QUIMERA_TASK_ID,
        QUIMERA_STAGE,
        QUIMERA_PROFILE_NAME,
        QUIMERA_SCHEMA_VERSION,
        HYBRID_BACKEND,
        HYBRID_FUSION_BACKEND,
        RETRIEVAL_CACHE_HIT,
        RETRIEVAL_CACHE_BYPASS,
        RETRIEVAL_TOP_K,
        RETRIEVAL_RESULT_COUNT,
        RETRIEVAL_RERANK_ENABLED,
        RETRIEVAL_RRF_K,
        CACHE_BACKEND,
        CACHE_COLLECTION,
        CACHE_HIT,
        CACHE_SCHEMA_VERSION,
        LATENCY_EMBED_MS,
        LATENCY_RETRIEVAL_MS,
        LATENCY_RRF_MS,
        LATENCY_RERANK_MS,
        LATENCY_PG_MS,
        LATENCY_LLM_MS,
        LATENCY_TOTAL_MS,
    }
)

SAFE_ATTRIBUTE_PREFIXES = frozenset(
    {
        "gen_ai.",
        "mcp.",
        "jsonrpc.",
        "network.",
        "quimera.",
        "hybrid.",
        "retrieval.",
        "cache.",
        "latency.",
        "error.",
    }
)

PII_FORBIDDEN_ATTRS = frozenset(
    {
        "query_text",
        "prompt",
        "answer",
        "response",
        "response_text",
        "raw_response",
        "chunk",
        "chunk_text",
        "document",
        "document_text",
        "vector",
        "embedding",
        "payload",
        "raw_payload",
        "authorization",
        "api_key",
        "token",
        "password",
        "secret",
        "dsn",
        "database_url",
    }
)

PII_FORBIDDEN_SUBSTRINGS = frozenset(
    {
        "query_text",
        "prompt",
        "answer",
        "raw_response",
        "response_text",
        "chunk",
        "document_text",
        "vector",
        "embedding",
        "payload",
        "authorization",
        "api_key",
        "token",
        "password",
        "secret",
        "dsn",
        "database_url",
    }
)

SAFE_ATTRS = GENAI_ATTRS | MCP_ATTRS | QUIMERA_ATTRS

