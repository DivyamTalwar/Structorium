## Gemini CLI Overlay

Gemini CLI has experimental subagent support, but subagents currently run
sequentially (not in parallel). Review dimensions one at a time.

### Setup

Enable subagents in Gemini CLI settings:
```json
{
  "experimental": {
    "enableAgents": true
  }
}
```

Optionally define a reviewer agent in `.gemini/agents/structorium-reviewer.md`:

```yaml
---
name: structorium-reviewer
description: Scores subjective codebase quality dimensions for structorium
kind: local
tools:
  - read_file
  - search_code
temperature: 0.2
max_turns: 10
---

You are a code quality reviewer. You will be given a codebase path, a set of
dimensions to score, and what each dimension means. Read the code, score each
dimension 0-100 from evidence only, and return JSON in the required format.
Do not anchor to target thresholds. When evidence is mixed, score lower and
explain uncertainty.
```

### Review workflow

1. Preferred local path (Codex runner): `structorium review --run-batches --runner codex --parallel --scan-after-import`.
2. Gemini/cloud path: run `structorium review --prepare` to generate `query.json`.
3. Invoke the reviewer agent for each group of dimensions sequentially.
   Even without parallelism, isolating dimensions across separate agent
   invocations prevents score bleed between concerns.
4. Merge assessments and findings, then import:
   - robust session flow (recommended): `structorium review --external-start --external-runner claude`; use generated `claude_launch_prompt.md` + `review_result.template.json`, then run printed `structorium review --external-submit --session-id <id> --import <file>`
   - durable scored import (legacy): `structorium review --import findings.json --attested-external --attest "I validated this review was completed without awareness of overall score and is unbiased."`
   - findings-only fallback: `structorium review --import findings.json`

When Gemini CLI adds parallel subagent execution, split dimensions across
concurrent agent calls instead.

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

<!-- structorium-overlay: gemini -->
<!-- structorium-end -->
