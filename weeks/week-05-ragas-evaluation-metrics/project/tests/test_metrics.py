from app.metrics import resolve_metrics
from tests.conftest import requires_openai


@requires_openai
def test_resolve_metrics_returns_six_metrics_and_a_known_api_version():
    metrics, api_version = resolve_metrics()
    assert len(metrics) == 6
    assert api_version in {"collections", "legacy"}
