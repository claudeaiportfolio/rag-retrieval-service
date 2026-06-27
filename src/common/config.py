import logging
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

GenerationBackend = Literal["aoai", "anthropic"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_ignore_empty=True)

    # --- Azure infra endpoints (injected by k8s manifests or local env) ---
    key_vault_url: str = "https://localdevenv.vault.azure.net/"
    aoai_endpoint: str = ""
    aoai_embedding_deployment: str = "embedding"
    aoai_chat_deployment: str = "chat"

    # --- Redis / RQ queue (replaced Service Bus in Phase 2) ---
    redis_host: str = ""
    redis_port: int = 6379
    redis_db: int = 0
    redis_username: str = ""  # ACL user (least-privilege per consumer)
    redis_password: str = ""  # injected from a Key Vault-synced Secret (REDIS_PASSWORD)
    redis_use_tls: bool = False
    redis_ca_path: str = ""  # mounted CA bundle for in-cluster TLS
    rq_queue_name: str = "embed-jobs"

    storage_account: str = ""
    storage_container: str = "documents"

    pg_host: str = ""
    pg_replica_host: str = ""
    pg_database: str = "rag"
    pg_user: str = ""

    # --- Application config ---
    generation_backend: GenerationBackend = "aoai"
    anthropic_model: str = "claude-haiku-4-5-20251001"
    chunking_strategy: Literal["fixed", "heading"] = "heading"
    chunk_size_tokens: int = 512
    chunk_overlap_tokens: int = 64

    retrieval_top_k: int = 8
    index_type: Literal["hnsw", "ivfflat"] = "hnsw"

    auth0_domain: str = ""
    auth0_audience: str = "https://rag.dev.michaelalinks.com"

    # --- Secrets loaded from Key Vault at startup ---
    anthropic_api_key: str = ""

    log_level: str = "INFO"


settings = Settings()


async def load_secrets() -> None:
    """Fetch sensitive config from Key Vault and populate `settings`.

    Resolves credentials via DefaultAzureCredential — workload identity on AKS,
    az CLI locally. Never logs secret values.
    """
    from azure.identity.aio import DefaultAzureCredential
    from azure.keyvault.secrets.aio import SecretClient

    from azure.core.exceptions import ResourceNotFoundError

    credential = DefaultAzureCredential()
    async with SecretClient(vault_url=settings.key_vault_url, credential=credential) as client:
        # Load the Anthropic key whenever it isn't already set: the retrieval
        # backend may be AOAI, but answer generation can route to Claude via the
        # provider seam. Fetched here so it never has to pass through the
        # process environment.
        if not settings.anthropic_api_key:
            try:
                secret = await client.get_secret("anthropic-portfolio-key")
                settings.anthropic_api_key = secret.value or ""
            except ResourceNotFoundError:
                logger.warning("event=anthropic_key_missing vault=%s", settings.key_vault_url)
        if not settings.auth0_domain:
            try:
                secret = await client.get_secret("auth0-domain")
                settings.auth0_domain = secret.value or ""
            except Exception:
                logger.warning("event=auth0_domain_missing vault=%s", settings.key_vault_url)
    await credential.close()

    logger.info(
        "event=secrets_loaded vault=%s generation=%s",
        settings.key_vault_url,
        settings.generation_backend,
    )
