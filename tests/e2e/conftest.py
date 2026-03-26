import os
import sys
import subprocess
from pathlib import Path
import pytest

class CLISandbox:
    """An isolated environment for running the Structorium CLI."""
    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.project_dir = workspace / "project"
        self.project_dir.mkdir()
        
        # Initialize the .structorium directory representing our state/config
        self.structorium_dir = self.project_dir / ".structorium"
        self.structorium_dir.mkdir()
        
    def write_file(self, rel_path: str, content: str) -> Path:
        """Write a file into the sandbox project directory."""
        p = self.project_dir / rel_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")
        return p

    def run_cli(self, *args, assert_exit_code: int | None = 0):
        """Run the CLI via subprocess and return the completed process."""
        python_exe = sys.executable
        cli_py = Path(__file__).parent.parent.parent / "cli.py"
        
        # We run it as a subprocess to guarantee environment isolation
        # and prevent sys.exit() from killing the pytest runner.
        cmd = [python_exe, str(cli_py)] + list(args)
        
        # We need to set PYTHONPATH so `cli.py` can absolute-import project modules
        env = os.environ.copy()
        env["PYTHONPATH"] = str(cli_py.parent)
        
        result = subprocess.run(
            cmd,
            cwd=str(self.project_dir),
            capture_output=True,
            text=True,
            env=env
        )
        
        if assert_exit_code is not None:
            assert result.returncode == assert_exit_code, (
                f"Command '{' '.join(cmd)}' failed.\n"
                f"Expected exit code: {assert_exit_code}, got: {result.returncode}\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}\n"
            )
            
        return result

@pytest.fixture
def cli_sandbox(tmp_path: Path) -> CLISandbox:
    """Provides a fresh, isolated structurally-accurate project directory."""
    return CLISandbox(tmp_path)
