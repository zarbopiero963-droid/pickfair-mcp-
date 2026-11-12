"""Controllo automatico di deriva del catalogo (scripts/capability_drift.py).

Il core è finto e costruito in tmp_path: la CI del MCP non ha un checkout di Pickfair-nogui.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "capability_drift.py"


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("capability_drift", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["capability_drift"] = module
    spec.loader.exec_module(module)
    return module


drift = load()

EXTRACTORS = {
    "methods": [{"file": "core/runtime_controller.py", "class": "RuntimeController"}],
    "fields": [{"file": "core/system_state.py", "class": "RoserpinaConfig"}],
}
MATRIX = "| CAP-RT-01 | x |\n| CAP-STP-04 | x |\n| CAP-ROS-01 | x |\n| CAP-ORD-02 | x |\n"


def fake_core(tmp_path: Path, *, extra_method: str = "", extra_event: str = "") -> Path:
    core = tmp_path / "core_repo"
    (core / "core").mkdir(parents=True)
    (core / "services").mkdir()
    (core / "tests").mkdir()
    method = f"    def {extra_method}(self):\n        pass\n" if extra_method else ""
    (core / "core" / "runtime_controller.py").write_text(
        "class RuntimeController:\n"
        "    def get_status(self):\n        pass\n"
        "    def emergency_stop(self):\n        self.bus.publish('EMERGENCY_STOP_TRIGGERED', {})\n"
        "    def _private(self):\n        pass\n" + method
    )
    (core / "core" / "system_state.py").write_text(
        "class RoserpinaConfig:\n    table_count: int\n    x = 1\n"
    )
    publish = f"bus.publish('{extra_event}')\n" if extra_event else ""
    (core / "services" / "svc.py").write_text(
        "bus.subscribe('CMD_QUICK_BET', h)\nbus.publish('lower_case_ignored')\n"
        "bus.publish(name_variable)\n" + publish
    )
    # i test del core non contano come capacità
    (core / "tests" / "test_x.py").write_text("bus.publish('TEST_ONLY_EVENT')\n")
    return core


def base_map() -> dict[str, Any]:
    return {
        "extractors": EXTRACTORS,
        "signals": {
            "method:RuntimeController.get_status": ["CAP-RT-01"],
            "method:RuntimeController.emergency_stop": ["CAP-STP-04"],
            "event:EMERGENCY_STOP_TRIGGERED": ["CAP-STP-04"],
            "event:CMD_QUICK_BET": ["CAP-ORD-02"],
            "config:RoserpinaConfig.table_count": ["CAP-ROS-01"],
        },
    }


def run(core: Path, mapping: dict[str, Any]) -> dict[str, Any]:
    signals = drift.core_signals(core, mapping["extractors"])
    report: dict[str, Any] = drift.check(signals, mapping, drift.known_caps(MATRIX))
    return report


def test_extracts_only_public_methods_literal_events_and_fields(tmp_path: Path) -> None:
    signals = drift.core_signals(fake_core(tmp_path), EXTRACTORS)
    assert signals == set(base_map()["signals"])


def test_fully_tracked_core_is_ok(tmp_path: Path) -> None:
    report = run(fake_core(tmp_path), base_map())
    assert report["ok"] is True
    assert report["untracked"] == [] and report["signals"] == 5


def test_new_core_method_is_detected_as_untracked(tmp_path: Path) -> None:
    report = run(fake_core(tmp_path, extra_method="start_strategy"), base_map())
    assert report["ok"] is False
    assert report["untracked"] == ["method:RuntimeController.start_strategy"]


def test_new_bus_event_is_detected_as_untracked(tmp_path: Path) -> None:
    report = run(fake_core(tmp_path, extra_event="STRATEGY_ACTIVATED"), base_map())
    assert report["untracked"] == ["event:STRATEGY_ACTIVATED"]


def test_removed_core_signal_is_reported_as_orphaned(tmp_path: Path) -> None:
    mapping = base_map()
    mapping["signals"]["method:RuntimeController.removed"] = ["CAP-RT-01"]
    report = run(fake_core(tmp_path), mapping)
    assert report["ok"] is False and report["orphaned"] == ["method:RuntimeController.removed"]


def test_unknown_cap_id_is_reported(tmp_path: Path) -> None:
    mapping = base_map()
    mapping["signals"]["method:RuntimeController.get_status"] = ["CAP-RT-99"]
    report = run(fake_core(tmp_path), mapping)
    assert report["ok"] is False
    assert report["unknown_caps"] == ["method:RuntimeController.get_status->CAP-RT-99"]


@pytest.mark.parametrize(
    "entry", [[], "CAP-RT-01", {"untracked": ""}, {"untracked": "x", "y": 1}, None]
)
def test_invalid_entries_rejected(tmp_path: Path, entry: Any) -> None:
    mapping = base_map()
    mapping["signals"]["method:RuntimeController.get_status"] = entry
    report = run(fake_core(tmp_path), mapping)
    assert report["ok"] is False
    assert report["invalid_entries"] == ["method:RuntimeController.get_status"]


def test_justified_untracked_is_accepted_and_listed(tmp_path: Path) -> None:
    mapping = base_map()
    mapping["signals"]["method:RuntimeController.get_status"] = {"untracked": "interno"}
    report = run(fake_core(tmp_path), mapping)
    assert report["ok"] is True
    assert report["justified_untracked"] == ["method:RuntimeController.get_status"]


def test_missing_core_class_fails_closed(tmp_path: Path) -> None:
    core = fake_core(tmp_path)
    (core / "core" / "runtime_controller.py").write_text("class Other:\n    pass\n")
    with pytest.raises(SystemExit):
        drift.core_signals(core, EXTRACTORS)


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    core = fake_core(tmp_path)
    map_path = tmp_path / "map.json"
    matrix_path = tmp_path / "matrix.md"
    matrix_path.write_text(MATRIX)
    map_path.write_text(json.dumps(base_map()))
    assert (
        drift.main(["--core", str(core), "--map", str(map_path), "--matrix", str(matrix_path)]) == 0
    )
    fake_core(tmp_path / "b", extra_method="new_thing")
    core_b = tmp_path / "b" / "core_repo"
    assert (
        drift.main(["--core", str(core_b), "--map", str(map_path), "--matrix", str(matrix_path)])
        == 1
    )
    capsys.readouterr()


def test_repository_map_cites_only_existing_cap_ids() -> None:
    mapping = json.loads(drift.MAP_PATH.read_text(encoding="utf-8"))
    caps = drift.known_caps(drift.MATRIX_PATH.read_text(encoding="utf-8"))
    cited = {c for e in mapping["signals"].values() if isinstance(e, list) for c in e}
    assert cited and cited <= caps
    for entry in mapping["signals"].values():
        assert (isinstance(entry, list) and entry) or (
            isinstance(entry, dict) and str(entry.get("untracked", "")).strip()
        )
