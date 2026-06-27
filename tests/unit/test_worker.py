"""Pure-logic tests for the embedding-worker failure classification.

The RQ job must let poison jobs (malformed / out-of-contract bodies) fail into
the FailedJobRegistry rather than retrying them forever, while genuinely
transient failures stay retryable.
"""

import pytest
from pydantic import ValidationError

from common.models import IngestMessage
from embedding_worker.tasks import is_poison


def _validation_error() -> ValidationError:
    with pytest.raises(ValidationError) as exc_info:
        IngestMessage.model_validate_json(b'{"document_id": "d1"}')  # missing fields
    return exc_info.value


def test_validation_error_is_poison():
    assert is_poison(_validation_error()) is True


def test_malformed_json_is_poison():
    with pytest.raises(ValidationError) as exc_info:
        IngestMessage.model_validate_json(b"not json at all")
    assert is_poison(exc_info.value) is True


@pytest.mark.parametrize(
    "exc",
    [ConnectionError("blob 503"), TimeoutError(), RuntimeError("db pool exhausted")],
)
def test_transient_errors_are_not_poison(exc):
    assert is_poison(exc) is False
