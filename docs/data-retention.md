# Retention and privacy

The local database retains redacted source text, original content hashes, derived evidence/claims/findings/dependencies, review decisions, session digests and audit events. The source fixtures are stored locally and no external AI provider receives context. GitHub source fetching would contact only api.github.com after authorized connection. OSV querying sends package identity/version, not repository source.

Retention duration is currently operator-managed; there is no configurable deletion/retention UI, object-storage lifecycle or cryptographic audit archive. Expired sessions cannot authenticate but automatic database cleanup is not implemented. Backups contain sensitive redacted source metadata and require secure handling.

Do not import customer source into this demo assuming enterprise deletion guarantees. A production deletion workflow must remove raw/derived/vector/cache/object data transactionally while retaining only an approved minimal audit tombstone. That workflow and its legal retention choices are not implemented in this release.
