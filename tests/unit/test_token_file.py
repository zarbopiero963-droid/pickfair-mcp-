"""Lettura fail-closed del file del token lato MCP (D-11)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from pickfair_control_api.tokens import issue_token_file
from pickfair_mcp.auth.token_file import LocalTokenFile, TokenFileError


@pytest.fixture
def token_dir(tmp_path: Path) -> Path:
    d = tmp_path / "secure"
    d.mkdir(mode=0o700)
    return d


def code(path: Path | str, **kwargs: object) -> str:
    with pytest.raises(TokenFileError) as info:
        LocalTokenFile(path, **kwargs).read()  # type: ignore[arg-type]
    return info.value.code


def test_valid_file_is_read(token_dir: Path) -> None:
    token = issue_token_file(token_dir / "t")
    assert LocalTokenFile(token_dir / "t").read() == token


def test_missing_file(token_dir: Path) -> None:
    assert code(token_dir / "absent") == "TOKEN_FILE_MISSING"


@pytest.mark.parametrize("perm", [0o640, 0o644, 0o604, 0o660, 0o666, 0o700])
def test_permissions_beyond_owner_rejected(token_dir: Path, perm: int) -> None:
    path = token_dir / "t"
    issue_token_file(path)
    os.chmod(path, perm)
    expected = "TOKEN_FILE_PERMISSIONS" if perm & 0o077 else None
    if expected is None:
        assert LocalTokenFile(path).read()
    else:
        assert code(path) == expected


def test_wrong_owner_rejected(token_dir: Path) -> None:
    path = token_dir / "t"
    issue_token_file(path)
    assert code(path, expected_uid=os.getuid() + 1) == "TOKEN_FILE_OWNER"


def test_symlink_rejected(token_dir: Path) -> None:
    real = token_dir / "real"
    issue_token_file(real)
    link = token_dir / "t"
    link.symlink_to(real)
    assert code(link) == "TOKEN_FILE_SYMLINK"


def test_directory_rejected(token_dir: Path) -> None:
    (token_dir / "t").mkdir(mode=0o700)
    assert code(token_dir / "t") in {"TOKEN_FILE_NOT_REGULAR", "TOKEN_FILE_UNREADABLE"}


@pytest.mark.parametrize("dir_mode", [0o777, 0o770, 0o722])
def test_writable_directory_rejected(token_dir: Path, dir_mode: int) -> None:
    issue_token_file(token_dir / "t")
    os.chmod(token_dir, dir_mode)
    try:
        assert code(token_dir / "t") == "TOKEN_DIR_UNSAFE"
    finally:
        os.chmod(token_dir, 0o700)


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"short",
        b"a" * 42,
        b"a" * 43 + b"\n",
        b"a" * 129,
        "à".encode() * 43,
        b"a b" * 20,
        b"\x00" * 50,
        b"a" * 300,
    ],
)
def test_altered_content_rejected(token_dir: Path, content: bytes) -> None:
    path = token_dir / "t"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT, 0o600)
    os.write(fd, content)
    os.close(fd)
    assert code(path) in {"TOKEN_FILE_MALFORMED", "TOKEN_FILE_TOO_LARGE"}


@pytest.mark.parametrize("raw", ["relative/token", "./t", "/abs/../etc/t"])
def test_unsafe_paths_rejected(raw: str) -> None:
    with pytest.raises(TokenFileError) as info:
        LocalTokenFile(raw)
    assert info.value.code == "TOKEN_PATH_INVALID"


def test_error_never_contains_the_token(token_dir: Path) -> None:
    path = token_dir / "t"
    token = issue_token_file(path)
    os.chmod(path, 0o644)
    with pytest.raises(TokenFileError) as info:
        LocalTokenFile(path).read()
    assert token not in str(info.value) and token not in repr(info.value)
