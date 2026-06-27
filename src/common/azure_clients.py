"""Azure client factories.

Every client uses DefaultAzureCredential — resolves to workload identity in
the cluster and to the local `az login` during dev. Nothing here ever sees a
SAS token, account key, or static secret.
"""

from __future__ import annotations

import logging

from azure.identity.aio import DefaultAzureCredential
from azure.storage.blob.aio import BlobServiceClient

logger = logging.getLogger(__name__)

_credential: DefaultAzureCredential | None = None


def credential() -> DefaultAzureCredential:
    global _credential
    if _credential is None:
        _credential = DefaultAzureCredential()
    return _credential


def blob_service_client(account: str) -> BlobServiceClient:
    return BlobServiceClient(
        account_url=f"https://{account}.blob.core.windows.net",
        credential=credential(),
    )


async def aoai_token() -> str:
    """Fetch a cognitive-services data-plane token. Cached by azure-identity."""
    token = await credential().get_token("https://cognitiveservices.azure.com/.default")
    return token.token
