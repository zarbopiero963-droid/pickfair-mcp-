"""MCP-01c: principal, scope e matrice completa principal x tool."""

from __future__ import annotations

import itertools
from enum import Enum

import pytest

from pickfair_mcp.auth import (
    OWNER_ONLY_TOOLS,
    TOOL_SCOPES,
    AuthorizationDenied,
    Principal,
    PrincipalInvalid,
    Scope,
    authorize,
    parse_principal,
    required_scope,
)
from pickfair_mcp.contract.routes import ROUTES_BY_KEY, RouteKind
from pickfair_mcp.errors import ErrorCode
from pickfair_mcp.tools.catalog import APPROVED_TOOL_ROUTES

ALL_SCOPE_SETS = [
    frozenset(c) for n in range(1, len(Scope) + 1) for c in itertools.combinations(list(Scope), n)
]


def test_scopes_are_exactly_the_four_declared() -> None:
    assert {s.value for s in Scope} == {"read", "write", "admin", "owner"}


def test_every_catalog_tool_has_exactly_one_declared_scope() -> None:
    assert set(TOOL_SCOPES) == set(APPROVED_TOOL_ROUTES)
    assert all(isinstance(s, Scope) for s in TOOL_SCOPES.values())


def test_read_routes_need_read_and_commands_never_need_read() -> None:
    for tool, route in APPROVED_TOOL_ROUTES.items():
        is_read = ROUTES_BY_KEY[route].kind is RouteKind.READ
        assert (TOOL_SCOPES[tool] is Scope.READ) is is_read, tool


def test_owner_only_operations() -> None:
    assert OWNER_ONLY_TOOLS == frozenset({"set_mode", "patch_config"})
    for tool in OWNER_ONLY_TOOLS:
        assert TOOL_SCOPES[tool] is Scope.OWNER
    assert required_scope("stop", qualifier="EMERGENCY") is Scope.OWNER
    assert required_scope("stop") is Scope.WRITE
    assert required_scope("stop", qualifier="PAUSE") is Scope.WRITE
    assert required_scope("get_meta", qualifier="EMERGENCY") is Scope.READ


def test_table_is_immutable() -> None:
    with pytest.raises(TypeError):
        TOOL_SCOPES["get_meta"] = Scope.OWNER  # type: ignore[index]


def test_unknown_tool_has_no_scope() -> None:
    with pytest.raises(AuthorizationDenied) as exc:
        required_scope("place_order_now")
    assert exc.value.reason == "SCOPE_UNDECLARED"


@pytest.mark.parametrize(
    "scopes", ALL_SCOPE_SETS, ids=lambda s: "+".join(sorted(x.value for x in s))
)
@pytest.mark.parametrize("tool", sorted(APPROVED_TOOL_ROUTES))
def test_full_principal_by_tool_matrix(scopes: frozenset[Scope], tool: str) -> None:
    principal = Principal(principal_id="p1", scopes=scopes)
    needed = TOOL_SCOPES[tool]
    if needed in scopes:
        authorize(principal, tool)
    else:
        with pytest.raises(AuthorizationDenied) as exc:
            authorize(principal, tool)
        assert exc.value.reason == "SCOPE_MISSING"
        err = exc.value.to_tool_error()
        assert err.code is ErrorCode.FORBIDDEN
        assert err.reasons == ("SCOPE_MISSING",)


def test_no_implicit_hierarchy() -> None:
    owner = Principal(principal_id="boss", scopes=frozenset({Scope.OWNER}))
    with pytest.raises(AuthorizationDenied):
        authorize(owner, "get_meta")
    with pytest.raises(AuthorizationDenied):
        authorize(owner, "place_order")
    admin = Principal(principal_id="adm", scopes=frozenset({Scope.ADMIN}))
    with pytest.raises(AuthorizationDenied):
        authorize(admin, "set_mode")
    writer = Principal(principal_id="w", scopes=frozenset({Scope.WRITE}))
    with pytest.raises(AuthorizationDenied):
        authorize(writer, "get_status")


def test_emergency_stop_is_owner_only() -> None:
    writer = Principal(principal_id="w", scopes=frozenset({Scope.WRITE}))
    authorize(writer, "stop")
    with pytest.raises(AuthorizationDenied):
        authorize(writer, "stop", qualifier="EMERGENCY")
    owner = Principal(principal_id="o", scopes=frozenset({Scope.OWNER}))
    authorize(owner, "stop", qualifier="EMERGENCY")


def test_missing_principal_fails_closed() -> None:
    with pytest.raises(AuthorizationDenied) as exc:
        authorize(None, "get_meta")
    assert exc.value.reason == "PRINCIPAL_MISSING"


class FakeScope(Enum):
    READ = "read"


class StrScope(str):
    pass


@pytest.mark.parametrize(
    "bad_scopes",
    [
        frozenset(),
        frozenset({"read"}),
        frozenset({FakeScope.READ}),
        frozenset({StrScope("read")}),
        {Scope.READ},
        [Scope.READ],
        (Scope.READ,),
        None,
    ],
)
def test_principal_rejects_forged_or_malformed_scopes(bad_scopes: object) -> None:
    with pytest.raises(PrincipalInvalid):
        Principal(principal_id="p1", scopes=bad_scopes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad_id", ["", "A", "x" * 33, "p 1", "p\n1", "p1\u200b", "\uff501", None, 1, b"p1", "-p", "p:1"]
)
def test_principal_rejects_malformed_ids(bad_id: object) -> None:
    with pytest.raises(PrincipalInvalid):
        Principal(principal_id=bad_id, scopes=frozenset({Scope.READ}))  # type: ignore[arg-type]


def test_principal_accepts_boundary_ids() -> None:
    for good in ("p", "a" * 32, "local-stdio", "a_b-9"):
        assert Principal(principal_id=good, scopes=frozenset({Scope.READ})).principal_id == good


def test_principal_tampered_after_construction_fails_closed() -> None:
    p = Principal(principal_id="p1", scopes=frozenset({Scope.READ}))
    object.__setattr__(p, "scopes", frozenset({"write"}))
    with pytest.raises(AuthorizationDenied) as exc:
        authorize(p, "get_meta")
    assert exc.value.reason == "PRINCIPAL_INVALID"
    q = Principal(principal_id="p1", scopes=frozenset({Scope.READ}))
    object.__setattr__(q, "principal_id", "bad id")
    with pytest.raises(AuthorizationDenied) as exc:
        authorize(q, "get_meta")
    assert exc.value.reason == "PRINCIPAL_INVALID"


def test_non_principal_object_fails_closed() -> None:
    class Lookalike:
        principal_id = "p1"
        scopes = frozenset(Scope)

    with pytest.raises(AuthorizationDenied) as exc:
        authorize(Lookalike(), "get_meta")  # type: ignore[arg-type]
    assert exc.value.reason == "PRINCIPAL_INVALID"


def test_parse_principal_strict() -> None:
    p = parse_principal({"id": "agent-1", "scopes": ["read", "write"]})
    assert p == Principal(principal_id="agent-1", scopes=frozenset({Scope.READ, Scope.WRITE}))


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "read",
        [],
        {},
        {"id": "a"},
        {"scopes": ["read"]},
        {"id": "a", "scopes": []},
        {"id": "a", "scopes": "read"},
        {"id": "a", "scopes": ["READ"]},
        {"id": "a", "scopes": ["read "]},
        {"id": "a", "scopes": ["superuser"]},
        {"id": "a", "scopes": ["read", "read"]},
        {"id": "a", "scopes": [1]},
        {"id": "a", "scopes": ["read"], "token": "s3cr3t"},
        {"id": "a", "scopes": ["read"], "password": "x"},
        {"id": 5, "scopes": ["read"]},
    ],
)
def test_parse_principal_rejects_malformed(raw: object) -> None:
    with pytest.raises(PrincipalInvalid):
        parse_principal(raw)


def test_principal_error_messages_never_echo_input() -> None:
    with pytest.raises(PrincipalInvalid) as exc:
        parse_principal({"id": "a", "scopes": ["read"], "token": "s3cr3t-value"})
    assert "s3cr3t" not in str(exc.value) and "s3cr3t" not in repr(exc.value)


def test_principal_has_no_credential_fields() -> None:
    assert set(Principal.__dataclass_fields__) == {"principal_id", "scopes"}


def test_forbidden_error_code_is_not_retryable() -> None:
    from pickfair_mcp.errors import MESSAGES, RETRYABLE_FOR_READS

    assert ErrorCode.FORBIDDEN.value == "FORBIDDEN"
    assert ErrorCode.FORBIDDEN in MESSAGES
    assert ErrorCode.FORBIDDEN not in RETRYABLE_FOR_READS


def test_local_stdio_principal_is_read_only() -> None:
    from pickfair_mcp.cli import LOCAL_STDIO_PRINCIPAL

    assert LOCAL_STDIO_PRINCIPAL.scopes == frozenset({Scope.READ})


def test_exception_texts_are_the_fixed_reasons() -> None:
    with pytest.raises(PrincipalInvalid) as exc:
        parse_principal(None)
    assert str(exc.value) == exc.value.reason == "PRINCIPAL_INVALID"
    with pytest.raises(AuthorizationDenied) as denied:
        authorize(None, "get_meta")
    assert str(denied.value) == "PRINCIPAL_MISSING"
