"""Read-only metrics handler for Lambdas, queues and jobs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

METRIC_NAMESPACE = "AWS/Lambda"
QUEUE_METRIC_NAMESPACE = "AWS/SQS"
API_GATEWAY_METRIC_NAMESPACE = "AWS/ApiGateway"
EVENTBRIDGE_METRIC_NAMESPACE = "AWS/Events"
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
EVENTBRIDGE_WINDOW_MINUTES = 90
API_MIN_REQUESTS_FOR_ERROR_RATE = 10
API_CRITICAL_5XX_RATE = 1.0
API_WARNING_LATENCY_MS = 2_000

cloudwatch = None
dynamodb = None
s3 = None
events = None
REQUIRED_GROUP = "observability-readonly"


def _api_gateway_request(event: dict[str, Any]) -> bool:
    request_context = event.get("requestContext")
    return isinstance(request_context, dict) and isinstance(
        request_context.get("http"), dict
    )


def _authorized_for_observability(event: dict[str, Any]) -> bool:
    if not _api_gateway_request(event):
        return True

    request_context = event.get("requestContext", {})
    authorizer = request_context.get("authorizer", {})
    jwt = authorizer.get("jwt", {})
    claims = jwt.get("claims", {})
    raw_groups = claims.get("cognito:groups", "")
    if isinstance(raw_groups, str):
        try:
            groups = json.loads(raw_groups)
            if not isinstance(groups, list):
                groups = raw_groups.replace(",", " ").split()
        except json.JSONDecodeError:
            groups = raw_groups.replace(",", " ").split()
    elif isinstance(raw_groups, list):
        groups = raw_groups
    else:
        groups = []

    required_group = os.getenv("OBSERVABILITY_REQUIRED_GROUP", REQUIRED_GROUP)
    return required_group in groups


def _forbidden_response() -> dict[str, Any]:
    return {
        "statusCode": 403,
        "headers": {"content-type": "application/json"},
        "body": json.dumps({"message": "Observability access is not authorized."}),
    }


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


def _s3_client():
    global s3
    if s3 is None:
        s3 = boto3.client("s3")
    return s3


def _events_client():
    global events
    if events is None:
        events = boto3.client("events")
    return events


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


def _observed_api_gateway(environment: str) -> dict[str, str] | None:
    api_id = os.getenv("API_GATEWAY_ID")
    if not api_id:
        return None
    return {
        "api_id": api_id,
        "stage": os.getenv("API_GATEWAY_STAGE", environment),
    }


def _observed_eventbridge(environment: str) -> dict[str, str] | None:
    rule_name = os.getenv("EVENTBRIDGE_RULE_NAME")
    if not rule_name:
        return None
    return {
        "rule_name": rule_name,
        "target_function": os.getenv(
            "EVENTBRIDGE_TARGET_FUNCTION", f"extension-resumer-{environment}"
        ),
    }


def _queue_metric_prefix(queue_id: str) -> str:
    return queue_id.replace("-", "_")


def _metric_queries(
    components: list[dict[str, Any]],
    queues: list[dict[str, Any]],
    api_gateway: dict[str, str] | None,
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
    api_metrics = [
        ("requests", "Count", "Sum"),
        ("errors_5xx", "5XXError", "Sum"),
        ("errors_4xx", "4XXError", "Sum"),
        ("latency_p95_ms", "Latency", "p95"),
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

    if api_gateway:
        dimensions = [
            {"Name": "ApiId", "Value": api_gateway["api_id"]},
            {"Name": "Stage", "Value": api_gateway["stage"]},
        ]
        for metric_id, metric_name, statistic in api_metrics:
            queries.append(
                {
                    "Id": f"api_{metric_id}",
                    "MetricStat": {
                        "Metric": {
                            "Namespace": API_GATEWAY_METRIC_NAMESPACE,
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


def _metric_totals(response: dict[str, Any]) -> dict[str, float]:
    return {
        result["Id"]: sum(float(value) for value in result.get("Values", []))
        for result in response.get("MetricDataResults", [])
    }


def _eventbridge_metric_queries(rule_name: str) -> list[dict[str, Any]]:
    dimensions = [{"Name": "RuleName", "Value": rule_name}]
    metrics = [
        ("invocations", "Invocations"),
        ("failed_invocations", "FailedInvocations"),
    ]
    return [
        {
            "Id": f"eventbridge_{metric_id}",
            "MetricStat": {
                "Metric": {
                    "Namespace": EVENTBRIDGE_METRIC_NAMESPACE,
                    "MetricName": metric_name,
                    "Dimensions": dimensions,
                },
                "Period": WINDOW_MINUTES * 60,
                "Stat": "Sum",
            },
            "ReturnData": True,
        }
        for metric_id, metric_name in metrics
    ]


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
        "ExpressionAttributeNames": {"#status": "status", "#type": "type"},
        "ExpressionAttributeValues": {":status": status},
        "ProjectionExpression": "PK, SK, jobId, userId, #status, #type, createdAt, updatedAt, expiresAt",
    }
    response = table.query(**query_kwargs)
    items.extend(response.get("Items", []))
    while response.get("LastEvaluatedKey"):
        response = table.query(
            **query_kwargs, ExclusiveStartKey=response["LastEvaluatedKey"]
        )
        items.extend(response.get("Items", []))
    return items


def _job_result(
    table: Any, now: datetime, s3_client: Any | None, bucket_name: str | None
) -> dict[str, Any]:
    items_by_status = {
        status: _query_jobs_by_status(table, status) for status in JOB_STATUSES
    }
    counts = {status: len(items) for status, items in items_by_status.items()}
    stale_pending = 0
    stale_running = 0
    done_exports_checked = 0
    done_exports_missing = 0
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

    if s3_client and bucket_name:
        for item in items_by_status["DONE"]:
            if item.get("type", "EXPORT") != "EXPORT":
                continue
            done_exports_checked += 1
            key = f"exports/{item['userId']}/{item['jobId']}.json"
            try:
                s3_client.head_object(Bucket=bucket_name, Key=key)
            except s3_client.exceptions.ClientError as error:
                error_code = error.response.get("Error", {}).get("Code")
                if error_code in ("404", "NoSuchKey", "NotFound"):
                    done_exports_missing += 1
                else:
                    raise

    if counts["FAILED"] > 0 or stale_running > 0 or done_exports_missing > 0:
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
            "done_exports_checked": done_exports_checked,
            "done_exports_missing": done_exports_missing,
            "oldest_age_seconds_by_status": oldest_age_seconds,
        },
    }


def _api_gateway_result(
    api_gateway: dict[str, str] | None, values: dict[str, float]
) -> dict[str, Any] | None:
    if not api_gateway:
        return None

    requests = values.get("api_requests", 0.0)
    errors_5xx = values.get("api_errors_5xx", 0.0)
    errors_4xx = values.get("api_errors_4xx", 0.0)
    latency_p95_ms = values.get("api_latency_p95_ms", 0.0)
    error_rate_5xx = (errors_5xx / requests * 100) if requests else 0.0

    if (
        requests >= API_MIN_REQUESTS_FOR_ERROR_RATE
        and error_rate_5xx > API_CRITICAL_5XX_RATE
    ):
        status = "critical"
    elif latency_p95_ms > API_WARNING_LATENCY_MS:
        status = "warning"
    else:
        status = "healthy"

    return {
        "api_id": api_gateway["api_id"],
        "stage": api_gateway["stage"],
        "status": status,
        "metrics": {
            "requests": int(requests),
            "errors_5xx": int(errors_5xx),
            "errors_4xx": int(errors_4xx),
            "error_rate_5xx": round(error_rate_5xx, 2),
            "latency_p95_ms": round(latency_p95_ms, 2),
        },
    }


def _eventbridge_result(
    eventbridge: dict[str, str] | None,
    events_client: Any,
    metric_values: dict[str, float],
) -> dict[str, Any] | None:
    if not eventbridge:
        return None

    rule_name = eventbridge["rule_name"]
    rule = events_client.describe_rule(Name=rule_name)
    targets = events_client.list_targets_by_rule(Rule=rule_name).get("Targets", [])
    target_suffix = f":function:{eventbridge['target_function']}"
    target_configured = any(
        str(target.get("Arn", "")).endswith(target_suffix) for target in targets
    )
    invocations = metric_values.get("eventbridge_invocations", 0.0)
    failed_invocations = metric_values.get("eventbridge_failed_invocations", 0.0)
    schedule_ok = rule.get("ScheduleExpression") == "rate(1 hour)"
    enabled = rule.get("State") == "ENABLED"

    if not enabled or not schedule_ok or not target_configured:
        status = "critical"
    elif failed_invocations > 0:
        status = "critical"
    elif invocations == 0:
        status = "warning"
    else:
        status = "healthy"

    return {
        "rule_name": rule_name,
        "state": rule.get("State"),
        "schedule_expression": rule.get("ScheduleExpression"),
        "target_function": eventbridge["target_function"],
        "target_configured": target_configured,
        "status": status,
        "metrics": {
            "window_minutes": EVENTBRIDGE_WINDOW_MINUTES,
            "invocations": int(invocations),
            "failed_invocations": int(failed_invocations),
        },
    }


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """Return a five-minute health summary for Lambdas, queues and jobs."""
    del context
    event = event or {}
    if not _authorized_for_observability(event):
        return _forbidden_response()
    environment = os.getenv("ENVIRONMENT", event.get("environment", "develop"))
    components = _observed_components(environment)
    queues = _observed_queues(environment)
    api_gateway = _observed_api_gateway(environment)
    eventbridge = _observed_eventbridge(environment)
    table_name = os.getenv("DYNAMODB_TABLE", f"extension-dynamo-table-{environment}")
    bucket_name = os.getenv("S3_BUCKET")

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=WINDOW_MINUTES)
    response = _cloudwatch_client().get_metric_data(
        MetricDataQueries=_metric_queries(components, queues, api_gateway),
        StartTime=start_time,
        EndTime=end_time,
        ScanBy="TimestampDescending",
    )
    values = _metric_values(response)
    component_results = [
        _component_result(component, values) for component in components
    ]
    queue_results = [_queue_result(queue, values) for queue in queues]
    api_result = _api_gateway_result(api_gateway, values)
    eventbridge_values = {}
    if eventbridge:
        event_end_time = end_time
        event_start_time = event_end_time - timedelta(
            minutes=EVENTBRIDGE_WINDOW_MINUTES
        )
        event_response = _cloudwatch_client().get_metric_data(
            MetricDataQueries=_eventbridge_metric_queries(eventbridge["rule_name"]),
            StartTime=event_start_time,
            EndTime=event_end_time,
            ScanBy="TimestampDescending",
        )
        eventbridge_values = _metric_totals(event_response)
    eventbridge_result = _eventbridge_result(
        eventbridge, _events_client() if eventbridge else None, eventbridge_values
    )
    job_results = _job_result(
        _dynamodb_resource().Table(table_name),
        end_time,
        _s3_client() if bucket_name else None,
        bucket_name,
    )
    status_results = [*component_results, *queue_results, job_results]
    if api_result:
        status_results.append(api_result)
    if eventbridge_result:
        status_results.append(eventbridge_result)
    statuses = [result["status"] for result in status_results]
    overall_status = max(statuses, key=STATUS_PRIORITY.get, default="healthy")

    return {
        "environment": environment,
        "status": overall_status,
        "window_minutes": WINDOW_MINUTES,
        "components": component_results,
        "queues": queue_results,
        "api_gateway": api_result,
        "eventbridge": eventbridge_result,
        "jobs": job_results,
        "observed_at": end_time.isoformat(),
    }
