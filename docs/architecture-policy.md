# Architecture policy as code

Place `structorium.toml` at the scan root. Rules operate on the dependency
graph already built by the active language plugin and become normal ranked
findings, including in the new-code gate.

```toml
[architecture]
enabled = true

[[architecture.rules]]
id = "domain-does-not-import-web"
from = "src/domain/**"
deny = ["src/web/**", "src/infrastructure/http/**"]
tier = 1

[[architecture.rules.exceptions]]
from = "src/domain/legacy.py"
to = "src/infrastructure/http/legacy.py"
until = 2026-10-01
```

Paths are root-relative, slash-normalized globs. An exception stops applying
after `until`; the resulting finding records that the exception expired.
Invalid TOML, duplicate IDs, empty globs, and tiers outside 1–4 fail the scan
instead of silently weakening policy.
