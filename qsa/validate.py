"""Schema-lite validation for evidence cards.

A deliberately small JSON-schema subset (type / enum / required / properties /
minimum / maximum / pattern / minItems / array items), kept tiny so the gate
has no dependency surface and its behaviour is fully auditable by reading one
file. Unregistered card types fail — no schema, no ledger entry.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REGISTRY = Path(__file__).resolve().parent / "registry" / "schemas"

TYPES: dict[str, type] = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": list,
    "object": dict,
}


def load_schema(name: str) -> dict[str, Any]:
    path = REGISTRY / f"{name}.json"
    if not path.exists():
        raise KeyError(name)
    return json.loads(path.read_text(encoding="utf-8"))


def check_field(value: Any, spec: dict[str, Any], path: str) -> list[str]:
    errs: list[str] = []
    t = spec.get("type")
    if t and t in TYPES:
        if t in ("integer", "number") and isinstance(value, bool):
            errs.append(f"{path}: bool is not a {t}")
        elif not isinstance(value, TYPES[t]):
            errs.append(f"{path}: expected {t}, got {type(value).__name__}")
            return errs
    if "enum" in spec and value not in spec["enum"]:
        errs.append(f"{path}: {value!r} not in enum {spec['enum']}")
    if "minimum" in spec and isinstance(value, (int, float)) \
            and not isinstance(value, bool) and value < spec["minimum"]:
        errs.append(f"{path}: {value} < minimum {spec['minimum']}")
    if "maximum" in spec and isinstance(value, (int, float)) \
            and not isinstance(value, bool) and value > spec["maximum"]:
        errs.append(f"{path}: {value} > maximum {spec['maximum']}")
    if "pattern" in spec and isinstance(value, str) \
            and not re.search(spec["pattern"], value):
        errs.append(f"{path}: {value!r} does not match pattern {spec['pattern']}")
    if spec.get("type") == "array" and "minItems" in spec and len(value) < spec["minItems"]:
        errs.append(f"{path}: fewer than minItems {spec['minItems']}")
    return errs


def validate_doc(doc: Any, schema: dict[str, Any], prefix: str) -> list[str]:
    """Validate *doc* against *schema*; errors are prefixed with *prefix*."""
    errs: list[str] = []
    if not isinstance(doc, dict):
        return [f"{prefix}: top level must be an object"]
    for req in schema.get("required", []):
        if req not in doc:
            errs.append(f"{prefix}: missing required field '{req}'")
    props = schema.get("properties", {})
    for key, spec in props.items():
        if key in doc:
            errs.extend(check_field(doc[key], spec, f"{prefix}:{key}"))
            if spec.get("type") == "object" and isinstance(doc[key], dict) \
                    and "required" in spec:
                for req in spec["required"]:
                    if req not in doc[key]:
                        errs.append(f"{prefix}:{key}: missing required field '{req}'")
                for sub_key, sub_spec in spec.get("properties", {}).items():
                    if sub_key in doc[key]:
                        errs.extend(check_field(doc[key][sub_key], sub_spec,
                                                f"{prefix}:{key}.{sub_key}"))
            if spec.get("type") == "array" and "items" in spec \
                    and isinstance(doc[key], list):
                for i, item in enumerate(doc[key]):
                    errs.extend(check_field(item, spec["items"], f"{prefix}:{key}[{i}]"))
    return errs


def validate_card(doc: Any, prefix: str) -> list[str]:
    """Route on the card's declared 'schema' field; unregistered types fail."""
    if not isinstance(doc, dict):
        return [f"{prefix}: top level must be an object"]
    stype = doc.get("schema")
    if not stype:
        return [f"{prefix}: missing 'schema' field (card type not declared)"]
    try:
        schema = load_schema(stype)
    except KeyError:
        return [f"{prefix}: schema '{stype}' is not registered "
                f"(no schema, no ledger entry)"]
    return validate_doc(doc, schema, prefix)
