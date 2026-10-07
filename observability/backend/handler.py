"""Read-only CloudWatch metrics handler for the observability MVP."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

METRIC_NAMESPACE = "AWS/Lambda"
WINDOW_MINUTES = 5
DEFAULT_WORKER_TIMEOUT_MS = 60_000

cloudwatch = None


def _cloudwatch_client():
    global cloudwatch
    if cloudwatch is None:
        cloudwatch = boto3.client("cloudwatch")
    return cloudwatch


def _metric_queries(function_name: str) -> list[dict[str, Any]]:
    dimensions = [{"Name": "FunctionName", "Value": function_name}]
    metrics = [
        ("invocations", "Invocations", "Sum"),
        ("errors", "Errors", "Sum"),
        ("throttles", "Throttles", "Sum"),
        ("duration_p95_ms", "Duration", "p95"),
    ]

    return [
        {
            "Id": metric_id,
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
        for metric_id, metric_name, statistic in metrics
    ]


def _metric_values(response: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for result in response.get("MetricDataResults", []):
        data_points = result.get("Values", [])
        values[result["Id"]] = float(data_points[0]) if data_points else 0.0
    return values


def _status(
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


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """Return the current five-minute health summary for the worker Lambda."""
    del context
    event = event or {}
    environment = os.getenv("ENVIRONMENT", event.get("environment", "develop"))
    function_name = os.getenv(
        "OBSERVED_WORKER_FUNCTION", f"extension-worker-{environment}"
    )
    timeout_ms = int(
        os.getenv("OBSERVED_WORKER_TIMEOUT_MS", str(DEFAULT_WORKER_TIMEOUT_MS))
    )

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=WINDOW_MINUTES)
    response = _cloudwatch_client().get_metric_data(
        MetricDataQueries=_metric_queries(function_name),
        StartTime=start_time,
        EndTime=end_time,
        ScanBy="TimestampDescending",
    )
    metrics = _metric_values(response)

    invocations = metrics.get("invocations", 0.0)
    errors = metrics.get("errors", 0.0)
    error_rate = (errors / invocations * 100) if invocations else 0.0

    return {
        "environment": environment,
        "component": "worker",
        "function_name": function_name,
        "status": _status(
            error_rate=error_rate,
            errors=errors,
            throttles=metrics.get("throttles", 0.0),
            duration_p95_ms=metrics.get("duration_p95_ms", 0.0),
            timeout_ms=timeout_ms,
        ),
        "window_minutes": WINDOW_MINUTES,
        "metrics": {
            "error_rate": round(error_rate, 2),
            "invocations": int(invocations),
            "errors": int(errors),
            "throttles": int(metrics.get("throttles", 0.0)),
            "duration_p95_ms": round(metrics.get("duration_p95_ms", 0.0), 2),
        },
        "observed_at": end_time.isoformat(),
    }
