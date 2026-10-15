# Evidence model

Generation extension (0024) and learning extension (0025): incomplete generations remain private; published graph/evidence IDs are pinned by learning objectives. Every assessment citation must belong to the objective and captured target snapshot. Source changes create new learning revisions while retaining earlier completion evidence. See [generation and learning data model](GENERATION_AND_LEARNING.md).

An immutable snapshot carries organization, repository, system/component labels, branch, commit provenance, SHA-256 file fingerprints and analyzer/rule versions. Local commit identifiers are CONTENT_DIGEST values, not Git commit SHAs. Credential-gated GitHub fetching can supply GIT_SHA provenance.

Evidence documents retain redacted source, path, hash, authority and scope. Claim and finding documents link to actual evidence IDs. Edges use DOCUMENTED_BY, SUPPORTED_BY, CONTRADICTED_BY, DETECTED_IN and AFFECTS. Repository grants constrain all graph/read/export surfaces.

The current relational model uses versioned JSON domain documents with explicit tenant/repository foreign keys. It does not yet have every normalized entity in the master specification, formal environment modeling, per-line signal authority tables or multi-component monorepo mappings. Snapshot source and append-oriented audit should be treated as sensitive retained data.
