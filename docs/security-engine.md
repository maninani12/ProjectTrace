# Security engine

Current Python rules identify dynamic SQL expressions passed directly to execute(), explicit shell=True subprocess calls, unsafe pickle/YAML deserialization and weak digest calls. Dynamic SQL and weak-digest context are medium confidence where reachability/security use is unproven. JS/Java eval patterns are similarly disclosed as lexical evidence. There is no complete taint engine.

Secrets include credential-shaped assignments, selected provider token patterns and private-key blocks. Values are masked before source persistence. Unsupported formats can be missed. IaC checks currently cover explicit privileged containers, Docker USER root/0 and Terraform public ACL patterns. These lexical rules require review and do not simulate cloud behavior.

Known dependency advisories come from a cached OSV query of the exact demo package version; provider severity is preserved (MODERATE maps to MEDIUM). Other dependencies are NOT_CHECKED, not asserted safe. CycloneDX exports identify parsed packages; complete dependency graphs, Maven/Gradle, SPDX, license compliance and vulnerability refresh UI are deferred.
