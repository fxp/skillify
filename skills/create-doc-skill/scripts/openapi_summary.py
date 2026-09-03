#!/usr/bin/env python3
"""Expand an OpenAPI 3.x / Swagger 2.0 spec into readable per-tag Markdown summaries.

Usage:
    python3 openapi_summary.py <spec.json|spec.yaml|URL> [--out-dir DIR] [--tag TAG] [--grep SUBSTR]

Writes <out-dir>/index.md plus one <tag>.md per tag (endpoints without tags are grouped
by the first path segment). Every $ref is resolved recursively (with cycle protection) so
each endpoint shows flattened request/response fields with type, required flag, enum and
description. Stdlib only; YAML specs need `pip install pyyaml`.
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path


def load_spec(src: str) -> dict:
    if re.match(r"^https?://", src):
        with urllib.request.urlopen(src, timeout=60) as r:
            text = r.read().decode("utf-8", "replace")
    else:
        text = Path(src).read_text(encoding="utf-8", errors="replace")
    text = text.lstrip("﻿")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # type: ignore
        except ImportError:
            sys.exit("spec is not JSON; install pyyaml to read YAML specs")
        return yaml.safe_load(text)


class Resolver:
    def __init__(self, spec: dict):
        self.spec = spec

    def deref(self, node, seen=None):
        """Resolve local $ref recursively. Returns a new structure (no mutation)."""
        seen = seen or ()
        if isinstance(node, dict):
            if "$ref" in node and isinstance(node["$ref"], str):
                ref = node["$ref"]
                if ref in seen:
                    return {"type": "object", "description": f"(recursive → {ref.split('/')[-1]})"}
                target = self.lookup(ref)
                merged = dict(target) if isinstance(target, dict) else target
                if isinstance(merged, dict):
                    for k, v in node.items():
                        if k != "$ref":
                            merged[k] = v
                return self.deref(merged, seen + (ref,))
            return {k: self.deref(v, seen) for k, v in node.items()}
        if isinstance(node, list):
            return [self.deref(v, seen) for v in node]
        return node

    def lookup(self, ref: str):
        if not ref.startswith("#/"):
            return {"type": "object", "description": f"(external ref {ref})"}
        node = self.spec
        for part in ref[2:].split("/"):
            part = part.replace("~1", "/").replace("~0", "~")
            if isinstance(node, dict) and part in node:
                node = node[part]
            else:
                return {"type": "object", "description": f"(unresolved ref {ref})"}
        return node


def type_of(schema: dict) -> str:
    if not isinstance(schema, dict):
        return str(schema)
    for comb in ("oneOf", "anyOf", "allOf"):
        if comb in schema:
            return comb + "[" + " | ".join(type_of(s) for s in schema[comb]) + "]"
    t = schema.get("type")
    if isinstance(t, list):
        t = "|".join(t)
    if t == "array":
        return f"array<{type_of(schema.get('items', {}))}>"
    if t is None and "properties" in schema:
        t = "object"
    if schema.get("format"):
        return f"{t}({schema['format']})"
    return t or "any"


def one_line(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def flatten(schema, prefix="", depth=0, out=None, max_depth=6):
    """Yield (path, type, required, enum, description) rows for a schema."""
    out = out if out is not None else []
    if not isinstance(schema, dict) or depth > max_depth:
        return out
    if "allOf" in schema:
        merged = {"type": "object", "properties": {}, "required": []}
        for part in schema["allOf"]:
            if isinstance(part, dict):
                merged["properties"].update(part.get("properties", {}))
                merged["required"] += part.get("required", [])
        schema = merged
    for comb in ("oneOf", "anyOf"):
        if comb in schema:
            for i, part in enumerate(schema[comb]):
                out.append((f"{prefix}({comb} #{i+1}: {type_of(part)})", "", "", "", one_line(part.get('description', '') if isinstance(part, dict) else '')))
                flatten(part, prefix, depth + 1, out, max_depth)
            return out
    req = set(schema.get("required", []) or [])
    props = schema.get("properties", {}) or {}
    for name, sub in props.items():
        if not isinstance(sub, dict):
            continue
        enum = sub.get("enum")
        enum_s = ", ".join(map(str, enum)) if enum else ""
        default = sub.get("default")
        desc = one_line(sub.get("description", ""))
        if default is not None:
            desc = f"default={default!r}. {desc}"
        out.append((prefix + name, type_of(sub), "yes" if name in req else "", enum_s, desc))
        if sub.get("type") == "array" and isinstance(sub.get("items"), dict):
            flatten(sub["items"], prefix + name + "[]." , depth + 1, out, max_depth)
        elif "properties" in sub or "allOf" in sub or "oneOf" in sub or "anyOf" in sub:
            flatten(sub, prefix + name + ".", depth + 1, out, max_depth)
    if schema.get("type") == "array" and isinstance(schema.get("items"), dict) and not props:
        flatten(schema["items"], prefix + "[].", depth + 1, out, max_depth)
    if "additionalProperties" in schema and isinstance(schema["additionalProperties"], dict) and not props:
        out.append((prefix + "{key}", type_of(schema["additionalProperties"]), "", "", one_line(schema["additionalProperties"].get("description", ""))))
    return out


def md_table(rows, headers):
    if not rows:
        return "_(none)_\n"
    esc = lambda s: str(s).replace("|", "\\|")
    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        lines.append("| " + " | ".join(esc(c) for c in r) + " |")
    return "\n".join(lines) + "\n"


def security_text(spec: dict, op: dict) -> str:
    schemes = (spec.get("components", {}) or {}).get("securitySchemes") or spec.get("securityDefinitions") or {}
    sec = op.get("security", spec.get("security", [])) or []
    names = [k for s in sec for k in (s or {}).keys()]
    if not names:
        return "none declared"
    parts = []
    for n in names:
        s = schemes.get(n, {})
        if s.get("type") == "http":
            parts.append(f"{n}: HTTP {s.get('scheme')} (Authorization: {str(s.get('scheme','')).title()} ...)")
        elif s.get("type") == "apiKey":
            parts.append(f"{n}: apiKey in {s.get('in')} '{s.get('name')}'")
        else:
            parts.append(f"{n}: {s.get('type', '?')}")
    return "; ".join(parts)


def render_operation(spec, res, path, method, op, base_url):
    lines = [f"### {method.upper()} {path}", ""]
    if op.get("summary") or op.get("operationId"):
        lines.append(f"**{one_line(op.get('summary') or op.get('operationId'))}**  ")
    if op.get("description"):
        lines.append(one_line(op["description"])[:600])
    if op.get("deprecated"):
        lines.append("\n> ⚠ DEPRECATED")
    lines.append(f"\n**Auth**: {security_text(spec, op)}  ")
    if base_url:
        lines.append(f"**Full URL**: `{base_url.rstrip('/')}{path}`")

    params = res.deref(op.get("parameters", []) or [])
    rows = []
    body_schema = None
    for p in params:
        if not isinstance(p, dict):
            continue
        if p.get("in") == "body":  # swagger 2
            body_schema = p.get("schema")
            continue
        sch = p.get("schema", {}) or {k: p[k] for k in ("type", "enum", "format", "items", "default") if k in p}
        enum = sch.get("enum")
        rows.append((p.get("name"), p.get("in"), type_of(sch), "yes" if p.get("required") else "",
                     ", ".join(map(str, enum)) if enum else "", one_line(p.get("description", ""))))
    lines.append("\n**Parameters (path / query / header)**\n")
    lines.append(md_table(rows, ["name", "in", "type", "required", "enum", "description"]))

    rb = op.get("requestBody")
    if rb:
        rb = res.deref(rb)
        content = rb.get("content", {}) or {}
        for ctype, media in content.items():
            body_schema = media.get("schema")
            lines.append(f"\n**Request body** (`{ctype}`{', required' if rb.get('required') else ''})\n")
            lines.append(md_table(flatten(body_schema), ["field", "type", "required", "enum", "description"]))
            ex = media.get("example") or (list((media.get("examples") or {}).values()) or [{}])[0].get("value")
            if ex is not None:
                lines.append("\nExample:\n```json\n" + json.dumps(ex, ensure_ascii=False, indent=2)[:2000] + "\n```\n")
            break
    elif body_schema is not None:
        lines.append("\n**Request body**\n")
        lines.append(md_table(flatten(res.deref(body_schema)), ["field", "type", "required", "enum", "description"]))

    responses = res.deref(op.get("responses", {}) or {})
    for code, resp in responses.items():
        if not isinstance(resp, dict):
            continue
        content = resp.get("content", {}) or {}
        schema = resp.get("schema")  # swagger 2
        ctype = ""
        if content:
            ctype, media = next(iter(content.items()))
            schema = media.get("schema")
        if str(code).startswith("2") or schema:
            lines.append(f"\n**Response {code}** {one_line(resp.get('description',''))} {f'(`{ctype}`)' if ctype else ''}\n")
            if schema:
                lines.append(md_table(flatten(schema)[:80], ["field", "type", "required", "enum", "description"]))
            if str(code).startswith("2"):
                ex = (content.get(ctype, {}) or {}).get("example") if content else None
                if ex is not None:
                    lines.append("\nExample:\n```json\n" + json.dumps(ex, ensure_ascii=False, indent=2)[:2000] + "\n```\n")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("spec")
    ap.add_argument("--out-dir", default="openapi-summary")
    ap.add_argument("--tag", help="only this tag / group")
    ap.add_argument("--grep", help="only paths containing this substring")
    args = ap.parse_args()

    spec = load_spec(args.spec)
    res = Resolver(spec)
    servers = spec.get("servers") or []
    base_url = servers[0].get("url", "") if servers else (
        (spec.get("schemes", ["https"])[0] + "://" + spec.get("host", "") + spec.get("basePath", "")) if spec.get("host") else "")

    groups: dict[str, list] = {}
    total = 0
    for path, item in (spec.get("paths", {}) or {}).items():
        if args.grep and args.grep not in path:
            continue
        if not isinstance(item, dict):
            continue
        shared = item.get("parameters", [])
        for method in ("get", "post", "put", "patch", "delete", "head", "options"):
            op = item.get(method)
            if not isinstance(op, dict):
                continue
            op = dict(op)
            op["parameters"] = list(shared) + list(op.get("parameters", []) or [])
            tags = op.get("tags") or [path.strip("/").split("/")[0] or "root"]
            group = tags[0]
            if args.tag and group != args.tag:
                continue
            groups.setdefault(group, []).append((path, method, op))
            total += 1

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    slug = lambda s: re.sub(r"[^A-Za-z0-9._-]+", "_", s).strip("_") or "root"
    index = [f"# OpenAPI summary: {one_line((spec.get('info') or {}).get('title', args.spec))} "
             f"v{(spec.get('info') or {}).get('version', '?')}", "",
             f"Source: `{args.spec}`  ", f"Base URL: `{base_url or '(not declared)'}`  ",
             f"Endpoints: {total} in {len(groups)} groups", ""]
    schemes = (spec.get("components", {}) or {}).get("securitySchemes") or spec.get("securityDefinitions") or {}
    if schemes:
        index.append("## Security schemes\n")
        for n, s in schemes.items():
            index.append(f"- **{n}**: {json.dumps(s, ensure_ascii=False)}")
        index.append("")
    index.append("## Groups\n")
    for group, ops in sorted(groups.items()):
        fname = slug(group) + ".md"
        index.append(f"- [{group}]({fname}) — {len(ops)} endpoints")
        for path, method, _ in ops:
            index.append(f"  - `{method.upper()} {path}`")
        body = [f"# {group}", "", f"{len(ops)} endpoints. Base URL: `{base_url or '(not declared)'}`", ""]
        for path, method, op in ops:
            body.append(render_operation(spec, res, path, method, op, base_url))
            body.append("---\n")
        (out / fname).write_text("\n".join(body), encoding="utf-8")
    (out / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    print(f"wrote {len(groups)} group files + index.md to {out} ({total} endpoints)", file=sys.stderr)


if __name__ == "__main__":
    main()
