# Incremental objective scans

`structorium scan --profile ci` and `--profile objective` persist a
content-addressed result under `.structorium/cache/objective-scan-v1.json`.
An unchanged scan reuses normalized objective findings. Full scans are not
cached because subjective review may depend on time or external state.

The key covers the Structorium source hash, selected phases, language/runtime
configuration, zone overrides, and every scanned source digest. The manifest
reuses a digest only when both file size and nanosecond modification time are
unchanged. Writes are atomic and corrupt cache documents are ignored.

Disable reuse for parity/debugging with:

```bash
STRUCTORIUM_DISABLE_INCREMENTAL_CACHE=1 structorium scan --profile ci
```

Run the 10,000-file manifest benchmark with:

```bash
PYTHONPATH=. python benchmarks/benchmark_incremental_cache.py
```
