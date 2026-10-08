import os
from datetime import datetime, timedelta, timezone

from botocore.exceptions import ClientError

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
DEFAULT_VALUES.update(
    {"eventbridge_invocations": 1, "eventbridge_failed_invocations": 0}
)
DEFAULT_VALUES.update(
    {
        "api_requests": 0,
        "api_errors_5xx": 0,
        "api_errors_4xx": 0,
        "api_latency_p95_ms": 0,
    }
)


class FakeCloudWatch:
    def __init__(self, values):
        self.values = values

    def get_metric_data(self, **kwargs):
        if any(
            query["Id"].startswith("eventbridge_")
            for query in kwargs["MetricDataQueries"]
        ):
            assert len(kwargs["MetricDataQueries"]) == 2
        else:
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
            api_query_count = 4 if os.getenv("API_GATEWAY_ID") else 0
            assert (
                len(kwargs["MetricDataQueries"])
                == component_count * 4 + queue_count * 3 + api_query_count
            )
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


class FakeEvents:
    def __init__(
        self,
        state="ENABLED",
        schedule="rate(1 hour)",
        target_function="extension-resumer-develop",
    ):
        self.state = state
        self.schedule = schedule
        self.target_function = target_function

    def describe_rule(self, **kwargs):
        assert kwargs["Name"] == "extension-resumer-cron-develop"
        return {"State": self.state, "ScheduleExpression": self.schedule}

    def list_targets_by_rule(self, **kwargs):
        assert kwargs["Rule"] == "extension-resumer-cron-develop"
        return {
            "Targets": [
                {"Arn": f"arn:aws:lambda:us-east-1:123:function:{self.target_function}"}
            ]
        }


class FakeS3:
    exceptions = type("Exceptions", (), {"ClientError": ClientError})

    def __init__(self, missing_keys=None):
        self.missing_keys = missing_keys or set()

    def head_object(self, *, Bucket, Key):
        assert Bucket == "extension-s3-uploads-develop"
        if Key in self.missing_keys:
            raise ClientError(
                {"Error": {"Code": "404"}},
                "HeadObject",
            )
        return {"ResponseMetadata": {"HTTPStatusCode": 200}}


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
        "userId": "user-test",
        "type": "EXPORT",
        "status": status,
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }


def _patch_clients(
    monkeypatch,
    values=None,
    items_by_status=None,
    missing_s3_keys=None,
    events_client=None,
):
    monkeypatch.setenv("ENVIRONMENT", "develop")
    monkeypatch.setenv("API_GATEWAY_ID", "api-test")
    monkeypatch.setenv("API_GATEWAY_STAGE", "develop")
    monkeypatch.setenv("S3_BUCKET", "extension-s3-uploads-develop")
    monkeypatch.setenv("EVENTBRIDGE_RULE_NAME", "extension-resumer-cron-develop")
    monkeypatch.setenv("EVENTBRIDGE_TARGET_FUNCTION", "extension-resumer-develop")
    monkeypatch.setattr(handler, "cloudwatch", FakeCloudWatch(values or _values()))
    monkeypatch.setattr(handler, "dynamodb", FakeDynamoDB(items_by_status))
    monkeypatch.setattr(handler, "s3", FakeS3(missing_s3_keys))
    monkeypatch.setattr(handler, "events", events_client or FakeEvents())


def test_all_lambdas_queues_and_jobs_are_healthy(monkeypatch):
    _patch_clients(monkeypatch)

    result = handler.lambda_handler({}, None)

    assert result["status"] == "healthy"
    assert len(result["components"]) == 6
    assert len(result["queues"]) == 4
    assert result["jobs"]["metrics"]["counts_by_status"]["FAILED"] == 0
    assert result["eventbridge"]["status"] == "healthy"


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


def test_api_gateway_5xx_rate_is_critical(monkeypatch):
    _patch_clients(monkeypatch, _values(api_requests=100, api_errors_5xx=2))

    result = handler.lambda_handler({}, None)

    assert result["status"] == "critical"
    assert result["api_gateway"]["status"] == "critical"
    assert result["api_gateway"]["metrics"]["error_rate_5xx"] == 2


def test_api_gateway_latency_is_warning(monkeypatch):
    _patch_clients(monkeypatch, _values(api_requests=20, api_latency_p95_ms=2001))

    result = handler.lambda_handler({}, None)

    assert result["status"] == "warning"
    assert result["api_gateway"]["status"] == "warning"


def test_eventbridge_without_recent_invocation_is_warning(monkeypatch):
    _patch_clients(monkeypatch, _values(eventbridge_invocations=0))

    result = handler.lambda_handler({}, None)

    assert result["status"] == "warning"
    assert result["eventbridge"]["status"] == "warning"
    assert result["eventbridge"]["metrics"]["window_minutes"] == 90


def test_eventbridge_failed_invocation_is_critical(monkeypatch):
    _patch_clients(monkeypatch, _values(eventbridge_failed_invocations=1))

    result = handler.lambda_handler({}, None)

    assert result["status"] == "critical"
    assert result["eventbridge"]["status"] == "critical"


def test_disabled_eventbridge_rule_is_critical(monkeypatch):
    _patch_clients(monkeypatch, events_client=FakeEvents(state="DISABLED"))

    result = handler.lambda_handler({}, None)

    assert result["status"] == "critical"
    assert result["eventbridge"]["status"] == "critical"


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


def test_done_export_with_s3_object_is_healthy(monkeypatch):
    _patch_clients(monkeypatch, items_by_status={"DONE": [_job("DONE", 2)]})

    result = handler.lambda_handler({}, None)

    assert result["status"] == "healthy"
    assert result["jobs"]["metrics"]["done_exports_checked"] == 1
    assert result["jobs"]["metrics"]["done_exports_missing"] == 0


def test_done_export_without_s3_object_is_critical(monkeypatch):
    _patch_clients(
        monkeypatch,
        items_by_status={"DONE": [_job("DONE", 2)]},
        missing_s3_keys={"exports/user-test/DONE.json"},
    )

    result = handler.lambda_handler({}, None)

    assert result["status"] == "critical"
    assert result["jobs"]["status"] == "critical"
    assert result["jobs"]["metrics"]["done_exports_missing"] == 1


def test_components_and_queues_can_be_restricted(monkeypatch):
    monkeypatch.setenv("OBSERVED_COMPONENTS", "worker,auth")
    monkeypatch.setenv("OBSERVED_QUEUES", "work,dlq")
    _patch_clients(monkeypatch)

    result = handler.lambda_handler({}, None)

    assert [item["component"] for item in result["components"]] == ["worker", "auth"]
    assert [item["queue"] for item in result["queues"]] == ["work", "dlq"]
