import logging
import os

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

try:
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    _httpx_available = True
except ImportError:
    _httpx_available = False

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    _fastapi_available = True
except ImportError:
    _fastapi_available = False

_DEFAULT_ENDPOINT = "otel-collector.otel.svc.cluster.local:4317"

# OTel GenAI semantic conventions (semconv 1.41.0).
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_RESPONSE_MODEL = "gen_ai.response.model"
GEN_AI_PROVIDER_NAME = "gen_ai.provider.name"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_OPERATION_NAME = "gen_ai.operation.name"
GEN_AI_RESPONSE_FINISH_REASONS = "gen_ai.response.finish_reasons"

# MCP semconv
MCP_METHOD_NAME = "mcp.method.name"
MCP_SESSION_ID = "mcp.session.id"

# RAG-specific extensions.
RAG_DOC_ID = "rag.document.id"
RAG_TENANT_ID = "rag.tenant.id"
RAG_CHUNK_COUNT = "rag.chunk.count"
RAG_RETRIEVAL_TOP_K = "rag.retrieval.top_k"
RAG_RETRIEVAL_SCORES = "rag.retrieval.scores"
RAG_INDEX_TYPE = "rag.index.type"


def setup_telemetry(service_name: str) -> None:
    """Initialise tracer + logger providers; bridge stdlib logging to OTLP.

    Never raises — telemetry failure must not block the app from starting.
    Never include Key Vault secret values in span attributes or log fields.
    """
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(levelname)s %(name)s %(message)s",
    )

    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", _DEFAULT_ENDPOINT)
    resource = Resource.create({"service.name": service_name})

    try:
        _setup_traces(endpoint, resource)
        _setup_logs(endpoint, resource)
        LoggingInstrumentor().instrument(set_logging_format=True)
        if _httpx_available:
            HTTPXClientInstrumentor().instrument()
        logging.info(
            "event=telemetry_initialized service=%s endpoint=%s",
            service_name,
            endpoint,
        )
    except Exception:
        logging.warning(
            "event=telemetry_setup_failed service=%s endpoint=%s",
            service_name,
            endpoint,
            exc_info=True,
        )


def instrument_fastapi(app) -> None:
    if _fastapi_available:
        FastAPIInstrumentor.instrument_app(app)


def get_tracer(name: str) -> trace.Tracer:
    return trace.get_tracer(name)


def _setup_traces(endpoint: str, resource: Resource) -> None:
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)


def _setup_logs(endpoint: str, resource: Resource) -> None:
    exporter = OTLPLogExporter(endpoint=endpoint, insecure=True)
    provider = LoggerProvider(resource=resource)
    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
    set_logger_provider(provider)
