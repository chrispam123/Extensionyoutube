"""Read-only metrics handler for Lambdas, queues and jobs."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

METRIC_NAMESPACE = "AWS/Lambda"
QUEUE_METRIC_NAMESPACE = "AWS/SQS"
WINDOW_MINUTES = 5
DEFAULT_TIMEOUT_MS = 60_000
DEFAULT_COMPONENTS = ("auth", "upload", "dispatcher", "worker", "status", "resumer")
DEFAULT_QUEUES = ("work", "dlq", "ingestion", "ingestion-dlq")
JOB_STATUSES = ("INITIALIZING", "PENDING", "RUNNING", "FAILED", "DONE", "PAUSED_QUOTA")
PENDING_MAX_AGE_SECONDS = 15 * 60
RUNNING_MAX_AGE_SECONDS = 30 * 60
COMPONENT_TIMEOUTS_MS = {
    "auth": 15_000,
    "upload": 10_000,
    "dispatcher": 10_000,
    "worker": 60_000,
    "status": 5_000,
    "resumer": 30_000,
}
QUEUE_DEFINITIONS = {
    "work": ("extension-sqs-work", False),
    "dlq": ("extension-sqs-dlq", True),
    "ingestion": ("extension-sqs-ingestion", False),
    "ingestion-dlq": ("extension-sqs-ingestion-dlq", True),
}
STATUS_PRIORITY = {"healthy": 0, "warning": 1, "critical": 2}
QUEUE_WARNING_VISIBLE = 10
QUEUE_CRITICAL_AGE_SECONDS = 30 * 60

cloudwatch = None
dynamodb = None


def _cloudwatch_client():
    global cloudwatch
    if cloudwatch is None:
        cloudwatch = boto3.client("cloudwatch")
    return cloudwatch


def _dynamodb_resource():
    global dynamodb
    if dynamodb is None:
        dynamodb = boto3.resource("dynamodb")
    return dynamodb


def _configured_names(
    environment_variable: str, defaults: tuple[str, ...]
) -> list[str]:
    configured = os.getenv(environment_variable)
    return [
        name.strip()
        for name in (configured.split(",") if configured else defaults)
        if name.strip()
    ]


def _observed_components(environment: str) -> list[dict[str, Any]]:
    return [
        {
            "component": component,
            "function_name": f"extension-{component}-{environment}",
            "timeout_ms": COMPONENT_TIMEOUTS_MS.get(component, DEFAULT_TIMEOUT_MS),
        }
        for component in _configured_names("OBSERVED_COMPONENTS", DEFAULT_COMPONENTS)
    ]


def _observed_queues(environment: str) -> list[dict[str, Any]]:
    queues = []
    for queue_id in _configured_names("OBSERVED_QUEUES", DEFAULT_QUEUES):
        prefix, is_dlq = QUEUE_DEFINITIONS.get(
            queue_id, (f"extension-sqs-{queue_id}", "dlq" in queue_id)
        )
        queues.append(
            {
                "queue": queue_id,
                "queue_name": f"{prefix}-{environment}",
                "is_dlq": is_dlq,
            }
        )
    return queues


def _queue_metric_prefix(queue_id: str) -> str:
    return queue_id.replace("-", "_")


def _metric_queries(
    components: list[dict[str, Any]], queues: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    queries = []
    lambda_metrics = [
        ("invocations", "Invocations", "Sum"),
        ("errors", "Errors", "Sum"),
        ("throttles", "Throttles", "Sum"),
        ("duration_p95_ms", "Duration", "p95"),
    ]
    queue_metrics = [
        ("visible", "ApproximateNumberOfMessagesVisible", "Maximum"),
        ("not_visible", "ApproximateNumberOfMessagesNotVisible", "Maximum"),
        ("oldest_age_s", "ApproximateAgeOfOldestMessage", "Maximum"),
    ]

    for item in components:
        dimensions = [{"Name": "FunctionName", "Value": item["function_name"]}]
        for metric_id, metric_name, statistic in lambda_metrics:
            queries.append(
                {
                    "Id": f"lambda_{item['component']}_{metric_id}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": METRIC_NAMESPACE,
                            "MetricName": metric_name,
                            "Dimensions": dimensions,
                        },
                        "Period": WINDOW_MINUTES * 60,
                        "Stat": statistic,
                    },
                    "ReturnData": True,
                }
            )

    for item in queues:
        dimensions = [{"Name": "QueueName", "Value": item["queue_name"]}]
        metric_prefix = _queue_metric_prefix(item["queue"])
        for metric_id, metric_name, statistic in queue_metrics:
            queries.append(
                {
                    "Id": f"sqs_{metric_prefix}_{metric_id.replace('-', '_')}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": QUEUE_METRIC_NAMESPACE,
                            "MetricName": metric_name,
                            "Dimensions": dimensions,
                        },
                        "Period": WINDOW_MINUTES * 60,
                        "Stat": statistic,
                    },
                    "ReturnData": True,
                }
            )

    return queries


def _metric_values(response: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for result in response.get("MetricDataResults", []):
        data_points = result.get("Values", [])
        values[result["Id"]] = float(data_points[0]) if data_points else 0.0
    return values


def _lambda_status(
    *,
    error_rate: float,
    errors: float,
    throttles: float,
    duration_p95_ms: float,
    timeout_ms: int,
) -> str:
    if throttles > 0 or errors >= 5:
        return "critical"
    if error_rate > 1 or duration_p95_ms > timeout_ms * 0.8:
        return "warning"
    return "healthy"


def _component_result(
    component: dict[str, Any], values: dict[str, float]
) -> dict[str, Any]:
    prefix = f"lambda_{component['component']}"
    invocations = values.get(f"{prefix}_invocations", 0.0)
    errors = values.get(f"{prefix}_errors", 0.0)
    throttles = values.get(f"{prefix}_throttles", 0.0)
    duration_p95_ms = values.get(f"{prefix}_duration_p95_ms", 0.0)
    error_rate = (errors / invocations * 100) if invocations else 0.0
    status = _lambda_status(
        error_rate=error_rate,
        errors=errors,
        throttles=throttles,
        duration_p95_ms=duration_p95_ms,
        timeout_ms=component["timeout_ms"],
    )

    return {
        "component": component["component"],
        "function_name": component["function_name"],
        "status": status,
        "metrics": {
            "error_rate": round(error_rate, 2),
            "invocations": int(invocations),
            "errors": int(errors),
            "throttles": int(throttles),
            "duration_p95_ms": round(duration_p95_ms, 2),
        },
    }


def _queue_result(queue: dict[str, Any], values: dict[str, float]) -> dict[str, Any]:
    prefix = f"sqs_{_queue_metric_prefix(queue['queue'])}"
    visible = values.get(f"{prefix}_visible", 0.0)
    not_visible = values.get(f"{prefix}_not_visible", 0.0)
    oldest_age_s = values.get(f"{prefix}_oldest_age_s", 0.0)

    if queue["is_dlq"] and visible > 0:
        status = "critical"
    elif oldest_age_s > QUEUE_CRITICAL_AGE_SECONDS:
        status = "critical"
    elif visible > QUEUE_WARNING_VISIBLE:
        status = "warning"
    else:
        status = "healthy"

    return {
        "queue": queue["queue"],
        "queue_name": queue["queue_name"],
        "type": "dlq" if queue["is_dlq"] else "primary",
        "status": status,
        "metrics": {
            "visible": int(visible),
            "not_visible": int(not_visible),
            "oldest_age_seconds": int(oldest_age_s),
        },
    }


def _parse_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
            timezone.utc
        )
    except ValueError:
        return None


def _query_jobs_by_status(table: Any, status: str) -> list[dict[str, Any]]:
    items = []
    query_kwargs = {
        "IndexName": "StatusIndex",
        "KeyConditionExpression": "#status = :status",
        "ExpressionAttributeNames": {"#status": "status"},
        "ExpressionAttributeValues": {":status": status},
        "ProjectionExpression": "PK, SK, jobId, #status, createdAt, updatedAt, expiresAt",
    }
    response = table.query(**query_kwargs)
    items.extend(response.get("Items", []))
    while response.get("LastEvaluatedKey"):
        response = table.query(
            **query_kwargs, ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        items.extend(response.get("Items", []))
    return items


def _job_result(table: Any, now: datetime) -> dict[str, Any]:
    items_by_status = {
        status: _query_jobs_by_status(table, status) for status in JOB_STATUSES
    }
    counts = {status: len(items) for status, items in items_by_status.items()}
    stale_pending = 0
    stale_running = 0
    oldest_age_seconds: dict[str, int] = {}

    for status, items in items_by_status.items():
        ages = []
        for item in items:
            timestamp = _parse_timestamp(item.get("updatedAt")) or _parse_timestamp(
                item.get("createdAt")
            )
            if timestamp:
                ages.append(max(0, int((now - timestamp).total_seconds())))
        if ages:
            oldest_age_seconds[status] = max(ages)
            if status in ("INITIALIZING", "PENDING"):
                stale_pending += sum(age > PENDING_MAX_AGE_SECONDS for age in ages)
            if status == "RUNNING":
                stale_running += sum(age > RUNNING_MAX_AGE_SECONDS for age in ages)

    if counts["FAILED"] > 0 or stale_running > 0:
        status = "critical"
    elif stale_pending > 0 or counts["PAUSED_QUOTA"] > 0:
        status = "warning"
    else:
        status = "healthy"

    return {
        "status": status,
        "metrics": {
            "counts_by_status": counts,
            "stale_pending_or_initializing": stale_pending,
            "stale_running": stale_running,
            "oldest_age_seconds_by_status": oldest_age_seconds,
        },
    }


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """Return a five-minute health summary for Lambdas, queues and jobs."""
    del context
    event = event or {}
    environment = os.getenv("ENVIRONMENT", event.get("environment", "develop"))
    components = _observed_components(environment)
    queues = _observed_queues(environment)
    table_name = os.getenv("DYNAMODB_TABLE", f"extension-dynamo-table-{environment}")

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=WINDOW_MINUTES)
    response = _cloudwatch_client().get_metric_data(
        MetricDataQueries=_metric_queries(components, queues),
        StartTime=start_time,
        EndTime=end_time,
        ScanBy="TimestampDescending",
    )
    values = _metric_values(response)
    component_results = [
        _component_result(component, values) for component in components
    ]
    queue_results = [_queue_result(queue, values) for queue in queues]
    job_results = _job_result(_dynamodb_resource().Table(table_name), end_time)
    statuses = [
        result["status"] for result in [*component_results, *queue_results, job_results]
    ]
    overall_status = max(statuses, key=STATUS_PRIORITY.get, default="healthy")

    return {
        "environment": environment,
        "status": overall_status,
        "window_minutes": WINDOW_MINUTES,
        "components": component_results,
        "queues": queue_results,
        "jobs": job_results,
        "observed_at": end_time.isoformat(),
    }
