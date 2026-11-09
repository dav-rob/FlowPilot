"""Runtime-enforced schemas and workflow permissions around ordinary business tools."""

from __future__ import annotations
import inspect
import types
import typing
from jsonschema import Draft202012Validator
from flowpilot_data.schema import TOOL_DOMAIN, GENERIC_TOOLS, SENSITIVE_TOOLS
from flowpilot_data.tools import EnterpriseSession


def type_schema(t):
    origin = typing.get_origin(t)
    if origin in (typing.Union, types.UnionType):
        return {"anyOf": [type_schema(a) for a in typing.get_args(t)]}
    if t is type(None):
        return {"type": "null"}
    if t in (list, typing.List) or origin is list:
        return {"type": "array", "items": {}}
    if t in (dict, typing.Dict) or origin is dict:
        return {"type": "object"}
    return {
        "type": {str: "string", bool: "boolean", int: "integer", float: "number"}.get(
            t, "string"
        )
    }


def catalogue(session):
    meta = {c["name"]: c for c in session.catalogue()}
    rows = []
    for name, fn in session._tools.items():
        if name == "list_tools":
            continue
        hints = typing.get_type_hints(fn)
        properties = {}
        required = []
        for key, p in inspect.signature(fn).parameters.items():
            if key == "approval_token":
                continue
            properties[key] = type_schema(hints.get(key, str))
            if p.default is inspect.Parameter.empty:
                required.append(key)
        schema = {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        }
        for key in ("dataset_ids", "related_records", "record_types"):
            if key in properties:
                spec = {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1},
                    "maxItems": 100,
                }
                if key == "dataset_ids":
                    spec.update(minItems=1, uniqueItems=True)
                properties[key] = (
                    spec
                    if key == "dataset_ids"
                    else {"anyOf": [spec, {"type": "null"}]}
                )
        if "limit" in properties:
            properties["limit"] = {"type": "integer", "minimum": 1, "maximum": 25}
        rows.append(
            {
                "name": name,
                "description": meta[name]["description"],
                "domain": TOOL_DOMAIN.get(name, "shared"),
                "parameters": schema,
                "permission": (
                    "approval_required"
                    if name in SENSITIVE_TOOLS
                    else (
                        "simulated_write"
                        if meta[name]["side_effects"] != "none"
                        else "read_only"
                    )
                ),
                "system": meta[name]["system"],
                "returns": "Structured {ok, tool, data | error} envelope",
            }
        )
    return sorted(rows, key=lambda t: t["name"])


class Registry:
    def __init__(self, session, categories):
        self.session = session
        self.categories = set(categories)
        self.tools = {
            t["name"]: t
            for t in catalogue(session)
            if t["domain"] in self.categories or t["domain"] == "shared"
        }

    def describe(self):
        return list(self.tools.values())

    def validate(self, name, args):
        if name not in self.tools:
            return {
                "code": "PERMISSION_DENIED",
                "message": f"{name} is not available to these workflows",
            }
        if not isinstance(args, dict):
            return {
                "code": "INVALID_ARGUMENT",
                "message": "Arguments must be an object",
            }
        errors = list(
            Draft202012Validator(self.tools[name]["parameters"]).iter_errors(args)
        )
        if errors:
            return {"code": "INVALID_ARGUMENT", "message": errors[0].message[:300]}
        if name == "request_approval":
            action = args.get("action")
            if action not in SENSITIVE_TOOLS or action not in self.tools:
                return {
                    "code": "PERMISSION_DENIED",
                    "message": "Approval target must be a permitted consequential action",
                }
            return self.validate(action, args.get("arguments", {}))
        return None
