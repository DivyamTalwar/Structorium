## Windsurf Overlay

Windsurf does not support spawning subagents from within a Cascade session.
Parallel reviews require the user to open multiple Cascade panes manually.

### Review workflow

1. Preferred local path (Codex runner): `structorium review --run-batches --runner codex --parallel --scan-after-import`.
2. Windsurf/cloud path: run `structorium review --prepare` to generate `query.json`.
3. Ask the user to open additional Cascade panes for parallel review.
   Suggest splitting dimensions across 2-3 panes (e.g., naming + clarity
   in one, abstraction + error consistency in another).
4. Each pane should score its assigned dimensions independently, reading
   the codebase and `query.json`'s `dimension_prompts` for context.
5. Each pane writes its output to a separate file.
6. In the primary pane, merge assessments (average where dimensions overlap)
   and findings, then import:
   - robust session flow (recommended): `structorium review --external-start --external-runner claude`; use generated `claude_launch_prompt.md` + `review_result.template.json`, then run printed `structorium review --external-submit --session-id <id> --import <file>`
   - durable scored import (legacy): `structorium review --import findings.json --attested-external --attest "I validated this review was completed without awareness of overall score and is unbiased."`
   - findings-only fallback: `structorium review --import findings.json`

If the user prefers a single-pane workflow, review all dimensions sequentially
in one session. This is slower but still works.

### Review integrity

1. Do not use prior chat context, score history, or target-threshold anchoring while scoring.
2. Score from evidence only; when evidence is mixed, score lower and explain uncertainty.
3. Return machine-readable JSON only for review imports. For `--external-submit`, include `session` from the generated template:

```json
{
  "session": {
    "id": "<session_id_from_template>",
    "token": "<session_token_from_template>"
  },
  "assessments": {
    "naming_quality": 0,
    "error_consistency": 0,
    "abstraction_fit": 0,
    "logic_clarity": 0,
    "ai_generated_debt": 0
  },
  "findings": [
    {
      "dimension": "naming_quality",
      "identifier": "short_id",
      "summary": "one-line defect summary",
      "related_files": ["relative/path/to/file.py"],
      "evidence": ["specific code observation"],
      "suggestion": "concrete fix recommendation",
      "confidence": "high|medium|low"
    }
  ]
}
```
4. `findings` MUST match `query.system_prompt` exactly. Use `"findings": []` only when no defects are found.
5. Import is fail-closed by default: invalid/skipped findings abort `structorium review --import` unless `--allow-partial` is explicitly passed.
6. Assessment scores are auto-applied from trusted internal run-batches imports, or via Claude cloud session imports (`--external-start` + printed `--external-submit`). Legacy attested external import via `--attested-external` remains supported.

<!-- structorium-overlay: windsurf -->
<!-- structorium-end -->
