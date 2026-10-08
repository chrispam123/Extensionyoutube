import os
from datetime import datetime

from observability.backend import handler

DEFAULT_VALUES = {
    f"{component}_{metric}": 0
    for component in handler.DEFAULT_COMPONENTS
    for metric in ("invocations", "errors", "throttles", "duration_p95_ms")
}


class FakeCloudWatch:
    def __init__(self, values):
        self.values = values

    def get_metric_data(self, **kwargs):
        configured = os.getenv("OBSERVED_COMPONENTS")
        component_count = len(
            [
                component
                for component in (
                    configured.split(",") if configured else handler.DEFAULT_COMPONENTS
                )
                if component.strip()
            ]
        )
        assert len(kwargs["MetricDataQueries"]) == component_count * 4
        assert isinstance(kwargs["StartTime"], datetime)
        assert isinstance(kwargs["EndTime"], datetime)
        return {
            "MetricDataResults": [
                {"Id": metric_id, "Values": [value]}
                for metric_id, value in self.values.items()
            ]
        }


def _values(**overrides):
    values = DEFAULT_VALUES.copy()
    values.update(overrides)
    return values


def test_all_lambdas_are_healthy_without_errors(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "develop")
    monkeypatch.setattr(handler, "cloudwatch", FakeCloudWatch(_values()))

    result = handler.lambda_handler({}, None)

    assert result["status"] == "healthy"
    assert len(result["components"]) == 6
    assert {item["component"] for item in result["components"]} == set(
        handler.DEFAULT_COMPONENTS
    )


def test_worker_is_warning_when_error_rate_exceeds_threshold(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setattr(
        handler,
        "cloudwatch",
        FakeCloudWatch(
            _values(worker_invocations=100, worker_errors=2, worker_duration_p95_ms=500)
        ),
    )

    result = handler.lambda_handler({}, None)
    worker = next(
        item for item in result["components"] if item["component"] == "worker"
    )

    assert result["status"] == "warning"
    assert worker["status"] == "warning"
    assert worker["metrics"]["error_rate"] == 2


def test_any_throttled_lambda_makes_global_status_critical(monkeypatch):
    monkeypatch.setattr(
        handler,
        "cloudwatch",
        FakeCloudWatch(_values(status_throttles=1)),
    )

    result = handler.lambda_handler({}, None)
    status = next(
        item for item in result["components"] if item["component"] == "status"
    )

    assert result["status"] == "critical"
    assert status["status"] == "critical"


def test_no_invocations_returns_healthy_components_with_zero_error_rate(monkeypatch):
    monkeypatch.setattr(handler, "cloudwatch", FakeCloudWatch(_values()))

    result = handler.lambda_handler({}, None)

    assert result["status"] == "healthy"
    assert all(item["metrics"]["error_rate"] == 0 for item in result["components"])


def test_components_can_be_restricted_by_environment_variable(monkeypatch):
    monkeypatch.setenv("OBSERVED_COMPONENTS", "worker,auth")
    monkeypatch.setattr(handler, "cloudwatch", FakeCloudWatch(_values()))

    result = handler.lambda_handler({}, None)

    assert [item["component"] for item in result["components"]] == ["worker", "auth"]
