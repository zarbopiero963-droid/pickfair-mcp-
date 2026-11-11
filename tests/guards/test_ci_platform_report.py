"""MCP-CI: classificatore degli esiti per piattaforma (nessuno skip silenzioso, nessun falso verde).

Mandato owner PF-OWNER-MCP-PARALLEL-EXECUTION-20261111, priorità 1. Il classificatore legge il
rapporto JUnit di pytest e il manifest versionato `ci/platform_expectations.json`:

- un test che fallisce senza essere dichiarato bloccato → FAIL (difetto inatteso);
- un test dichiarato bloccato che fallisce o viene saltato → BLOCKED_BY_DEPENDENCY:<dipendenza>,
  mai PASS: con almeno un blocco il verdetto non è verde;
- un test dichiarato bloccato che passa, o che non esiste più → FAIL (manifest da aggiornare,
  il blocco non deve sopravvivere alla correzione);
- uno skip non dichiarato → FAIL (nessuno skip silenzioso);
- rapporto assente, illeggibile o vuoto, oppure pytest uscito con un codice diverso da 0/1 → FAIL.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from tests.conftest import REPO_ROOT

pytestmark = pytest.mark.guard

SCRIPT = REPO_ROOT / "scripts" / "ci_platform_report.py"
MANIFEST = REPO_ROOT / "ci" / "platform_expectations.json"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ci_platform_report", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ci_platform_report"] = mod
    spec.loader.exec_module(mod)
    return mod


def junit(path: Path, cases: list[tuple[str, str, str]]) -> Path:
    """cases: (classname, name, esito) con esito in pass/fail/error/skip."""
    rows = []
    for classname, name, outcome in cases:
        body = {
            "pass": "",
            "fail": '<failure message="boom">trace</failure>',
            "error": '<error message="boom">trace</error>',
            "skip": '<skipped type="pytest.skip" message="motivo">motivo</skipped>',
        }[outcome]
        rows.append(f'<testcase classname="{classname}" name="{name}" time="0.1">{body}</testcase>')
    path.write_text(
        '<?xml version="1.0" encoding="utf-8"?><testsuites><testsuite name="pytest">'
        + "".join(rows)
        + "</testsuite></testsuites>",
        encoding="utf-8",
    )
    return path


def expectations(
    path: Path, platform: str, blocked: dict[str, Any], skips: dict[str, Any] | None = None
) -> Path:
    data = {
        "schema": 1,
        "dependencies": {"MCP-WIN": "parità Windows di MCP e Control API (#625)"},
        "platforms": {platform: {"blocked": blocked, "skips": skips or {}}},
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def run(
    mod: ModuleType,
    tmp: Path,
    cases: list[tuple[str, str, str]],
    *,
    platform: str = "windows",
    blocked: dict[str, Any] | None = None,
    skips: dict[str, Any] | None = None,
    pytest_rc: int = 1,
) -> Any:
    report = junit(tmp / "r.xml", cases)
    exp = expectations(tmp / "e.json", platform, blocked or {}, skips)
    return mod.classify(report, exp, platform, pytest_rc)


BLOCK = {"dependency": "MCP-WIN", "reason": "lock esclusivo msvcrt mai verificato"}


def test_all_passing_is_pass(tmp_path: Path) -> None:
    res = run(load(), tmp_path, [("tests.unit.test_a", "test_x", "pass")], pytest_rc=0)
    assert res.verdict == "PASS" and res.exit_code == 0


def test_undeclared_failure_is_fail(tmp_path: Path) -> None:
    res = run(load(), tmp_path, [("tests.unit.test_a", "test_x", "fail")])
    assert res.verdict == "FAIL" and res.exit_code == 1
    assert res.unexpected == ["tests.unit.test_a::test_x"]


def test_collection_error_is_fail(tmp_path: Path) -> None:
    res = run(load(), tmp_path, [("", "tests.unit.test_a", "error")])
    assert res.verdict == "FAIL" and res.unexpected == ["::tests.unit.test_a"]


def test_declared_blocked_failure_is_blocked_never_pass(tmp_path: Path) -> None:
    res = run(
        load(),
        tmp_path,
        [("tests.unit.test_a", "test_x", "fail"), ("tests.unit.test_a", "test_y", "pass")],
        blocked={"tests.unit.test_a::test_x": BLOCK},
    )
    assert res.verdict == "BLOCKED_BY_DEPENDENCY:MCP-WIN"
    assert res.exit_code not in (0, 1)  # job rosso ma distinto da un FAIL inatteso
    assert res.blocked == {"tests.unit.test_a::test_x": "MCP-WIN"}


def test_declared_blocked_skip_is_blocked(tmp_path: Path) -> None:
    res = run(
        load(),
        tmp_path,
        [("tests.e2e.test_k", "test_kill", "skip")],
        blocked={"tests.e2e.test_k::test_kill": BLOCK},
        pytest_rc=0,
    )
    assert res.verdict == "BLOCKED_BY_DEPENDENCY:MCP-WIN" and res.exit_code not in (0, 1)


def test_blocked_test_that_passes_is_stale_fail(tmp_path: Path) -> None:
    res = run(
        load(),
        tmp_path,
        [("tests.unit.test_a", "test_x", "pass")],
        blocked={"tests.unit.test_a::test_x": BLOCK},
        pytest_rc=0,
    )
    assert res.verdict == "FAIL" and res.stale == ["tests.unit.test_a::test_x"]


def test_blocked_test_that_no_longer_exists_is_fail(tmp_path: Path) -> None:
    res = run(
        load(),
        tmp_path,
        [("tests.unit.test_a", "test_x", "pass")],
        blocked={"tests.unit.test_a::test_gone": BLOCK},
        pytest_rc=0,
    )
    assert res.verdict == "FAIL" and res.missing == ["tests.unit.test_a::test_gone"]


def test_undeclared_skip_is_fail(tmp_path: Path) -> None:
    res = run(load(), tmp_path, [("tests.unit.test_a", "test_x", "skip")], pytest_rc=0)
    assert res.verdict == "FAIL" and res.undeclared_skips == ["tests.unit.test_a::test_x"]


def test_declared_environment_skip_is_allowed_and_reported(tmp_path: Path) -> None:
    res = run(
        load(),
        tmp_path,
        [("tests.unit.test_a", "test_x", "skip"), ("tests.unit.test_a", "test_y", "pass")],
        platform="linux",
        skips={"tests.unit.test_a::test_x": "ENV: root ignora i permessi"},
        pytest_rc=0,
    )
    assert res.verdict == "PASS" and res.env_skips == ["tests.unit.test_a::test_x"]


def test_unknown_dependency_is_rejected(tmp_path: Path) -> None:
    mod = load()
    with pytest.raises(mod.ManifestError):
        run(
            mod,
            tmp_path,
            [("tests.unit.test_a", "test_x", "fail")],
            blocked={"tests.unit.test_a::test_x": {"dependency": "SOMEDAY", "reason": "x"}},
        )


def test_blocked_entry_without_reason_is_rejected(tmp_path: Path) -> None:
    mod = load()
    with pytest.raises(mod.ManifestError):
        run(
            mod,
            tmp_path,
            [("tests.unit.test_a", "test_x", "fail")],
            blocked={"tests.unit.test_a::test_x": {"dependency": "MCP-WIN", "reason": ""}},
        )


def test_unknown_platform_is_rejected(tmp_path: Path) -> None:
    mod = load()
    report = junit(tmp_path / "r.xml", [("tests.unit.test_a", "test_x", "pass")])
    exp = expectations(tmp_path / "e.json", "linux", {})
    with pytest.raises(mod.ManifestError):
        mod.classify(report, exp, "macos", 0)


@pytest.mark.parametrize("rc", [2, 3, 4, 5, -9, 124])
def test_pytest_abnormal_exit_is_fail_even_if_report_is_green(tmp_path: Path, rc: int) -> None:
    res = run(load(), tmp_path, [("tests.unit.test_a", "test_x", "pass")], pytest_rc=rc)
    assert res.verdict == "FAIL" and res.exit_code == 1


def test_rc1_without_any_failure_in_report_is_fail(tmp_path: Path) -> None:
    """pytest dice «fallito» ma il rapporto non mostra fallimenti: incoerenza, mai verde."""
    res = run(load(), tmp_path, [("tests.unit.test_a", "test_x", "pass")], pytest_rc=1)
    assert res.verdict == "FAIL"


@pytest.mark.parametrize("content", ["", "<testsuites></testsuites>", "non xml"])
def test_missing_or_empty_report_is_fail(tmp_path: Path, content: str) -> None:
    mod = load()
    report = tmp_path / "r.xml"
    report.write_text(content, encoding="utf-8")
    exp = expectations(tmp_path / "e.json", "windows", {})
    assert mod.classify(report, exp, "windows", 0).verdict == "FAIL"
    assert mod.classify(tmp_path / "assente.xml", exp, "windows", 0).verdict == "FAIL"


def test_main_writes_summary_and_returns_exit_code(tmp_path: Path) -> None:
    mod = load()
    report = junit(tmp_path / "r.xml", [("tests.unit.test_a", "test_x", "fail")])
    exp = expectations(tmp_path / "e.json", "windows", {"tests.unit.test_a::test_x": BLOCK})
    summary = tmp_path / "summary.md"
    rc = mod.main(
        [
            "--junit",
            str(report),
            "--expectations",
            str(exp),
            "--platform",
            "windows",
            "--pytest-rc",
            "1",
            "--summary",
            str(summary),
        ]
    )
    assert rc not in (0, 1)
    text = summary.read_text(encoding="utf-8")
    assert "BLOCKED_BY_DEPENDENCY:MCP-WIN" in text and "tests.unit.test_a::test_x" in text
    assert "PASS" not in text.split("Verdetto")[1].splitlines()[0]


def test_repository_manifest_is_valid_and_declares_every_platform_of_the_workflow() -> None:
    mod = load()
    manifest = mod.load_manifest(MANIFEST)
    assert set(manifest["platforms"]) == {"linux", "windows"}
    for entry in manifest["platforms"]["windows"]["blocked"].values():
        assert entry["dependency"] == "MCP-WIN" and entry["reason"]
    # Linux non ha blocchi: su Linux ogni test deve passare davvero.
    assert manifest["platforms"]["linux"]["blocked"] == {}


def test_workflow_runs_the_classifier_on_both_platforms_without_masking() -> None:
    wf = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "windows-latest" in wf and "ubuntu-latest" in wf
    assert '"3.11"' in wf and '"3.12"' in wf
    assert wf.count("scripts/ci_platform_report.py") >= 2
    assert "--platform windows" in wf and "--platform linux" in wf
    # nessun mascheramento del verdetto: il classificatore decide l'esito del job
    assert "|| true" not in wf.split("ci_platform_report.py")[1].split("\n")[0]
    # l'installazione resta con hash anche su Windows (nessun fallback senza hash)
    assert wf.count("--require-hashes") >= 3
