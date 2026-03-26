import json
from tests.e2e.conftest import CLISandbox

def test_malformed_config_fallback(cli_sandbox: CLISandbox):
    """Verifies PR 1 fix: a malformed config (list instead of dict) falls back gracefully."""
    # Write a valid JSON array instead of a JSON object
    config_path = cli_sandbox.project_dir / ".structorium" / "config.json"
    config_path.write_text('["this", "is", "a", "list"]')
    
    cli_sandbox.write_file("src/ok.py", "print('hello')")
    
    # Should not crash with TypeError, but fallback to defaults
    result = cli_sandbox.run_cli("--lang", "python", "scan", assert_exit_code=0)
    assert "Config file" in result.stderr and "contains a non-object" in result.stderr

def test_config_ignore_patterns(cli_sandbox: CLISandbox):
    """Verifies that config ignore overrides work correctly."""
    cli_sandbox.write_file(".structorium/config.json", json.dumps({
        "exclude": ["src/ignored.py"]
    }))
    
    cli_sandbox.write_file("src/ignored.py", "aws_key = 'AKIAIOSFODNN7EXAMPLE'") # Vulnerable
    cli_sandbox.write_file("src/scanned.py", "aws_key = 'AKIAIOSFODNN7EXAMPLE'") # Vulnerable
    
    cli_sandbox.run_cli("--lang", "python", "scan", assert_exit_code=0)
    
    state_file = cli_sandbox.project_dir / ".structorium" / "state-python.json"
    state_data = json.loads(state_file.read_text())
    
    # Only the 'scanned.py' finding should be present
    findings = state_data.get("findings", {})
    affected_files = {f.get("file") for f in findings.values()}
    assert "src/scanned.py" in affected_files
    assert "src/ignored.py" not in affected_files

def test_custom_thresholds(cli_sandbox: CLISandbox):
    """Verifies that custom thresholds in config affect scoring/findings."""
    cli_sandbox.write_file(".structorium/config.json", json.dumps({
        "large_files_threshold": 5 # Super small threshold
    }))
    
    # Write a 10 line file, which usually passes, but fails our 5 line threshold
    content = "\n".join([f"line_{i} = {i}" for i in range(10)])
    cli_sandbox.write_file("src/big.py", content)
    
    cli_sandbox.run_cli("--lang", "python", "scan", assert_exit_code=0)
    
    state_file = cli_sandbox.project_dir / ".structorium" / "state-python.json"
    state_data = json.loads(state_file.read_text())
    
    # We should have a structural/large_file finding
    findings = state_data.get("findings", {})
    structural = [f for f in findings.values() if f.get("detector") == "structural"]
    assert any("large" in str(s).lower() or "line" in str(s).lower() for s in structural), "File should trigger large threshold"
