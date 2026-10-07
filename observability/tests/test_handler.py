from datetime import datetime

from observability.backend import handler


class FakeCloudWatch:
    def __init__(self, values):
        self.values = values

    def get_metric_data(self, **kwargs):
        assert len(kwargs["MetricDataQueries"]) == 4
        assert isinstance(kwargs["StartTime"], datetime)
        assert isinstance(kwargs["EndTime"], datetime)
        return {
            "MetricDataResults": [
                {"Id": metric_id, "Values": [value]}
                for metric_id, value in self.values.items()
            ]
        }


def test_worker_is_healthy_without_errors(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "develop")
    monkeypatch.setattr(
        handler,
        "cloudwatch",
        FakeCloudWatch(
            {
                "invocations": 20,
                "errors": 0,
                "throttles": 0,
                "duration_p95_ms": 500,
            }
        ),
    )

    result = handler.lambda_handler({}, None)

    assert result["status"] == "healthy"
    assert result["metrics"]["error_rate"] == 0
    assert result["function_name"] == "extension-worker-develop"


def test_worker_is_warning_when_error_rate_exceeds_threshold(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setattr(
        handler,
        "cloudwatch",
        FakeCloudWatch(
            {
                "invocations": 100,
                "errors": 2,
                "throttles": 0,
                "duration_p95_ms": 500,
            }
        ),
    )

    result = handler.lambda_handler({}, None)

    assert result["status"] == "warning"
    assert result["metrics"]["error_rate"] == 2


def test_worker_is_critical_when_throttled(monkeypatch):
    monkeypatch.setattr(
        handler,
        "cloudwatch",
        FakeCloudWatch(
            {
                "invocations": 10,
                "errors": 0,
                "throttles": 1,
                "duration_p95_ms": 500,
            }
        ),
    )

    result = handler.lambda_handler({}, None)

    assert result["status"] == "critical"


def test_worker_with_no_invocations_returns_zero_error_rate(monkeypatch):
    monkeypatch.setattr(
        handler,
        "cloudwatch",
        FakeCloudWatch(
            {
                "invocations": 0,
                "errors": 0,
                "throttles": 0,
                "duration_p95_ms": 0,
            }
        ),
    )

    result = handler.lambda_handler({}, None)

    assert result["status"] == "healthy"
    assert result["metrics"]["error_rate"] == 0
