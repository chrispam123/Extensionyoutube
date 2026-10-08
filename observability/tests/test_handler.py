import os
from datetime import datetime, timedelta, timezone

from observability.backend import handler

DEFAULT_VALUES = {
    f"lambda_{component}_{metric}": 0
    for component in handler.DEFAULT_COMPONENTS
    for metric in ("invocations", "errors", "throttles", "duration_p95_ms")
}
DEFAULT_VALUES.update(
    {
        f"sqs_{queue.replace('-', '_')}_{metric}": 0
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


class FakeTable:
    def __init__(self, items_by_status=None):
        self.items_by_status = items_by_status or {}

    def query(self, **kwargs):
        status = kwargs["ExpressionAttributeValues"][":status"]
        return {"Items": self.items_by_status.get(status, [])}


class FakeDynamoDB:
    def __init__(self, items_by_status=None):
        self.table = FakeTable(items_by_status)

    def Table(self, table_name):
        assert table_name == "extension-dynamo-table-develop"
        return self.table


def _values(**overrides):
    values = DEFAULT_VALUES.copy()
    values.update(overrides)
    return values


def _job(status, age_minutes):
    timestamp = (
        datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    ).isoformat()
    return {
        "PK": "USER#test",
        "SK": f"JOB#{status}",
        "jobId": status,
        "status": status,
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }


def _patch_clients(monkeypatch, values=None, items_by_status=None):
    monkeypatch.setenv("ENVIRONMENT", "develop")
    monkeypatch.setattr(handler, "cloudwatch", FakeCloudWatch(values or _values()))
    monkeypatch.setattr(handler, "dynamodb", FakeDynamoDB(items_by_status))


def test_all_lambdas_queues_and_jobs_are_healthy(monkeypatch):
    _patch_clients(monkeypatch)

    result = handler.lambda_handler({}, None)

    assert result["status"] == "healthy"
    assert len(result["components"]) == 6
    assert len(result["queues"]) == 4
    assert result["jobs"]["metrics"]["counts_by_status"]["FAILED"] == 0


def test_worker_error_rate_is_warning(monkeypatch):
    _patch_clients(
        monkeypatch,
        _values(lambda_worker_invocations=100, lambda_worker_errors=2),
    )

    result = handler.lambda_handler({}, None)
    worker = next(
        item for item in result["components"] if item["component"] == "worker"
    )

    assert result["status"] == "warning"
    assert worker["status"] == "warning"


def test_dlq_with_visible_messages_is_critical(monkeypatch):
    _patch_clients(monkeypatch, _values(sqs_dlq_visible=1))

    result = handler.lambda_handler({}, None)
    dlq = next(item for item in result["queues"] if item["queue"] == "dlq")

    assert result["status"] == "critical"
    assert dlq["status"] == "critical"


def test_failed_job_is_critical(monkeypatch):
    _patch_clients(monkeypatch, items_by_status={"FAILED": [_job("FAILED", 2)]})

    result = handler.lambda_handler({}, None)

    assert result["status"] == "critical"
    assert result["jobs"]["status"] == "critical"
    assert result["jobs"]["metrics"]["counts_by_status"]["FAILED"] == 1


def test_stale_pending_job_is_warning(monkeypatch):
    _patch_clients(monkeypatch, items_by_status={"PENDING": [_job("PENDING", 16)]})

    result = handler.lambda_handler({}, None)

    assert result["status"] == "warning"
    assert result["jobs"]["status"] == "warning"
    assert result["jobs"]["metrics"]["stale_pending_or_initializing"] == 1


def test_stale_running_job_is_critical(monkeypatch):
    _patch_clients(monkeypatch, items_by_status={"RUNNING": [_job("RUNNING", 31)]})

    result = handler.lambda_handler({}, None)

    assert result["status"] == "critical"
    assert result["jobs"]["metrics"]["stale_running"] == 1


def test_components_and_queues_can_be_restricted(monkeypatch):
    monkeypatch.setenv("OBSERVED_COMPONENTS", "worker,auth")
    monkeypatch.setenv("OBSERVED_QUEUES", "work,dlq")
    _patch_clients(monkeypatch)

    result = handler.lambda_handler({}, None)

    assert [item["component"] for item in result["components"]] == ["worker", "auth"]
    assert [item["queue"] for item in result["queues"]] == ["work", "dlq"]
