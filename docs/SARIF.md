# GitHub-native SARIF evidence

Structorium can export persisted findings as SARIF 2.1.0 without rerunning detectors:

```bash
structorium scan --path . --profile ci
structorium sarif --output artifacts/structorium.sarif
```

The exporter is deterministic, caps output at 5,000 findings by default, maps
Structorium tiers to SARIF levels, and emits a stable fingerprint derived from the
finding identity and repository-relative path. A source line moving by itself does
not create a new alert identity.

Use `--include-resolved` or `--include-suppressed` only for audit exports. Normal CI
exports contain active, unsuppressed findings. `--max-results` can lower the cap for
repositories with strict artifact budgets.

Upload the result with GitHub's CodeQL action:

```yaml
- name: Export Structorium SARIF
  run: structorium sarif --output artifacts/structorium.sarif

- name: Upload Structorium SARIF
  uses: github/codeql-action/upload-sarif@v4
  with:
    sarif_file: artifacts/structorium.sarif
    category: structorium
```

The implementation follows GitHub's supported SARIF subset and size guidance. It
does not copy or depend on another analyzer's exporter.

## Research provenance

- [GitHub SARIF support](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/sarif-support-for-code-scanning)
- [Uploading SARIF to GitHub](https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/uploading-a-sarif-file-to-github)
