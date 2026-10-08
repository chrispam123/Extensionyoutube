"""Read-only CloudWatch metrics handler for the observability MVP."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

METRIC_NAMESPACE = "AWS/Lambda"
WINDOW_MINUTES = 5
DEFAULT_TIMEOUT_MS = 60_000
DEFAULT_COMPONENTS = ("auth", "upload", "dispatcher", "worker", "status", "resumer")
COMPONENT_TIMEOUTS_MS = {
    "auth": 15_000,
    "upload": 10_000,
    "dispatcher": 10_000,
    "worker": 60_000,
    "status": 5_000,
    "resumer": 30_000,
}
STATUS_PRIORITY = {"healthy": 0, "warning": 1, "critical": 2}

cloudwatch = None


def _cloudwatch_client():
    global cloudwatch
    if cloudwatch is None:
        cloudwatch = boto3.client("cloudwatch")
    return cloudwatch


def _observed_components(environment: str) -> list[dict[str, Any]]:
    configured = os.getenv("OBSERVED_COMPONENTS")
    component_names = [
        component.strip()
        for component in (configured.split(",") if configured else DEFAULT_COMPONENTS)
        if component.strip()
    ]

    return [
        {
            "component": component,
            "function_name": f"extension-{component}-{environment}",
            "timeout_ms": COMPONENT_TIMEOUTS_MS.get(component, DEFAULT_TIMEOUT_MS),
        }
        for component in component_names
    ]


def _metric_queries(components: list[dict[str, Any]]) -> list[dict[str, Any]]:
    metrics = [
        ("invocations", "Invocations", "Sum"),
        ("errors", "Errors", "Sum"),
        ("throttles", "Throttles", "Sum"),
        ("duration_p95_ms", "Duration", "p95"),
    ]
    queries = []

    for item in components:
        dimensions = [{"Name": "FunctionName", "Value": item["function_name"]}]
        for metric_id, metric_name, statistic in metrics:
            queries.append(
                {
                    "Id": f"{item['component']}_{metric_id}",
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

    return queries


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


def _component_result(
    component: dict[str, Any], values: dict[str, float]
) -> dict[str, Any]:
    prefix = component["component"]
    invocations = values.get(f"{prefix}_invocations", 0.0)
    errors = values.get(f"{prefix}_errors", 0.0)
    throttles = values.get(f"{prefix}_throttles", 0.0)
    duration_p95_ms = values.get(f"{prefix}_duration_p95_ms", 0.0)
    error_rate = (errors / invocations * 100) if invocations else 0.0
    status = _status(
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


def lambda_handler(event: dict[str, Any] | None, context: Any) -> dict[str, Any]:
    """Return a five-minute health summary for all configured Lambda components."""
    del context
    event = event or {}
    environment = os.getenv("ENVIRONMENT", event.get("environment", "develop"))
    components = _observed_components(environment)

    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(minutes=WINDOW_MINUTES)
    response = _cloudwatch_client().get_metric_data(
        MetricDataQueries=_metric_queries(components),
        StartTime=start_time,
        EndTime=end_time,
        ScanBy="TimestampDescending",
    )
    values = _metric_values(response)
    component_results = [
        _component_result(component, values) for component in components
    ]
    overall_status = max(
        (result["status"] for result in component_results),
        key=STATUS_PRIORITY.get,
        default="healthy",
    )

    return {
        "environment": environment,
        "status": overall_status,
        "window_minutes": WINDOW_MINUTES,
        "components": component_results,
        "observed_at": end_time.isoformat(),
    }
