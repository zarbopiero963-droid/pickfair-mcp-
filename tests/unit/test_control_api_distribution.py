"""Distribuzione immutabile di `pickfair_control_api` (opzione A wheel, opzione B manifest)."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "build_control_api_wheel.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_control_api_wheel", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["build_control_api_wheel"] = module
    spec.loader.exec_module(module)
    return module


builder = load()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_wheel_is_byte_for_byte_reproducible(tmp_path: Path) -> None:
    a = builder.build_wheel(tmp_path / "a")
    b = builder.build_wheel(tmp_path / "b")
    assert a.read_bytes() == b.read_bytes()
    assert a.name == "pickfair_control_api-1.4.0-py3-none-any.whl"


def test_wheel_contains_only_the_package_and_valid_record(tmp_path: Path) -> None:
    wheel = builder.build_wheel(tmp_path)
    with zipfile.ZipFile(wheel) as zf:
        names = zf.namelist()
        assert all(
            n.startswith(("pickfair_control_api/", "pickfair_control_api-1.4.0.dist-info/"))
            for n in names
        )
        assert not any("pickfair_mcp" in n or n.endswith(".pyc") for n in names)
        record = zf.read("pickfair_control_api-1.4.0.dist-info/RECORD").decode().splitlines()
        for row in record:
            name, digest, size = row.split(",")
            if name.endswith("RECORD"):
                continue
            data = zf.read(name)
            expected = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
            assert digest == f"sha256={expected}" and int(size) == len(data)
        metadata = zf.read("pickfair_control_api-1.4.0.dist-info/METADATA").decode()
    assert "Requires-Dist" not in metadata  # solo libreria standard: nulla da risolvere
    assert "Version: 1.4.0" in metadata


def test_contract_version_and_package_version_are_pinned_together() -> None:
    import pickfair_control_api

    assert pickfair_control_api.__version__ == pickfair_control_api.CONTRACT_VERSION == "1.4.0"


def _pip(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--no-deps",
            "--no-index",
            "--require-hashes",
            *args,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def test_offline_hash_pinned_install_works(tmp_path: Path) -> None:
    out = tmp_path / "dist"
    assert builder.main(["--out", str(out)]) == 0
    target = tmp_path / "site"
    proc = _pip(
        "--target",
        str(target),
        "--find-links",
        str(out),
        "-r",
        str(out / "requirements-control-api.txt"),
    )
    assert proc.returncode == 0, proc.stderr
    probe = (
        f"import sys; sys.path.insert(0, {str(target)!r}); import pickfair_control_api as c; "
        "print(c.__file__); print(c.schema_hash())"
    )
    run = subprocess.run(
        [sys.executable, "-I", "-c", probe], capture_output=True, text=True, check=True, timeout=60
    )
    installed_file, installed_hash = run.stdout.split()
    assert installed_file.startswith(str(target))
    from pickfair_control_api import schema_hash

    assert installed_hash == schema_hash()


def test_tampered_wheel_is_refused_by_the_hash_pin(tmp_path: Path) -> None:
    out = tmp_path / "dist"
    builder.main(["--out", str(out)])
    wheel = next(out.glob("*.whl"))
    data = bytearray(wheel.read_bytes())
    data[len(data) // 2] ^= 0x01
    wheel.write_bytes(bytes(data))
    proc = _pip(
        "--target",
        str(tmp_path / "site"),
        "--find-links",
        str(out),
        "-r",
        str(out / "requirements-control-api.txt"),
    )
    assert proc.returncode != 0
    assert "HASH" in proc.stderr.upper()


def test_manifest_detects_any_change_in_the_vendored_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = builder.manifest()
    copy = tmp_path / "pickfair_control_api"
    shutil.copytree(builder.PACKAGE, copy, ignore=shutil.ignore_patterns("__pycache__"))
    monkeypatch.setattr(builder, "PACKAGE", copy)
    assert builder.manifest() == original
    target = copy / "server.py"
    target.write_text(target.read_text() + "\n# modifica\n")
    changed = builder.manifest()
    assert changed["tree_sha256"] != original["tree_sha256"]
    assert (
        changed["files"]["pickfair_control_api/server.py"]
        != original["files"]["pickfair_control_api/server.py"]
    )
    json.dumps(changed)
