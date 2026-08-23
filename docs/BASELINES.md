# Freeze existing debt, ratchet every change

Large existing repositories often cannot fix every finding before enabling a CI
gate. Structorium's baseline workflow records the current active finding identities
and then fails only when a later scan introduces more than the allowed number of new
findings.

```bash
structorium scan --path . --profile ci
structorium baseline capture --output .structorium/baseline.json
git add .structorium/baseline.json

# In later CI runs
structorium scan --path . --profile ci
structorium baseline check --baseline .structorium/baseline.json
```

`check` exits with code `3` when new findings exceed `--max-new` (zero by
default). It also reports baseline findings that were resolved, making the artifact
a one-way ratchet rather than a permanent exemption list.

The baseline is deterministic, sorted, and protected by a SHA-256 checksum. Editing
individual entries by hand fails closed; recapturing requires the explicit
`capture --force` operation. Resolved and suppressed findings are never captured.

## Research provenance

The design is an original Structorium implementation informed by two public
patterns:

- [ArchUnit FreezingArchRule](https://www.archunit.org/userguide/html/000_Index.html#_freezing_arch_rules)
  records existing violations and reports only new ones, allowing incremental
  adoption in grown projects.
- [Qodana baselines](https://www.jetbrains.com/help/qodana/quality-gate.html#baseline)
  separate accepted existing problems from newly introduced analysis results.

Unlike those systems, this artifact is built directly from Structorium's stable
finding IDs, includes a tamper-evident checksum, and exposes resolved baseline debt
in the same comparison.
