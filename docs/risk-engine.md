# Risk and gates

The local release presents severity/confidence and groups evidence by component/repository. It does not invent an exposure, exploitability or business-risk score when those inputs are unavailable.

Default advisory gate v1: high-confidence critical findings FAIL; other high/critical findings REQUIRE_REVIEW; contradicted claims REQUIRE_REVIEW. Uncertain low-confidence findings do not automatically block a live merge. Scope and reasons appear in the PR view. Human false-positive/resolved review flags and active privileged exceptions can change gate evaluation; expiry restores review requirements.

Runtime reachability, cross-asset risk-path correlation, policy-builder customization and enterprise merge enforcement remain deferred. GitHub check publication is neutral/advisory and requires explicit connector checks_enabled plus Checks:write permission.
