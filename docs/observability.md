# Observability

The API adds X-Request-ID and records structured method/path/status/duration fields through the projecttrace logger. Raw request bodies, source and credentials are not included. Uvicorn process logs are available during native development.

OpenTelemetry API is present through the framework dependencies, but an SDK/exporter, distributed spans, tenant metrics dashboards, queue saturation metrics and production alerting are not configured. Do not claim exported tracing or production SRE visibility. Health/readiness and measured local benchmark reports are the currently verified signals.

Native ZIP/JSON imports now create durable job records with stage history, timestamps, warnings, errors, request ID, snapshot ID and analyzer counts. The projecttrace.pipeline logger emits safe JSON stage records with organization/repository/job IDs and elapsed duration. For small local imports execution remains bounded and synchronous: stage history persists at completion, with PARSING durably visible before computation. This is not a streaming distributed worker implementation. Unhandled process termination recovery and exported telemetry remain deferred.
