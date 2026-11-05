"""MCP-01l: route con parametro `/v1/markets/{id}/book` e `/v1/markets` sul server Control API reale."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.control_api import bodies
from tests.control_api.servers import control_api
from tests.control_api.test_server import request

pytestmark = pytest.mark.loopback


@pytest.fixture
def api(tmp_path: Path) -> Any:
    with control_api(tmp_path) as ctx:
        yield ctx


def test_markets_route_serves_the_provider(api: Any) -> None:
    server, _s, token_path, providers = api
    status, _h, body = request(server.port, "GET", "/v1/markets", token=token_path.read_text())
    assert status == 200 and body["markets"][0]["market_id"] == "1.200000001"


@pytest.mark.parametrize("market_id", ["1.200000001", "1.1", "9999.123456789012345"])
def test_book_route_passes_the_validated_id(api: Any, market_id: str) -> None:
    server, _s, token_path, providers = api
    providers.market_book = lambda mid: bodies.market_book(mid)
    status, _h, body = request(server.port, "GET", f"/v1/markets/{market_id}/book",
                               token=token_path.read_text())
    assert status == 200 and body["market_id"] == market_id
    assert providers.book_requests == [market_id]


@pytest.mark.parametrize(
    "path",
    [
        "/v1/markets/../book",
        "/v1/markets/./book",
        "/v1/markets/%2e%2e/book",
        "/v1/markets/1.2/../book",
        "/v1/markets/1.2a/book",
        "/v1/markets/a.1/book",
        "/v1/markets/1/book",
        "/v1/markets/12345.1/book",
        "/v1/markets/1.1234567890123456/book",
        "/v1/markets/1.2/book?x=1",
        "/v1/markets/1.2/book/",
        "/v1/markets//book",
        "/v1/markets/1.2",
        "/v1/markets/",
    ],
)
def test_book_route_rejects_any_other_shape_without_calling_the_core(api: Any, path: str) -> None:
    server, _s, token_path, providers = api
    status, _h, body = request(server.port, "GET", path, token=token_path.read_text())
    assert status in (400, 404) and body["error"]["code"] in ("NOT_FOUND", "BAD_REQUEST")
    assert providers.calls == 0 and providers.book_requests == []


def test_book_route_needs_the_token_and_only_get(api: Any) -> None:
    server, _s, token_path, providers = api
    assert request(server.port, "GET", "/v1/markets/1.2/book", token=None)[0] == 401
    assert request(server.port, "GET", "/v1/markets/1.2/book", token="x" * 43)[0] == 401
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert request(server.port, method, "/v1/markets/1.2/book", token=token_path.read_text())[0] == 405
    assert providers.calls == 0


def test_book_response_out_of_contract_never_leaves(api: Any) -> None:
    server, _s, token_path, providers = api
    providers.market_book = lambda mid: bodies.market_book(mid, event_name="Juventus v Inter")
    status, _h, body = request(server.port, "GET", "/v1/markets/1.2/book", token=token_path.read_text())
    assert (status, body) == (500, {"error": {"code": "CONTRACT_SELF_CHECK"}})


def test_book_provider_failure_is_a_fixed_error(api: Any) -> None:
    server, _s, token_path, providers = api

    def boom(_mid: str) -> dict[str, Any]:
        raise RuntimeError("secret detail /home/x")

    providers.market_book = boom
    status, _h, body = request(server.port, "GET", "/v1/markets/1.2/book", token=token_path.read_text())
    assert (status, body) == (500, {"error": {"code": "INTERNAL"}})


def test_meta_lists_the_market_capabilities(api: Any) -> None:
    server, _s, token_path, _p = api
    _st, _h, body = request(server.port, "GET", "/v1/meta", token=token_path.read_text())
    assert {"GET /v1/markets", "GET /v1/markets/{id}/book"} <= set(body["capabilities"])
