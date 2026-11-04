"""No-bypass: il pacchetto non può raggiungere Betfair, il DB Pickfair o il motore.

I pattern testuali replicano `MCP_FORBIDDEN_RE` e `MONEY_PATH_CALL_RE` di
Pickfair-nogui `scripts/pr_autonomy_policy.py` (`full-diff --repo-kind mcp`):
si applicano ai file .py fuori da tests/, righe di commento escluse.
In più, l'analisi AST vieta import di rete, processi e motore Pickfair.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import REPO_ROOT, SRC_ROOT

pytestmark = pytest.mark.guard

MCP_FORBIDDEN_RE = re.compile(
    r"(?i)(betfair\.com|identitysso|api\.betfair|certlogin|app_?key|"
    r"sqlite3|\bpickfair\.db\b|betfair_client|betfairlightweight)"
)
MONEY_PATH_CALL_RE = re.compile(
    r"\b(?:place_bet|place_orders|placeOrders|cancel_orders|cancelOrders|"
    r"replace_orders|replaceOrders|update_orders|updateOrders|execute_cashout)\s*\("
    r"|[\"']CMD_QUICK_BET[\"']"
)
EXTRA_FORBIDDEN_RE = re.compile(
    r"\b(?:TradingEngine|OrderManager|BetfairClient|SimulationBroker|RuntimeController|"
    r"telethon|Telethon|stream-api)\b"
)

FORBIDDEN_IMPORT_ROOTS = {
    # rete: l'adapter HTTP è BLOCKED_CORE in MCP-01a
    "socket",
    "ssl",
    "http",
    "urllib3",
    "httpx",
    "requests",
    "aiohttp",
    "websockets",
    "ftplib",
    "smtplib",
    "telnetlib",
    # processi ed esecuzione arbitraria
    "subprocess",
    "multiprocessing",
    "pty",
    "pickle",
    "marshal",
    "ctypes",
    # DB e motore Pickfair
    "sqlite3",
    "dbm",
    "shelve",
    "importlib",
    "betfairlightweight",
    "telethon",
    "betfair_client",
    "betfair_market_api",
    "core",
    "services",
    "order_manager",
    "simulation_broker",
    "database",
    "trading_config",
    "money_management",
}
# urllib.parse è solo parsing di stringhe; i moduli di rete di urllib restano vietati.
FORBIDDEN_IMPORT_EXACT = {"urllib.request", "urllib.error", "urllib.robotparser"}
# Il client MCP dell'SDK (http/sse/websocket) non serve al server: vietato.
FORBIDDEN_IMPORT_PREFIXES = ("mcp.client",)
# Attributi di rete o di output diretto, rilevati anche se chiamati via modulo.
FORBIDDEN_ATTRIBUTES = {
    "connect_tcp",
    "connect_unix",
    "open_connection",
    "create_connection",
    "getaddrinfo",
    "urlopen",
    "stdout",
    "__stdout__",
    "system",
    "popen",
    "create_udp_socket",
    "create_tcp_listener",
    "create_unix_listener",
    "create_datagram_endpoint",
    "sock_connect",
    "posix_spawn",
    "posix_spawnp",
    "execv",
    "execve",
    "execvp",
    "execl",
}
FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__", "breakpoint", "getattr"}

# MCP-01d: UNICA eccezione alle importazioni di rete. Solo questo file, solo questi moduli.
# Ogni altra regola (attributi vietati come create_connection/getaddrinfo, testo vietato,
# chiamate dinamiche) resta valida anche per questo file.
NETWORK_EXCEPTION_FILE = SRC_ROOT / "adapters" / "http.py"
NETWORK_EXCEPTION_IMPORTS = frozenset({"http.client", "socket"})
PRINT_ALLOWED = {SRC_ROOT / "cli.py"}


def production_py_files() -> list[Path]:
    files = sorted(SRC_ROOT.rglob("*.py"))
    files += sorted((REPO_ROOT / "scripts").rglob("*.py"))
    assert files, "nessun file sorgente trovato"
    return files


def code_lines(path: Path) -> list[tuple[int, str]]:
    out = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.lstrip().startswith("#"):
            continue
        out.append((number, line))
    return out


@pytest.mark.parametrize("regex", [MCP_FORBIDDEN_RE, MONEY_PATH_CALL_RE, EXTRA_FORBIDDEN_RE])
def test_no_forbidden_text_in_production_code(regex: re.Pattern[str]) -> None:
    hits = [
        f"{p.relative_to(REPO_ROOT)}:{n}"
        for p in production_py_files()
        for n, line in code_lines(p)
        if regex.search(line)
    ]
    assert hits == []


def _imports(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found += [(node.lineno, alias.name) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.append((node.lineno, node.module))
                found += [(node.lineno, f"{node.module}.{a.name}") for a in node.names]
    return found


def _forbidden_import(name: str) -> bool:
    return (
        name.split(".")[0] in FORBIDDEN_IMPORT_ROOTS
        or name in FORBIDDEN_IMPORT_EXACT
        or name.startswith(FORBIDDEN_IMPORT_PREFIXES)
        or name.rsplit(".", 1)[-1] in FORBIDDEN_ATTRIBUTES  # from x import connect_tcp
    )


def test_no_forbidden_imports_in_package() -> None:
    hits = [
        f"{p.relative_to(REPO_ROOT)}:{line}:{name}"
        for p in sorted(SRC_ROOT.rglob("*.py"))
        for line, name in _imports(p)
        if _forbidden_import(name)
        and not (p == NETWORK_EXCEPTION_FILE and name in NETWORK_EXCEPTION_IMPORTS)
    ]
    assert hits == []


def test_network_exception_is_exactly_one_file_and_two_modules() -> None:
    """L'eccezione non si allarga: esiste, usa SOLO i moduli ammessi, nessun altro li usa."""
    assert NETWORK_EXCEPTION_FILE.is_file()
    used = {name for _, name in _imports(NETWORK_EXCEPTION_FILE) if _forbidden_import(name)}
    assert used == NETWORK_EXCEPTION_IMPORTS
    others = [
        f"{p.relative_to(REPO_ROOT)}:{name}"
        for p in sorted(SRC_ROOT.rglob("*.py"))
        if p != NETWORK_EXCEPTION_FILE
        for _, name in _imports(p)
        if name.split(".")[0] in {"http", "socket", "ssl"}
    ]
    assert others == []


def test_network_exception_file_never_resolves_names() -> None:
    """Nemmeno l'adapter può risolvere nomi o usare scorciatoie di connessione."""
    tree = ast.parse(NETWORK_EXCEPTION_FILE.read_text(encoding="utf-8"))
    attrs = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    assert not attrs & {
        "getaddrinfo",
        "gethostbyname",
        "create_connection",
        "set_tunnel",
        "HTTPSConnection",
        "urlopen",
    }
    text = NETWORK_EXCEPTION_FILE.read_text(encoding="utf-8")
    assert "environ" not in text and "getenv" not in text  # nessuna configurazione ambientale


def test_no_dynamic_execution_or_stray_prints() -> None:
    hits = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRIBUTES:
                hits.append(f"{path.name}:{node.lineno}:.{node.attr}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in FORBIDDEN_CALLS:
                    hits.append(f"{path.name}:{node.lineno}:{node.func.id}")
                if node.func.id == "print" and path not in PRINT_ALLOWED:
                    # stdout è il canale JSON-RPC: un print lo corromperebbe
                    hits.append(f"{path.name}:{node.lineno}:print")
    assert hits == []


def test_runtime_import_does_not_load_engine_or_db_modules() -> None:
    probe = (
        "import sys, pkgutil, importlib, pickfair_mcp\n"
        "for m in pkgutil.walk_packages(pickfair_mcp.__path__, 'pickfair_mcp.'):\n"
        "    if m.name != 'pickfair_mcp.__main__':\n"
        "        importlib.import_module(m.name)\n"
        "bad = {'sqlite3', 'betfair' + 'lightweight', 'telethon', 'requests', 'core',\n"
        "       'services', 'order_manager', 'simulation_broker', 'database'}\n"
        "print(sorted(m for m in sys.modules if m.split('.')[0] in bad))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PYTHONPATH": str(REPO_ROOT / "src")},
        check=True,
    )
    assert proc.stdout.strip() == "[]"


def test_guard_detects_a_planted_violation(tmp_path: Path) -> None:
    """Il guard non è a vuoto: una violazione piantata viene rilevata."""
    planted = tmp_path / "planted.py"
    planted.write_text(
        "import betfairlightweight\nfrom urllib import request\nx = client.place_orders(1)\n"
        "import importlib\nfrom mcp.client.stdio import stdio_client\n"
        "from anyio import connect_tcp\nfrom os import system\n"
    )
    assert any(MCP_FORBIDDEN_RE.search(line) for _, line in code_lines(planted))
    assert any(MONEY_PATH_CALL_RE.search(line) for _, line in code_lines(planted))
    names = [n for _, n in _imports(planted)]
    assert any(n.split(".")[0] in FORBIDDEN_IMPORT_ROOTS for n in names)
    assert "urllib.request" in names
    assert any(n.split(".")[0] == "importlib" for n in names)
    assert any(n.startswith(FORBIDDEN_IMPORT_PREFIXES) for n in names)
    assert "anyio.connect_tcp" in names
    assert any(n.rsplit(".", 1)[-1] in FORBIDDEN_ATTRIBUTES for n in names)
