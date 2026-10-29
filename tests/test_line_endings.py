from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# Files that run inside Linux containers. A CRLF checkout breaks them: a shebang ending
# in "\r" makes `env` look for a program named "bash\r" (#48).
CONTAINER_PATTERNS = ("*.sh", "*.sql", "Caddyfile", "Dockerfile")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=REPO_ROOT, check=True, capture_output=True, text=True
    ).stdout


@pytest.fixture(scope="module")
def container_files() -> list[str]:
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("requires a git checkout")
    pathspecs = [f":(glob)**/{pattern}" for pattern in CONTAINER_PATTERNS]
    files = git("ls-files", "--", *pathspecs).splitlines()
    assert files, "expected tracked container files"
    return files


def test_container_files_are_checked_out_with_lf(container_files: list[str]) -> None:
    attributes = git("check-attr", "eol", "--", *container_files).splitlines()

    not_lf = [line for line in attributes if not line.endswith(": eol: lf")]

    assert not_lf == []
