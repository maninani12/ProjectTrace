# GitHub App integration

Use a GitHub App with Metadata:read, Contents:read and Pull requests:read. Request Checks:write only if checks are explicitly enabled. Do not request source writes. Subscribe to push and pull_request events as needed.

Configure GITHUB_APP_ID, GITHUB_PRIVATE_KEY (PEM), GITHUB_INSTALLATION_ID and GITHUB_WEBHOOK_SECRET through secure environment injection. The .env.example is a reference: the native application does not automatically load .env files. With a signed-in administrator and CSRF header, POST /api/github/connect with {repository_id, system, owner, checks_enabled:false}. It tests installation access and grants the initiating user access to the chosen repository. Other users need their own source grants; provider permission inheritance/member synchronization is still a production gate.

POST /api/github/webhook verifies HMAC-SHA256 and persists delivery uniqueness. Configure JOB_MODE=celery and Redis to dispatch provider jobs. Receipt, source analysis and check publication are distinct states. Jobs with failed broker dispatch remain durable and can be retried through /api/jobs/{id}/retry; queued/stopped jobs can be cancelled. There is no production outbox dispatcher or full distributed backpressure yet.

The worker fetches bounded GitHub trees/blobs using temporary installation tokens, rejects truncated trees, symlinks/submodules and oversize data, analyzes base/head, and optionally publishes a neutral ProjectTrace check. Owner/repository and SHA formats are validated; arbitrary URLs are never accepted. Fork source permissions, large-installation pagination, provider failures/recovery and real check publication require live tests.

This environment has no GitHub App credentials or installation: LIVE END-TO-END NOT VERIFIED. Mocks verify selected transport contracts only. SonarQube/Wiz normalization interfaces exist; live provider adapters remain deferred.

Provider contracts were checked against the official [Git trees documentation](https://docs.github.com/en/rest/git/trees) and [check-run documentation](https://docs.github.com/en/rest/checks/runs). Those documentation checks used no live credentials.
