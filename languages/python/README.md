## Python Plugin Maintainer Notes

### AST smell detector layout

`languages.python.detectors.smells_ast` is split by role:

- `_dispatch.py`: registry-driven orchestration for AST smell scanning
- `_types.py`: typed match/count models and deterministic merge helpers
- `_node_detectors.py`: function/class node-level detectors
- `_source_detectors.py`: source/import-resolution detectors
- `_tree_safety_detectors.py`: security/safety oriented tree detectors
- `_tree_quality_detectors.py`: maintainability/quality tree detectors
- `_tree_context_detectors.py`: callback/path context detectors

Public package exports are intentionally narrow in
`smells_ast/__init__.py`.

### Adding a new AST smell detector

1. Decide category:
- node-level: function/class-specific logic
- tree-level: whole-module AST logic
- source-level: import resolution or source-text + AST combo

2. Implement detector in the appropriate module.
- Keep detector focused to one smell ID.
- Prefer returning normalized entries (`file`, `line`, `content`) via
  dispatch adapters.

3. Register detector in `_dispatch.py`.
- Add a `NODE_DETECTORS` or `TREE_DETECTORS` spec entry.
- Ensure smell ID is unique.

4. Wire smell metadata in `/Users/peteromalley/Documents/structorium/languages/python/detectors/smells.py`.
- Add ID, label, severity to `SMELL_CHECKS`.

5. Add tests.
- Unit test for detector behavior.
- Direct test for dispatch/registry behavior when relevant.

6. Run checks.
- `ruff check`
- `pytest -q`
