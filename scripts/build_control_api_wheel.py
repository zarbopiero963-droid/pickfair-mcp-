"""Distribuzione immutabile e riproducibile di `pickfair_control_api` (opzioni A e B).

A — wheel deterministica: stessi sorgenti => stessi byte => stesso SHA-256. Nessuna dipendenza
    dichiarata (solo libreria standard): l'installazione con
    `pip install --no-deps --no-index --require-hashes -r requirements-control-api.txt`
    non risolve nulla e non usa la rete.
B — manifest per la copia vendorizzata: impronta SHA-256 di ogni file e impronta complessiva
    dell'albero, da verificare con un test nel repository che ospita la copia.

Uso:
    python scripts/build_control_api_wheel.py --out DIR      # wheel + requirements + manifest
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "pickfair_control_api"
DIST_NAME = "pickfair_control_api"
PROJECT_NAME = "pickfair-control-api"
FIXED_DATE = (1980, 1, 1, 0, 0, 0)  # i timestamp non entrano nei byte della wheel
INCLUDED_SUFFIXES = (".py", ".json")


def package_version() -> str:
    for line in (PACKAGE / "__init__.py").read_text(encoding="utf-8").splitlines():
        if line.startswith("__version__ = "):
            return line.split('"')[1]
    raise SystemExit("__version__ mancante in pickfair_control_api")


def package_files() -> list[Path]:
    files = sorted(
        p
        for p in PACKAGE.rglob("*")
        if p.is_file() and p.suffix in INCLUDED_SUFFIXES and "__pycache__" not in p.parts
    )
    if not files:
        raise SystemExit("nessun file nel package")
    return files


def _digest(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def manifest() -> dict[str, object]:
    entries = {
        p.relative_to(PACKAGE.parent).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in package_files()
    }
    tree = hashlib.sha256(
        "".join(f"{name}\0{digest}\n" for name, digest in sorted(entries.items())).encode()
    ).hexdigest()
    return {
        "package": DIST_NAME,
        "version": package_version(),
        "files": entries,
        "tree_sha256": tree,
    }


def build_wheel(out_dir: Path) -> Path:
    version = package_version()
    dist_info = f"{DIST_NAME}-{version}.dist-info"
    payload: list[tuple[str, bytes]] = [
        (p.relative_to(PACKAGE.parent).as_posix(), p.read_bytes()) for p in package_files()
    ]
    metadata = (
        "Metadata-Version: 2.1\n"
        f"Name: {PROJECT_NAME}\n"
        f"Version: {version}\n"
        "Summary: Control API v1 di Pickfair, sola lettura, solo libreria standard\n"
        "Requires-Python: >=3.11\n"
    ).encode()
    wheel_meta = (
        b"Wheel-Version: 1.0\n"
        b"Generator: pickfair-mcp scripts/build_control_api_wheel.py\n"
        b"Root-Is-Purelib: true\n"
        b"Tag: py3-none-any\n"
    )
    payload += [(f"{dist_info}/METADATA", metadata), (f"{dist_info}/WHEEL", wheel_meta)]
    record = "".join(f"{name},{_digest(data)},{len(data)}\n" for name, data in payload)
    record += f"{dist_info}/RECORD,,\n"
    payload.append((f"{dist_info}/RECORD", record.encode()))
    out_dir.mkdir(parents=True, exist_ok=True)
    wheel = out_dir / f"{DIST_NAME}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        for name, data in payload:
            info = zipfile.ZipInfo(name, date_time=FIXED_DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            info.create_system = 3
            zf.writestr(info, data, compresslevel=9)
    return wheel


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    wheel = build_wheel(args.out)
    sha = hashlib.sha256(wheel.read_bytes()).hexdigest()
    (args.out / "requirements-control-api.txt").write_text(
        f"{PROJECT_NAME}=={package_version()} --hash=sha256:{sha}\n", encoding="ascii"
    )
    (args.out / "control_api_manifest.json").write_text(
        json.dumps(manifest(), indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    print(
        json.dumps({"wheel": wheel.name, "sha256": sha, "tree_sha256": manifest()["tree_sha256"]})
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
