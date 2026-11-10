---
applyTo: "main.py,server.py,src/**/*.py,data_provider/**/*.py,api/**/*.py,bot/**/*.py,tests/**/*.py"
---

# Backend Instructions

- Preserve current pipeline boundaries and reuse existing services, repositories, schemas, and fallback logic instead of creating parallel paths.
- Changes touching config, CLI flags, schedule semantics, API behavior, auth, or report payloads must sync `.env.example` and assess Web/Desktop compatibility.
- Changes in `data_provider/` must preserve provider priority, normalization behavior, timeout/retry expectations, and graceful degradation.
- Run `python -m py_compile` on changed files and targeted deterministic tests covering affected behavior and direct consumers. Expand relevant regression coverage for shared or high-risk contracts. Full `./scripts/ci_gate.sh` runs in CI by default; run it locally only when the user explicitly requests or agrees. If impact remains unclear, explain the risk and obtain agreement first. Do not describe targeted checks as a full gate pass.
- Do not let a single provider, notification channel, or optional integration failure break the main analysis flow unless the requirement explicitly demands fail-fast behavior.
