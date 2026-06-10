# TDD+M Professional Methodology

Status: active testing policy.

This document defines how QUIMERA/OpenClaw uses Test Driven Development plus
Mutation testing without turning mutation score into a vanity metric.

## Principle

Mutation testing is a diagnostic tool. It asks whether the test suite would
detect small faults in behavior. A higher score is useful only when it comes
from stronger behavioral oracles.

Do not improve the score by hiding code from mutation, relaxing mutants, or
rewriting tests to assert implementation details that do not matter to users or
operators.

## Loop

For code touched in a PR, use this loop:

1. Red: write a failing behavioral test for the contract being changed.
2. Green: implement the smallest production change that satisfies it.
3. Mutate: run targeted mutation against the changed module or the survivor
   cluster named by the Vibe Deep report.
4. Refactor: improve names or structure only after the behavior and mutation
   signal are stable.

## Survivor Triage

Every surviving mutant should be classified into one of these buckets:

- Missing oracle: the test reaches the code but does not assert the observable
  consequence. Add an assertion against output, emitted telemetry, persisted
  state, raised error, or external call shape.
- Missing path: no executable test reaches the code in the current environment.
  Prefer a fake, adapter, or fixture that exercises the path offline. If a live
  service is essential, run through `scripts/vibe_deep_run.sh`.
- Equivalent mutant: the mutation does not change observable behavior under
  the module contract. Document the reason in the review notes.
- Dead or obsolete code: remove it rather than preserving it with decorative
  tests.

## OpenTelemetry Decorators

For tracing decorators, fake spans are not enough. Unit tests must use
`TracerProvider`, `SimpleSpanProcessor`, and `InMemorySpanExporter` when the
contract is span emission, span name, attributes, status, or exception events.

Assertions should verify:

- exact span name for the operation;
- required semantic attributes;
- latency attribute exists and is numeric;
- sensitive inputs are absent from attributes and exception events;
- exception status and event messages are sanitized.

## Configuration Guardrails

`pyproject.toml` must keep:

```toml
[tool.mutmut]
source_paths = ["backend"]
mutate_only_covered_lines = false
```

`mutate_only_covered_lines = false` is intentional. It keeps no-test regions
visible in the report, which prevents an artificially high score over only the
already-covered subset.

## Review Output

COWORK or any adversarial reviewer should report:

- total killed, survived, suspicious, and no-test mutants;
- the top survivor clusters by module;
- at least one root-cause classification for each touched cluster;
- whether any score improvement came from changed behavior tests rather than
  mutation exclusions.
