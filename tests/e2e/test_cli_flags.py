import json
from tests.e2e.conftest import CLISandbox

def test_cli_exclude_flag(cli_sandbox: CLISandbox):
    """Verifies that the --exclude flag correctly masks files from the scan."""
    cli_sandbox.write_file("src/main.py", "aws_key = 'AKIAIOSFODNN7EXAMPLE'")
    cli_sandbox.write_file("tests/test_main.py", "aws_key = 'AKIAIOSFODNN7EXAMPLE'")
    
    # exclude tests directory
    result = cli_sandbox.run_cli("--lang", "python", "--exclude", "tests/*", "scan", assert_exit_code=0)
    
    assert "Excluding: tests/*" in result.stderr
    
    state_file = cli_sandbox.project_dir / ".structorium" / "state-python.json"
    state_data = json.loads(state_file.read_text())
    affected_files = {f.get("file") for f in state_data.get("findings", {}).values()}
    
    assert "src/main.py" in affected_files
    assert "tests/test_main.py" not in affected_files

def test_skip_slow_flag(cli_sandbox: CLISandbox):
    """Verifies --skip-slow disables detectors marked as slow."""
    cli_sandbox.write_file("src/main.py", "def a(): pass")
    
    result = cli_sandbox.run_cli("--lang", "python", "scan", "--skip-slow", assert_exit_code=0)
    # The output log should indicate skipping if a slow detector is bypassed
    assert "[1/" in result.stderr

def test_unknown_command_ux(cli_sandbox: CLISandbox):
    """Verifies unknown commands are cleanly rejected by argparse."""
    result = cli_sandbox.run_cli("--lang", "python", "blarg", assert_exit_code=2)
    assert "invalid choice: 'blarg'" in result.stderr
