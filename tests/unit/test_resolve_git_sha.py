"""`resolve_git_sha`: checkout normale e git worktree (MCP-01m), sempre senza sottoprocessi."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pickfair_control_api.contract import resolve_git_sha


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    (r / "f").write_text("x")
    git(r, "add", "f")
    git(r, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "c")
    return r


def test_plain_checkout(repo: Path) -> None:
    assert resolve_git_sha(repo) == git(repo, "rev-parse", "HEAD")


def test_worktree_on_a_branch(repo: Path, tmp_path: Path) -> None:
    wt = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "feature", str(wt))
    assert (wt / ".git").is_file()
    assert resolve_git_sha(wt) == git(wt, "rev-parse", "HEAD")


def test_worktree_with_packed_refs(repo: Path, tmp_path: Path) -> None:
    wt = tmp_path / "wt2"
    git(repo, "worktree", "add", "-q", "-b", "packed", str(wt))
    git(repo, "pack-refs", "--all")
    assert not (repo / ".git" / "refs" / "heads" / "packed").exists()
    assert resolve_git_sha(wt) == git(wt, "rev-parse", "HEAD")


def test_unresolvable_is_an_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / ".git").write_text("gitdir: missing\n")
    with pytest.raises(Exception):
        resolve_git_sha(bad)
