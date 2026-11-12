"""Token Bearer locale lato Control API: emissione, rotazione atomica, concorrenza."""

from __future__ import annotations

import os
import re
import stat
import threading
from pathlib import Path

import pytest

import pickfair_control_api.tokens as tokens_mod
from pickfair_control_api.tokens import TokenStore, issue_token_file
from tests.conftest import subprocess_env

TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")


def mode(path: Path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def test_issue_creates_private_new_file(tmp_path: Path) -> None:
    path = tmp_path / "api.token"
    old_umask = os.umask(0)
    try:
        token = issue_token_file(path)
    finally:
        os.umask(old_umask)
    assert TOKEN_RE.fullmatch(token) and path.read_text() == token
    assert mode(path) == 0o600
    with pytest.raises(FileExistsError):
        issue_token_file(path)
    assert path.read_text() == token


def test_issue_refuses_symlink(tmp_path: Path) -> None:
    target = tmp_path / "elsewhere"
    link = tmp_path / "api.token"
    link.symlink_to(target)
    with pytest.raises(OSError):
        issue_token_file(link)
    assert not target.exists()


def test_rotation_switches_atomically_and_revokes_old(tmp_path: Path) -> None:
    path = tmp_path / "api.token"
    old = issue_token_file(path)
    store = TokenStore(old)
    new = store.rotate(path)
    assert new != old and TOKEN_RE.fullmatch(new)
    assert path.read_text() == new and mode(path) == 0o600
    assert store.accepts(new.encode()) and not store.accepts(old.encode())
    assert [p.name for p in tmp_path.iterdir()] == ["api.token"]  # nessun temporaneo residuo
    assert store.rotations == 1


def test_failed_rotation_keeps_old_token_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "api.token"
    old = issue_token_file(path)
    store = TokenStore(old)

    def broken_replace(*_a: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(tokens_mod.os, "replace", broken_replace)
    with pytest.raises(OSError):
        store.rotate(path)
    assert path.read_text() == old
    assert store.accepts(old.encode())
    assert [p.name for p in tmp_path.iterdir()] == ["api.token"]


def test_during_rotation_both_tokens_accepted_then_only_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "api.token"
    old = issue_token_file(path)
    store = TokenStore(old)
    seen: list[tuple[bool, bool]] = []
    real_replace = os.replace

    def observing_replace(src: object, dst: object) -> None:
        new = Path(str(src)).read_text()
        seen.append((store.accepts(old.encode()), store.accepts(new.encode())))
        real_replace(src, dst)  # type: ignore[arg-type]

    monkeypatch.setattr(tokens_mod.os, "replace", observing_replace)
    store.rotate(path)
    assert seen == [(True, True)]


def test_concurrent_rotations_and_readers_never_see_partial_tokens(tmp_path: Path) -> None:
    path = tmp_path / "api.token"
    store = TokenStore(issue_token_file(path))
    errors: list[str] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            text = path.read_text()
            if not TOKEN_RE.fullmatch(text):
                errors.append(repr(text))

    def rotator() -> None:
        for _ in range(25):
            store.rotate(path)

    readers = [threading.Thread(target=reader) for _ in range(3)]
    rotators = [threading.Thread(target=rotator) for _ in range(3)]
    for t in readers + rotators:
        t.start()
    for t in rotators:
        t.join()
    stop.set()
    for t in readers:
        t.join()
    assert errors == []
    assert store.rotations == 75
    assert store.accepts(path.read_text().encode())
    assert [p.name for p in tmp_path.iterdir()] == ["api.token"]


def test_store_repr_is_redacted(tmp_path: Path) -> None:
    token = issue_token_file(tmp_path / "t")
    assert token not in repr(TokenStore(token))


def test_publish_fresh_token_replaces_previous_run_token(tmp_path: Path) -> None:
    from pickfair_control_api.tokens import publish_fresh_token

    path = tmp_path / "api.token"
    old = issue_token_file(path)
    store = publish_fresh_token(path)
    new = path.read_text()
    assert new != old and TOKEN_RE.fullmatch(new) and mode(path) == 0o600
    assert store.accepts(new.encode()) and not store.accepts(old.encode())
    assert [p.name for p in tmp_path.iterdir()] == ["api.token"]


def test_publish_fresh_token_replaces_a_symlink_without_following_it(tmp_path: Path) -> None:
    from pickfair_control_api.tokens import publish_fresh_token

    target = tmp_path / "target"
    target.write_text("untouched")
    link = tmp_path / "api.token"
    link.symlink_to(target)
    publish_fresh_token(link)
    assert target.read_text() == "untouched"
    assert not link.is_symlink() and mode(link) == 0o600


def test_concurrent_processes_never_read_a_partial_token(tmp_path: Path) -> None:
    import subprocess
    import sys

    secure = tmp_path / "secure"
    secure.mkdir(mode=0o700)
    path = secure / "api.token"
    store = TokenStore(issue_token_file(path))
    reader = (
        "import sys, re\n"
        "from pickfair_mcp.auth.token_file import LocalTokenFile, TokenFileError\n"
        "import time\n"
        "f = LocalTokenFile(sys.argv[1]); bad = 0; ok = 0; seen = set()\n"
        "deadline = time.monotonic() + 60\n"
        "# Condizione, non tempo: almeno 2000 letture E almeno 3 token diversi osservati\n"
        "# (rotazioni sovrapposte alle letture), con una scadenza larga solo come rete.\n"
        "while (ok + bad < 2000 or len(seen) < 3) and time.monotonic() < deadline:\n"
        "    try:\n"
        "        seen.add(f.read()); ok += 1\n"
        "    except TokenFileError as e:\n"
        "        bad += 1; print(e.code)\n"
        "print('READS', ok, 'DISTINCT', len(seen))\n"
        "print('BAD', bad)\n"
    )
    procs = [
        subprocess.Popen(
            [sys.executable, "-c", reader, str(path)],
            stdout=subprocess.PIPE,
            text=True,
            # il figlio importa lo stesso sorgente del test (anche le copie di mutmut)
            env=subprocess_env(PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src")),
        )
        for _ in range(3)
    ]
    # Le rotazioni continuano finché i lettori sono vivi: lettura e rotazione si sovrappongono.
    while any(p.poll() is None for p in procs):
        store.rotate(path)
    outputs = [p.communicate(timeout=120)[0] for p in procs]
    assert all(out.strip().endswith("BAD 0") for out in outputs), outputs
    assert store.rotations >= 2, store.rotations  # sovrapposizione reale, non sequenziale
    for out in outputs:  # ogni lettore ha fatto le letture e ha visto le rotazioni
        reads, distinct = (
            int(x) for x in out.split("READS ")[1].split("\n")[0].split(" DISTINCT ")
        )
        assert reads >= 2000
        assert distinct >= 3, out  # più rotazioni osservate davvero durante le letture
    assert [p.name for p in secure.iterdir()] == ["api.token"]


def test_generated_store_writes_nothing_until_published(tmp_path: Path) -> None:
    from pickfair_control_api.tokens import generate_token_store

    store = generate_token_store()
    assert list(tmp_path.iterdir()) == []
    path = tmp_path / "api.token"
    store.publish(path)
    token = path.read_text()
    assert TOKEN_RE.fullmatch(token) and store.accepts(token.encode()) and mode(path) == 0o600
    assert [p.name for p in tmp_path.iterdir()] == ["api.token"]
    store.publish(path)  # ripubblicazione dello stesso token: idempotente
    assert path.read_text() == token
