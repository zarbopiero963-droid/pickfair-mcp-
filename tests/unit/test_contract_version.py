"""Versionamento del contratto e schema hash.

Il valore atteso dello schema hash è fissato qui: qualunque modifica al descrittore
canonico del contratto (route o schema di /v1/meta) cambia l'hash e deve essere
una scelta esplicita, accompagnata dall'aggiornamento della compat matrix.
"""

from __future__ import annotations

import copy

from pickfair_mcp.contract import version as v

GOLDEN_SCHEMA_HASH = "09bd5e8e6641c2c25664fe7deb05e7a8510b18d92b016ccb6f3acf9086dcf855"


def test_supported_version_is_semver_1_0_0() -> None:
    assert v.SUPPORTED_CONTRACT_VERSION == "1.0.0"


def test_schema_hash_is_stable_golden_value() -> None:
    assert v.contract_schema_hash() == GOLDEN_SCHEMA_HASH


def test_schema_hash_is_sha256_hex() -> None:
    h = v.contract_schema_hash()
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)


def test_schema_hash_changes_when_descriptor_changes() -> None:
    descriptor = copy.deepcopy(v.canonical_contract_descriptor())
    base = v.hash_descriptor(descriptor)
    descriptor["routes"] = descriptor["routes"][:-1]
    assert v.hash_descriptor(descriptor) != base


def test_hash_is_independent_of_key_order() -> None:
    descriptor = v.canonical_contract_descriptor()
    reordered = dict(reversed(list(descriptor.items())))
    assert v.hash_descriptor(reordered) == v.hash_descriptor(descriptor)


def test_compat_matrix_only_lists_the_supported_pair() -> None:
    assert dict(v.COMPAT_MATRIX) == {"1.0.0": frozenset({v.contract_schema_hash()})}


def test_capabilities_are_route_keys() -> None:
    caps = v.APPROVED_CAPABILITIES
    assert "GET /v1/meta" in caps
    assert len(caps) == 25


def test_hash_handles_non_ascii_text_deterministically() -> None:
    h = v.hash_descriptor({"note": "perdita è sempre contabilizzata"})
    assert len(h) == 64
    assert h == v.hash_descriptor({"note": "perdita \u00e8 sempre contabilizzata"})
