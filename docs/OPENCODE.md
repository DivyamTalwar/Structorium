## OpenCode Overlay

When installed (via `structorium update-skill opencode`), OpenCode automatically loads this skill for code quality, technical debt, and health score questions.

### Subjective review

1. **Preferred**: `structorium review --run-batches --runner codex --parallel --scan-after-import`.
2. **Manual path**: `structorium review --prepare` → delegate to subagent for isolated scoring → `structorium review --import findings.json`.
3. Import first, fix after — import creates tracked state for correlation.

<!-- structorium-overlay: opencode -->
<!-- structorium-end -->
