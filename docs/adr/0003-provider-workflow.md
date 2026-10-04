# ADR 0003 — least-privilege GitHub App and advisory checks

Accepted: temporary installation tokens, source-read access, signed unique webhook delivery and a separate provider worker. Optional check publication needs explicit checks_enabled and Checks:write; checks remain neutral/advisory in V1. No source write, push, merge or deploy authority is added.

Bounded tree/blob intake avoids arbitrary URL transport and repository execution. Live credentials, source permission inheritance, outbox dispatch and recovery tests are production gates. External evidence adapters preserve source attribution and do not claim native analysis.
