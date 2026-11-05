"""G8 (PF-UNIVERSAL-360-TESTING): manifest delle suite MCP/Control API e runner a argv fisso."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import run_suites  # noqa: E402

# Campi chiusi delle suite del catalogo canonico (scripts/pf_test_dispatch.py, Pickfair-nogui main 911562ad).
PF_SUITE_FIELDS = {"id", "component", "behaviour", "category", "runner", "args", "environment", "risk",
                   "timeout_seconds", "resources", "datasets", "evidence", "requires", "criteria"}


def manifest() -> dict[str, Any]:
    return run_suites.validate_manifest(run_suites.MANIFEST.read_bytes())


def test_manifest_is_valid_and_declares_the_catalog_gap() -> None:
    cat = manifest()
    assert cat["pf_catalog_status"]["state"] == "UNSUPPORTED" and cat["pf_catalog_status"]["reason"]
    assert set(cat["campaigns"]["all"]) == {s["id"] for s in cat["suites"]}


def test_every_test_file_of_the_repository_belongs_to_a_suite() -> None:
    args = [a for s in manifest()["suites"] for a in s["args"]]
    files = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "tests").rglob("test_*.py"))
    uncovered = [f for f in files if not any(f == a or f.startswith(a.rstrip("/") + "/") for a in args)]
    assert uncovered == []


def test_crossrepo_suite_requires_the_core_and_is_never_pass_without_it(
        monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    suite = run_suites.resolve(manifest(), "suite:mcp-crossrepo")[0]
    assert suite["requires"] == ["PICKFAIR_CORE_PATH", "PICKFAIR_CORE_PYTHON"]
    monkeypatch.delenv("PICKFAIR_CORE_PATH", raising=False)
    result = run_suites.run_suite(suite, tmp_path)
    assert result["verdict"] == "BLOCKED" and result["reason"] == "REQUIRES_MISSING"


@pytest.mark.parametrize("target", ["suite:nope", "campaign:nope", "dev:tests/unit", "suite:", "x"])
def test_unknown_targets_are_refused(target: str) -> None:
    with pytest.raises(run_suites.Refused):
        run_suites.resolve(manifest(), target)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda s: s.update(args=["tests/../src"]),
        lambda s: s.update(args=["-k", "x"]),
        lambda s: s.update(args=["/etc/passwd"]),
        lambda s: s.update(args=["tests/does_not_exist"]),
        lambda s: s.update(args=["tests/./unit"]),
        lambda s: s.update(runner="python"),
        lambda s: s.update(environment="LIVE"),
        lambda s: s.update(extra=1),
        lambda s: s.update(requires=["rm -rf"]),
        lambda s: s.update(allowed_skips=[{"nodeid": "tests/other/x.py::t", "reason": "r"}]),
        lambda s: s.update(criteria={"PASS": "x"}),
    ],
)
def test_unsafe_manifests_are_refused(mutate: Any) -> None:
    cat = json.loads(run_suites.MANIFEST.read_text())
    mutate(cat["suites"][0])
    with pytest.raises(run_suites.Refused):
        run_suites.validate_manifest(json.dumps(cat).encode())


def write_junit(path: Path, cases: str) -> None:
    path.write_text(f'<testsuites><testsuite name="pytest">{cases}</testsuite></testsuites>')


@pytest.mark.parametrize(
    ("cases", "code", "verdict"),
    [
        ('<testcase classname="tests.unit.test_a" name="t1"/>', 0, "PASS"),
        ('<testcase classname="tests.unit.test_a" name="t1"><failure/></testcase>', 1, "FAIL"),
        ('<testcase classname="tests.unit.test_a" name="t1"><error/></testcase>', 1, "FAIL"),
        ('<testcase classname="tests.unit.test_a" name="t1"><skipped/></testcase>', 0, "BLOCKED"),
        ('<testcase classname="tests.unit.test_journal" name="test_permission_denied_fails_closed">'
         '<skipped/></testcase><testcase classname="tests.unit.test_a" name="t2"/>', 0, "PASS"),
        ("", 5, "BLOCKED"),
    ],
)
def test_verdicts_follow_the_criteria(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cases: str, code: int,
                                      verdict: str) -> None:
    suite = run_suites.resolve(manifest(), "suite:mcp-unit")[0]

    class Done:
        returncode = code

    def fake_run(argv: list[str], **kwargs: Any) -> Done:
        assert argv[-len(suite["args"]):] == suite["args"]  # argv fisso dal manifest
        assert not any(a.startswith("-k") for a in argv)
        junit = next(a for a in argv if a.startswith("--junitxml=")).split("=", 1)[1]
        write_junit(Path(junit), cases)
        return Done()

    monkeypatch.setattr(run_suites.subprocess, "run", fake_run)
    assert run_suites.run_suite(suite, tmp_path)["verdict"] == verdict


def test_core_catalog_proposal_matches_the_canonical_schema() -> None:
    proposal = json.loads((ROOT / "catalog" / "g8" / "pf-test-catalog.control-api.json").read_text())
    assert proposal["schema"] == "pf-test-catalog/1"
    for s in proposal["suites"]:
        assert set(s) == PF_SUITE_FIELDS
        assert s["runner"] == "pytest" and all(a.startswith("tests/control_api") for a in s["args"])
        assert s["environment"] in run_suites.ENVIRONMENTS and set(s["criteria"]) == {"PASS", "FAIL", "BLOCKED"}
