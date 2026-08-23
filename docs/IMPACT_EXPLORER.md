# Dependency impact explorer

Before changing a shared module, ask Structorium which modules depend on it, which
dependencies it reaches, and the shortest path that proves each relationship:

```bash
structorium impact src/domain.py --direction dependents --depth 4
structorium impact src/domain.py --format json --output artifacts/impact.json
structorium impact src/domain.py --format mermaid --output artifacts/impact.mmd
```

Directory targets expand to every dependency-graph node below that prefix. Searches
are deterministic breadth-first traversals, so every result includes a shortest-path
witness. `--depth` defaults to 3 and `--max-nodes` defaults to 200; the report marks
itself as truncated instead of silently exploring an unbounded monorepo graph.

Directions use explicit names:

- `dependents`: files that could be affected when the target changes.
- `dependencies`: files the target itself relies on.
- `both`: both views within the same shared node budget.

JSON is intended for agents and CI artifacts. Mermaid is intended for PR descriptions
and architecture discussions. Both describe original source-to-dependency edges; the
visual renderer never invents relationships.

## Research provenance

The feature is original Structorium code informed by public code-graph workflows:

- [dependency-cruiser CLI reporters](https://github.com/sverweij/dependency-cruiser/blob/main/doc/cli.md)
  provide graph outputs including Mermaid for repository-native review.
- [dependency-cruiser folder graphs](https://github.com/sverweij/dependency-cruiser/blob/main/doc/faq.md#folder-level-dependency-graph-ddot-reporter)
  demonstrate why large dependency graphs need focused, summarized views.
- [CodeQL path explanations](https://codeql.github.com/docs/writing-codeql-queries/creating-path-queries/)
  establish evidence paths as a useful way to explain why a result is reachable.

No competitor code or runtime dependency is used.
