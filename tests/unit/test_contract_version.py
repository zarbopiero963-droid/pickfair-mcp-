"""Versionamento del contratto e schema hash.

Il valore atteso dello schema hash è fissato qui: qualunque modifica al descrittore
canonico del contratto (route, schemi upstream, schemi dei tool, codici d'errore,
semantica) cambia l'hash e deve essere
una scelta esplicita, accompagnata dall'aggiornamento della compat matrix.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from pickfair_mcp.contract import version as v

GOLDEN_SCHEMA_HASH = "194301d45e858201d71ed5a7057d63dc7294a9c32d8c16f1a12cb140a1ecf325"


def test_supported_version_is_semver_1_5_0() -> None:
    assert v.SUPPORTED_CONTRACT_VERSION == "1.16.0"


def test_schema_hash_is_stable_golden_value() -> None:
    assert v.contract_schema_hash() == GOLDEN_SCHEMA_HASH


def test_schema_hash_is_sha256_hex() -> None:
    h = v.contract_schema_hash()
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_schema_hash_changes_when_descriptor_changes() -> None:
    descriptor = copy.deepcopy(v.load_contract_descriptor())
    base = v.hash_descriptor(descriptor)
    descriptor["routes"] = descriptor["routes"][:-1]
    assert v.hash_descriptor(descriptor) != base


def test_hash_is_independent_of_key_order() -> None:
    descriptor = v.load_contract_descriptor()
    reordered = dict(reversed(list(descriptor.items())))
    assert v.hash_descriptor(reordered) == v.hash_descriptor(descriptor)


def test_compat_matrix_only_lists_the_supported_pair() -> None:
    assert dict(v.COMPAT_MATRIX) == {"1.16.0": frozenset({v.contract_schema_hash()})}


def test_capabilities_are_route_keys() -> None:
    caps = v.APPROVED_CAPABILITIES
    assert "GET /v1/meta" in caps
    assert len(caps) == 29


def test_hash_handles_non_ascii_text_deterministically() -> None:
    h = v.hash_descriptor({"note": "perdita è sempre contabilizzata"})
    assert len(h) == 64
    assert h == v.hash_descriptor({"note": "perdita \u00e8 sempre contabilizzata"})


# I rami di errore di `load_contract_descriptor` si provano al momento del test, puntando
# `DESCRIPTOR_PATH` a un file temporaneo: COMPAT_MATRIX è calcolata all'import e non li esercita.


def test_load_descriptor_rejects_a_different_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "descriptor.json"
    path.write_text(json.dumps({"contract_version": "1.15.0"}), encoding="ascii")
    monkeypatch.setattr(v, "DESCRIPTOR_PATH", path)
    with pytest.raises(ValueError) as excinfo:
        v.load_contract_descriptor()
    assert excinfo.value.args == ("descriptor version mismatch",)


def test_load_descriptor_rejects_a_non_object(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "descriptor.json"
    path.write_text("[]", encoding="ascii")
    monkeypatch.setattr(v, "DESCRIPTOR_PATH", path)
    with pytest.raises(ValueError) as excinfo:
        v.load_contract_descriptor()
    assert excinfo.value.args == ("descriptor version mismatch",)


def test_load_descriptor_accepts_the_supported_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "descriptor.json"
    path.write_text(json.dumps({"contract_version": "1.16.0", "x": 1}), encoding="ascii")
    monkeypatch.setattr(v, "DESCRIPTOR_PATH", path)
    assert v.load_contract_descriptor() == {"contract_version": "1.16.0", "x": 1}


def test_load_descriptor_reads_strict_ascii(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "descriptor.json"
    path.write_bytes('{"contract_version": "1.16.0", "note": "è"}'.encode())
    monkeypatch.setattr(v, "DESCRIPTOR_PATH", path)
    with pytest.raises(UnicodeDecodeError):
        v.load_contract_descriptor()


class _RecordingPath:
    """Registra la codifica richiesta: il descrittore canonico si legge solo come ASCII."""

    def __init__(self, text: str) -> None:
        self.text = text
        self.encodings: list[object] = []

    def read_text(self, encoding: object = None) -> str:
        self.encodings.append(encoding)
        return self.text


def test_load_descriptor_requests_the_ascii_codec_by_its_canonical_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = _RecordingPath(json.dumps({"contract_version": "1.16.0"}))
    monkeypatch.setattr(v, "DESCRIPTOR_PATH", recorder)
    v.load_contract_descriptor()
    assert recorder.encodings == ["ascii"]
