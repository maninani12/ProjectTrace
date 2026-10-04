# Observability

The API adds X-Request-ID and records structured method/path/status/duration fields through the projecttrace logger. Raw request bodies, source and credentials are not included. Uvicorn process logs are available during native development.

OpenTelemetry API is present through the framework dependencies, but an SDK/exporter, distributed spans, tenant metrics dashboards, queue saturation metrics and production alerting are not configured. Do not claim exported tracing or production SRE visibility. Health/readiness and measured local benchmark reports are the currently verified signals.
