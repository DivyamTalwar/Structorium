import json
from tests.e2e.conftest import CLISandbox

def test_status_command(cli_sandbox: CLISandbox):
    """Verifies status command summarizes correctly without failing."""
    cli_sandbox.write_file("src/main.py", "print('hello')")
    cli_sandbox.run_cli("--lang", "python", "scan", assert_exit_code=0)
    
    result = cli_sandbox.run_cli("--lang", "python", "status", assert_exit_code=0)
    assert "Overall Quality" in result.stdout or "Health" in result.stdout or "0 findings" in result.stdout

def test_plan_command(cli_sandbox: CLISandbox):
    """Verifies plan generation after a scan."""
    cli_sandbox.write_file("src/main.py", "aws_key = 'AKIAIOSFODNN7EXAMPLE'")
    cli_sandbox.run_cli("--lang", "python", "scan", assert_exit_code=0)
    
    result = cli_sandbox.run_cli("--lang", "python", "plan", assert_exit_code=0)
    # Should generate either markdown or tree output indicating a priority plan
    assert "Plan" in result.stdout or "AWS" in result.stdout or "queue" in result.stdout.lower()

def test_show_command_safety(cli_sandbox: CLISandbox):
    """Verifies PR 2 fix: show command does not crash on partial payloads."""
    # Hand-craft a corrupted state.json where finding misses "file" and "detector" keys
    state = {
        "findings": {
            "bad_finding_1": {
                "summary": "This finding is missing everything else",
                "tier": 1
            }
        }
    }
    cli_sandbox.write_file(".structorium/state-python.json", json.dumps(state))
    
    # We haven't implemented PR 2 yet, so this might crash if it hits the bug!
    # But if PR 1 handled general CLI crashes, we still want this to fail gracefully.
    # We will test `show bad_finding_1`
    result = cli_sandbox.run_cli("--lang", "python", "show", "bad_finding_1", assert_exit_code=0)
    assert result.stdout != "" # some output rendered
