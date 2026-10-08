import os
from datetime import datetime

from observability.backend import handler

DEFAULT_VALUES = {
    f"lambda_{component}_{metric}": 0
    for component in handler.DEFAULT_COMPONENTS
    for metric in ("invocations", "errors", "throttles", "duration_p95_ms")
}
DEFAULT_VALUES.update(
    {
        f"sqs_{queue}_{metric}": 0
        for queue in handler.DEFAULT_QUEUES
        for metric in ("visible", "not_visible", "oldest_age_s")
    }
)


class FakeCloudWatch:
    def __init__(self, values):
        self.values = values

    def get_metric_data(self, **kwargs):
        configured_components = os.getenv("OBSERVED_COMPONENTS")
        configured_queues = os.getenv("OBSERVED_QUEUES")
        component_count = len(
            [
                item
                for item in (
                    configured_components.split(",")
                    if configured_components
                    else handler.DEFAULT_COMPONENTS
                )
                if item.strip()
            ]
        )
        queue_count = len(
            [
                item
                for item in (
                    configured_queues.split(",")
                    if configured_queues
                    else handler.DEFAULT_QUEUES
                )
                if item.strip()
            ]
        )
        assert len(kwargs["MetricDataQueries"]) == component_count * 4 + queue_count * 3
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


def test_all_lambdas_and_queues_are_healthy_without_errors(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "develop")
    monkeypatch.setattr(handler, "cloudwatch", FakeCloudWatch(_values()))

    result = handler.lambda_handler({}, None)

    assert result["status"] == "healthy"
    assert len(result["components"]) == 6
    assert len(result["queues"]) == 4


def test_worker_is_warning_when_error_rate_exceeds_threshold(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "prod")
    monkeypatch.setattr(
        handler,
        "cloudwatch",
        FakeCloudWatch(_values(lambda_worker_invocations=100, lambda_worker_errors=2)),
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
        FakeCloudWatch(_values(lambda_status_throttles=1)),
    )

    result = handler.lambda_handler({}, None)
    status = next(
        item for item in result["components"] if item["component"] == "status"
    )

    assert result["status"] == "critical"
    assert status["status"] == "critical"


def test_dlq_with_visible_messages_is_critical(monkeypatch):
    monkeypatch.setattr(
        handler,
        "cloudwatch",
        FakeCloudWatch(_values(sqs_dlq_visible=1)),
    )

    result = handler.lambda_handler({}, None)
    dlq = next(item for item in result["queues"] if item["queue"] == "dlq")

    assert result["status"] == "critical"
    assert dlq["status"] == "critical"
    assert dlq["type"] == "dlq"


def test_primary_queue_backlog_is_warning(monkeypatch):
    monkeypatch.setattr(
        handler,
        "cloudwatch",
        FakeCloudWatch(_values(sqs_work_visible=11)),
    )

    result = handler.lambda_handler({}, None)
    work = next(item for item in result["queues"] if item["queue"] == "work")

    assert result["status"] == "warning"
    assert work["status"] == "warning"


def test_oldest_message_over_thirty_minutes_is_critical(monkeypatch):
    monkeypatch.setattr(
        handler,
        "cloudwatch",
        FakeCloudWatch(_values(sqs_ingestion_oldest_age_s=1801)),
    )

    result = handler.lambda_handler({}, None)
    ingestion = next(item for item in result["queues"] if item["queue"] == "ingestion")

    assert result["status"] == "critical"
    assert ingestion["status"] == "critical"


def test_components_and_queues_can_be_restricted_by_environment(monkeypatch):
    monkeypatch.setenv("OBSERVED_COMPONENTS", "worker,auth")
    monkeypatch.setenv("OBSERVED_QUEUES", "work,dlq")
    monkeypatch.setattr(handler, "cloudwatch", FakeCloudWatch(_values()))

    result = handler.lambda_handler({}, None)

    assert [item["component"] for item in result["components"]] == ["worker", "auth"]
    assert [item["queue"] for item in result["queues"]] == ["work", "dlq"]
