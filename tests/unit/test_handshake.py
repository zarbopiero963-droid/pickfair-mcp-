"""Handshake di versione/capability: fail-closed in ogni caso non dimostrato compatibile."""

from __future__ import annotations

import anyio
import pytest

from pickfair_mcp.adapters.simulated import Scenario, SimulatedControlApiAdapter
from pickfair_mcp.contract.models import MetaResponse
from pickfair_mcp.contract.version import (
    APPROVED_CAPABILITIES,
    COMPAT_MATRIX,
    SUPPORTED_CONTRACT_VERSION,
    contract_schema_hash,
)
from pickfair_mcp.errors import ErrorCode
from pickfair_mcp.policy.handshake import (
    HANDSHAKE_REQUIRED_CAPABILITIES,
    HandshakeFailed,
    HandshakeGuard,
    HandshakeStatus,
    check_compatibility,
)

pytestmark = pytest.mark.anyio

META_CAP = frozenset({"GET /v1/meta"})


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def make_meta(**overrides: object) -> MetaResponse:
    data: dict[str, object] = {
        "contract_version": SUPPORTED_CONTRACT_VERSION,
        "capabilities": ("GET /v1/meta", "GET /v1/status"),
        "git_sha": "c" * 40,
        "schema_hash": contract_schema_hash(),
    }
    data.update(overrides)
    return MetaResponse.model_validate(data)


# --- funzione pura ---------------------------------------------------------


def test_pure_check_accepts_supported_pair() -> None:
    reasons = check_compatibility(
        make_meta(), matrix=COMPAT_MATRIX, approved=APPROVED_CAPABILITIES, required=META_CAP
    )
    assert reasons == ()


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"contract_version": "2.0.0"}, "VERSION_UNSUPPORTED"),
        ({"contract_version": "1.1.0"}, "VERSION_UNSUPPORTED"),
        ({"contract_version": "0.9.0"}, "VERSION_UNSUPPORTED"),
        ({"schema_hash": "d" * 64}, "SCHEMA_HASH_UNKNOWN"),
        ({"capabilities": ("GET /v1/status",)}, "CAPABILITY_MISSING:GET /v1/meta"),
        (
            {"capabilities": ("GET /v1/meta", "POST /v1/cashout/all")},
            "CAPABILITY_NOT_APPROVED",
        ),
    ],
)
def test_pure_check_rejects(overrides: dict[str, object], expected: str) -> None:
    reasons = check_compatibility(
        make_meta(**overrides),
        matrix=COMPAT_MATRIX,
        approved=APPROVED_CAPABILITIES,
        required=META_CAP,
    )
    assert expected in reasons


def test_version_mismatch_does_not_check_hash_of_other_version() -> None:
    # Un hash valido per 1.0.0 non rende compatibile una versione diversa.
    reasons = check_compatibility(
        make_meta(contract_version="1.0.1"),
        matrix=COMPAT_MATRIX,
        approved=APPROVED_CAPABILITIES,
        required=META_CAP,
    )
    assert "VERSION_UNSUPPORTED" in reasons


def test_handshake_requires_meta_capability() -> None:
    assert frozenset({"GET /v1/meta"}) == HANDSHAKE_REQUIRED_CAPABILITIES


# --- guard con adapter simulato --------------------------------------------


async def test_compatible_handshake() -> None:
    adapter = SimulatedControlApiAdapter()
    guard = HandshakeGuard(adapter, timeout_s=1.0)
    result = await guard.perform()
    assert result.status is HandshakeStatus.COMPATIBLE
    assert result.reasons == ()
    assert result.meta is not None
    assert result.error_code is None
    assert result.epoch == adapter.connection_epoch


@pytest.mark.parametrize(
    ("scenario", "status", "code"),
    [
        (
            Scenario.INCOMPATIBLE_MAJOR,
            HandshakeStatus.INCOMPATIBLE,
            ErrorCode.CONTRACT_INCOMPATIBLE,
        ),
        (Scenario.UNSUPPORTED_MINOR, HandshakeStatus.INCOMPATIBLE, ErrorCode.CONTRACT_INCOMPATIBLE),
        (
            Scenario.SCHEMA_HASH_MISMATCH,
            HandshakeStatus.INCOMPATIBLE,
            ErrorCode.CONTRACT_INCOMPATIBLE,
        ),
        (
            Scenario.MISSING_META_CAPABILITY,
            HandshakeStatus.INCOMPATIBLE,
            ErrorCode.CONTRACT_INCOMPATIBLE,
        ),
        (
            Scenario.UNAPPROVED_CAPABILITY,
            HandshakeStatus.INCOMPATIBLE,
            ErrorCode.CONTRACT_INCOMPATIBLE,
        ),
        (Scenario.MALFORMED, HandshakeStatus.INCOMPATIBLE, ErrorCode.UPSTREAM_INVALID_RESPONSE),
        (Scenario.EXTRA_FIELD, HandshakeStatus.INCOMPATIBLE, ErrorCode.UPSTREAM_INVALID_RESPONSE),
        (Scenario.TIMEOUT, HandshakeStatus.UNAVAILABLE, ErrorCode.UPSTREAM_TIMEOUT),
        (Scenario.UNAVAILABLE, HandshakeStatus.UNAVAILABLE, ErrorCode.UPSTREAM_UNAVAILABLE),
    ],
)
async def test_failing_scenarios(
    scenario: Scenario, status: HandshakeStatus, code: ErrorCode
) -> None:
    guard = HandshakeGuard(SimulatedControlApiAdapter(scenario), timeout_s=0.05)
    with anyio.fail_after(5):  # il guard deve terminare da solo, mai bloccarsi
        result = await guard.perform()
    assert result.status is status
    assert result.error_code is code
    assert result.meta is None
    assert result.reasons
    assert result.epoch == 1
    with pytest.raises(HandshakeFailed) as excinfo, anyio.fail_after(5):
        await guard.require_compatible(META_CAP)
    assert excinfo.value.code is code
    assert excinfo.value.status is status
    assert excinfo.value.reasons == result.reasons
    assert str(excinfo.value) == code.value


async def test_require_compatible_reuses_handshake_within_epoch() -> None:
    adapter = SimulatedControlApiAdapter()
    guard = HandshakeGuard(adapter, timeout_s=1.0)
    await guard.require_compatible(META_CAP)
    await guard.require_compatible(META_CAP)
    assert adapter.meta_calls == 1


async def test_reconnect_forces_new_handshake() -> None:
    adapter = SimulatedControlApiAdapter()
    guard = HandshakeGuard(adapter, timeout_s=1.0)
    await guard.require_compatible(META_CAP)
    adapter.reconnect(Scenario.INCOMPATIBLE_MAJOR)
    with pytest.raises(HandshakeFailed) as excinfo:
        await guard.require_compatible(META_CAP)
    assert excinfo.value.code is ErrorCode.CONTRACT_INCOMPATIBLE
    assert adapter.meta_calls == 2


async def test_incompatible_stays_blocked_without_reconnect() -> None:
    adapter = SimulatedControlApiAdapter(Scenario.INCOMPATIBLE_MAJOR)
    guard = HandshakeGuard(adapter, timeout_s=1.0)
    await guard.perform()
    calls = adapter.meta_calls
    adapter.set_scenario_without_reconnect(Scenario.COMPATIBLE)
    with pytest.raises(HandshakeFailed):
        await guard.require_compatible(META_CAP)
    assert adapter.meta_calls == calls  # nessuna nuova chiamata: resta bloccato


async def test_unavailable_is_retried_on_next_requirement() -> None:
    adapter = SimulatedControlApiAdapter(Scenario.UNAVAILABLE)
    guard = HandshakeGuard(adapter, timeout_s=1.0)
    with pytest.raises(HandshakeFailed):
        await guard.require_compatible(META_CAP)
    adapter.set_scenario_without_reconnect(Scenario.COMPATIBLE)
    meta = await guard.require_compatible(META_CAP)
    assert meta.contract_version == SUPPORTED_CONTRACT_VERSION


async def test_require_capability_not_advertised_is_refused() -> None:
    adapter = SimulatedControlApiAdapter()
    guard = HandshakeGuard(adapter, timeout_s=1.0)
    with pytest.raises(HandshakeFailed) as excinfo:
        await guard.require_compatible(frozenset({"POST /v1/orders"}))
    assert excinfo.value.code is ErrorCode.CONTRACT_INCOMPATIBLE
    assert excinfo.value.status is HandshakeStatus.INCOMPATIBLE
    assert "CAPABILITY_MISSING:POST /v1/orders" in excinfo.value.reasons


async def test_require_capability_outside_approved_set_is_refused() -> None:
    guard = HandshakeGuard(SimulatedControlApiAdapter(), timeout_s=1.0)
    with pytest.raises(HandshakeFailed) as excinfo:
        await guard.require_compatible(frozenset({"POST /v1/cashout/all"}))
    assert excinfo.value.code is ErrorCode.CONTRACT_INCOMPATIBLE
    assert "CAPABILITY_REQUIRED_NOT_APPROVED:POST /v1/cashout/all" in excinfo.value.reasons


async def test_concurrent_requirements_share_one_handshake() -> None:
    adapter = SimulatedControlApiAdapter(delay_s=0.02)
    guard = HandshakeGuard(adapter, timeout_s=1.0)
    async with anyio.create_task_group() as tg:
        for _ in range(10):
            tg.start_soon(guard.require_compatible, META_CAP)
    assert adapter.meta_calls == 1


async def test_timeout_is_bounded() -> None:
    adapter = SimulatedControlApiAdapter(Scenario.TIMEOUT)
    guard = HandshakeGuard(adapter, timeout_s=0.05)
    with anyio.fail_after(2):
        result = await guard.perform()
    assert result.status is HandshakeStatus.UNAVAILABLE
    assert result.reasons == ("UPSTREAM_TIMEOUT",)


@pytest.mark.parametrize(
    ("bad", "message"),
    [
        (0, "timeout out of range"),
        (-1, "timeout out of range"),
        (float("nan"), "timeout out of range"),
        (float("inf"), "timeout out of range"),
        (31.0, "timeout out of range"),
        (True, "timeout must be a number of seconds"),
        ("1", "timeout must be a number of seconds"),
    ],
)
def test_guard_rejects_invalid_timeout(bad: float, message: str) -> None:
    with pytest.raises(ValueError, match=f"^{message}$"):
        HandshakeGuard(SimulatedControlApiAdapter(), timeout_s=bad)


async def test_unexpected_adapter_exception_is_fail_closed() -> None:
    class Broken(SimulatedControlApiAdapter):
        async def get_meta_raw(self) -> bytes:
            raise RuntimeError("secret-token-abc")

    guard = HandshakeGuard(Broken(), timeout_s=1.0)
    result = await guard.perform()
    assert result.status is HandshakeStatus.UNAVAILABLE
    assert result.error_code is ErrorCode.UPSTREAM_UNAVAILABLE
    assert result.reasons == ("ADAPTER_FAILURE",)
    assert result.epoch == 1


async def test_adapter_level_timeout_is_mapped() -> None:
    from pickfair_mcp.adapters.base import UpstreamTimeout

    class SlowTransport(SimulatedControlApiAdapter):
        async def get_meta_raw(self) -> bytes:
            raise UpstreamTimeout

    result = await HandshakeGuard(SlowTransport(), timeout_s=1.0).perform()
    assert result.status is HandshakeStatus.UNAVAILABLE
    assert result.error_code is ErrorCode.UPSTREAM_TIMEOUT
    assert result.reasons == ("UPSTREAM_TIMEOUT",)
    assert result.epoch == 1


@pytest.mark.parametrize(
    ("scenario", "reasons"),
    [
        (Scenario.TIMEOUT, ("UPSTREAM_TIMEOUT",)),
        (Scenario.UNAVAILABLE, ("UPSTREAM_UNAVAILABLE",)),
        (Scenario.MALFORMED, ("UPSTREAM_INVALID_RESPONSE:NOT_JSON",)),
        (Scenario.EXTRA_FIELD, ("UPSTREAM_INVALID_RESPONSE:SCHEMA_VIOLATION",)),
        (Scenario.INCOMPATIBLE_MAJOR, ("VERSION_UNSUPPORTED",)),
        (Scenario.SCHEMA_HASH_MISMATCH, ("SCHEMA_HASH_UNKNOWN",)),
        (Scenario.MISSING_META_CAPABILITY, ("CAPABILITY_MISSING:GET /v1/meta",)),
        (Scenario.UNAPPROVED_CAPABILITY, ("CAPABILITY_NOT_APPROVED",)),
    ],
)
async def test_exact_reason_codes(scenario: Scenario, reasons: tuple[str, ...]) -> None:
    adapter = SimulatedControlApiAdapter(scenario)
    adapter.reconnect()  # epoch 2: il risultato deve riportare l'epoch corrente
    result = await HandshakeGuard(adapter, timeout_s=0.05).perform()
    assert result.reasons == reasons
    assert result.epoch == 2
