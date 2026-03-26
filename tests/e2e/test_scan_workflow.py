import json
from pathlib import Path
from tests.e2e.conftest import CLISandbox

def test_tracer_bullet_scan_finds_vulnerability(cli_sandbox: CLISandbox):
    """
    Tracer Bullet test matching the implementation plan.
    Initializes a basic Python project with a mocked security vulnerability,
    runs `structorium scan`, and asserts the findings.
    """
    # 1. Setup Phase: Write vulnerable code
    # Using a common credential pattern (e.g., AWS Key) to trigger the security detector
    vulnerable_code = '''
def connect_to_db():
    aws_access_key = "AKIAIOSFODNN7EXAMPLE" 
    aws_secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    return (aws_access_key, aws_secret_key)
    '''
    cli_sandbox.write_file("src/main.py", vulnerable_code)
    
    # 2. Execution Phase: Run the complete scan process
    # We expect this to succeed (exit code 0) but output findings
    result = cli_sandbox.run_cli("--lang", "python", "scan", assert_exit_code=0)
    
    # 3. Verification Phase: Assertions on the engine's output and state
    state_file = cli_sandbox.project_dir / ".structorium" / "state-python.json"
    assert state_file.exists(), "State file should be created after a scan"
    
    state_data = json.loads(state_file.read_text())
    findings = state_data.get("findings", {})
    
    # Assert we caught at least the AWS Keys
    assert len(findings) > 0, "Security detector should have found the AWS keys"
    
    # Check that at least one finding from "security" detector is present
    security_findings = [f for f in findings.values() if f.get("detector") == "security"]
    assert len(security_findings) > 0, "No security findings were persisted"
    
    # Ensure stderr actually printed some progress
    assert "Scan complete" in result.stderr or "[1/15]" in result.stderr, "CLI stderr should indicate scan progression"
