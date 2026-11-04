"""Validazione delle risposte della Control API contro gli schemi del contratto (fail-closed).

Sottoinsieme di JSON Schema usato dal descrittore canonico. Regole:
- una parola chiave non gestita è un ERRORE (`SchemaUnsupported`), mai un vincolo ignorato;
- `pattern` con `$` finale non accetta un a capo finale (in Python `$` lo ammetterebbe);
- `True`/`False` non sono numeri; i numeri non finiti non sono ammessi;
- controllo semantico aggiuntivo: in un oggetto con `unavailable`, un campo è null se e solo
  se è elencato (invariante che JSON Schema non sa esprimere).
"""

from __future__ import annotations

import math
import re
from functools import lru_cache
from typing import Any, Final

HANDLED: Final = frozenset(
    {
        "$defs",
        "$ref",
        "additionalProperties",
        "anyOf",
        "const",
        "enum",
        "exclusiveMaximum",
        "exclusiveMinimum",
        "items",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minimum",
        "pattern",
        "properties",
        "required",
        "title",
        "type",
        "uniqueItems",
        "description",
    }
)
ENVELOPE_FIELDS: Final = frozenset({"source", "observed_at", "consistency", "unavailable"})


class SchemaUnsupported(Exception):
    """Lo schema usa una parola chiave che questo validatore non sa applicare."""


class SchemaViolation(Exception):
    """L'istanza non rispetta lo schema. Il messaggio contiene solo il percorso JSON."""


@lru_cache(maxsize=256)
def _compiled(pattern: str) -> re.Pattern[str]:
    if pattern.endswith("$") and not pattern.endswith("\\$"):
        pattern = pattern[:-1] + r"\Z"
    return re.compile(pattern)


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return type(value) is bool
    if expected == "integer":
        return type(value) is int
    if expected == "number":
        return (type(value) is int) or (type(value) is float and math.isfinite(value))
    if expected == "string":
        return type(value) is str
    if expected == "array":
        return type(value) is list
    if expected == "object":
        return type(value) is dict
    raise SchemaUnsupported(f"type:{expected}")


def validate(instance: Any, schema: dict[str, Any], root: dict[str, Any] | None = None) -> None:
    _check(instance, schema, root if root is not None else schema, "$")


def _check(value: Any, schema: dict[str, Any], root: dict[str, Any], path: str) -> None:
    unknown = set(schema) - HANDLED
    if unknown:
        raise SchemaUnsupported(",".join(sorted(unknown)))
    if "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            raise SchemaUnsupported(f"$ref:{ref}")
        target = root.get("$defs", {}).get(ref[len("#/$defs/") :])
        if not isinstance(target, dict):
            raise SchemaUnsupported(f"$ref:{ref}")
        _check(value, target, root, path)
    if "anyOf" in schema:
        for option in schema["anyOf"]:
            try:
                _check(value, option, root, path)
                break
            except SchemaViolation:
                continue
        else:
            raise SchemaViolation(path)
    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_type_ok(value, t) for t in types):
            raise SchemaViolation(path)
    if type(value) is float and not math.isfinite(value):
        raise SchemaViolation(path)
    if "const" in schema and not _same(value, schema["const"]):
        raise SchemaViolation(path)
    if "enum" in schema and not any(_same(value, e) for e in schema["enum"]):
        raise SchemaViolation(path)
    if type(value) is str:
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            raise SchemaViolation(path)
        if "pattern" in schema and not _compiled(schema["pattern"]).search(value):
            raise SchemaViolation(path)
    if type(value) in (int, float):
        if "minimum" in schema and value < schema["minimum"]:
            raise SchemaViolation(path)
        if "maximum" in schema and value > schema["maximum"]:
            raise SchemaViolation(path)
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise SchemaViolation(path)
        if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
            raise SchemaViolation(path)
    if type(value) is list:
        if "minItems" in schema and len(value) < schema["minItems"]:
            raise SchemaViolation(path)
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise SchemaViolation(path)
        if schema.get("uniqueItems") and len({_key(v) for v in value}) != len(value):
            raise SchemaViolation(path)
        if "items" in schema:
            for i, item in enumerate(value):
                _check(item, schema["items"], root, f"{path}[{i}]")
    if type(value) is dict:
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                raise SchemaViolation(f"{path}.{name}")
        if schema.get("additionalProperties") is False and set(value) - set(props):
            raise SchemaViolation(path)
        for name, sub in props.items():
            if name in value:
                _check(value[name], sub, root, f"{path}.{name}")
        if "unavailable" in props and "unavailable" in value:
            _check_unavailable(value, props, path)


def _check_unavailable(value: dict[str, Any], props: dict[str, Any], path: str) -> None:
    declared = value["unavailable"]
    optional = set(props) - ENVELOPE_FIELDS
    if type(declared) is not list or len(set(declared)) != len(declared):
        raise SchemaViolation(f"{path}.unavailable")
    for name in optional:
        if (value.get(name) is None) != (name in declared):
            raise SchemaViolation(f"{path}.{name}")


def _same(a: Any, b: Any) -> bool:
    return type(a) is type(b) and a == b


def _key(value: Any) -> str:
    return repr(value)
