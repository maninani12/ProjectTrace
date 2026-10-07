# Infrastructure support and authority

All five formats are **PARTIAL**, static and non-executing. Syntax parsing is supported for the listed inputs; full deployment semantics and production accuracy remain unmeasured. Terraform, Docker, kubectl, Helm, Compose, shell commands and CloudFormation transforms are never executed against imported source.

| Format | Implemented observations | Remaining boundaries |
| --- | --- | --- |
| Terraform HCL2 / tf.json | Resources, variables, locals, outputs, providers/aliases, module declarations, symbolic references; included local module links; selected AWS/Azure/GCP storage/network/identity checks | count/for_each and dynamic expressions are symbolic; modules are not instantiated; missing or remote modules unresolved; no plan/state/provider evaluation |
| CloudFormation YAML / JSON | Resources and Parameters/Mappings/Conditions/Outputs; symbolic intrinsic references; selected storage, DB, ingress and IAM permissions/trust | Conditions/intrinsics are not evaluated; macros/Transforms/SAM unresolved; remote nested templates not fetched; incomplete ECS/EKS semantics |
| Kubernetes YAML / JSON | Listed workload/network/RBAC/config/storage declarations; security contexts, identity, images, resource budgets and selected TLS/RBAC/exposure checks; Secret/ConfigMap references | Policy presence does not establish selector coverage or effective admission defaults; service routing and secret key existence unresolved; Helm templates are unrendered; Secret values excluded from resource metadata |
| Compose YAML / JSON | Service and network/volume/secret/config declarations; image, identity, privileges, capabilities, sockets, host modes, published ports and references | External networks, resolved interpolation, host firewall exposure and runtime images unobserved; no Compose execution |
| Dockerfile | Bounded logical instruction parser, stages and final user; image pinning, secret declarations, remote downloads, sensitive COPY, chmod 777 and configured healthcheck requirement | No build; shell instructions are inert strings; base image defaults, executable provenance, final tooling necessity and runtime state unknown |

Organization/team/repository profile inheritance supplies static infrastructure policy. Administrators select the environment explicitly, enable or disable rules, override severity, restrict applicability, require selected declarations, and configure registry allowlists. Each save preserves a version record; each analysis captures its effective configuration. Configuration changes invalidate IaC observation reuse. No filename establishes a production environment.

Findings remain linked to the Evidence Graph and their declared resources. Uniquely resolved references create graph edges; unresolved references do not invent targets. Captured Trust & Coverage reports per-format files, resources and diagnostics for the selected snapshot. Public declarations are never labeled proof of production exposure. The fixture suite is evidence of implemented behavior, not population precision.

Validation: six focused deep infrastructure tests passed; 65 existing native platform, enterprise trust and structural identity tests passed after the configuration regression fix. Production cloud validation remains unavailable without operator credentials.
