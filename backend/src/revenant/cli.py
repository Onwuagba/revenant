"""``revenant`` command line: verify, compile, mcp-validator.

Exit codes: 0 ok, 1 validator violations / compile errors, 2 every operation refused
(only with --strict for ``verify``).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .compiler.annotate.pipeline import compile_with_annotation
from .compiler.emit import emit_folder
from .compiler.ingest_openapi import IngestError, ingest_openapi
from .compiler.subset import classify_app

SPEC_SUFFIXES = {".yaml", ".yml", ".json"}


def _specs(path: Path) -> list[Path]:
    if path.is_dir():
        return sorted(p for p in path.rglob("*") if p.suffix in SPEC_SUFFIXES)
    return [path]


def _compile(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    drafts, ing_ref = ingest_openapi(path.read_bytes())
    slug = path.name.split(".")[0].lower().replace("_", "-")
    app, report = classify_app(drafts, slug=slug, title=slug.replace("-", " ").title())
    if not app.operations:
        return None, report
    refusals = report["refusals"] + [
        {"op_id": r.op_id, "path": r.path, "code": r.code.value, "message": r.message, "hint": r.hint}
        for r in ing_ref]
    return compile_with_annotation(app, refusals), report


def cmd_verify(args: argparse.Namespace) -> int:
    code = 0
    for spec in _specs(Path(args.path)):
        try:
            bundle, report = _compile(spec)
        except IngestError as exc:
            print(f"FAIL {spec}: {exc.code}")
            code = 1
            continue
        per_code = ", ".join(f"{k}={v}" for k, v in sorted(report["per_code"].items())) or "none"
        if bundle is None:
            print(f"REFUSED {spec}: every operation refused ({per_code})")
            if args.strict:
                code = max(code, 2)
            continue
        failed = [v for v in bundle["report"]["validators"] if not v["passed"]]
        status = "OK" if not failed else "FAIL"
        ann = bundle["report"]["annotation"]["annotator"]
        print(f"{status} {spec}: compiled={report['compiled_count']} refused={report['refused_count']} "
              f"[{per_code}] validators={len(bundle['report']['validators']) - len(failed)}/"
              f"{len(bundle['report']['validators'])} annotator={ann} hash={bundle['bundle_hash'][:12]}")
        for v in failed:
            for x in v["violations"]:
                print(f"  {v['validator']}: {x['state_id']} {x['message']}")
        if failed:
            code = 1
    return code


def cmd_compile(args: argparse.Namespace) -> int:
    bundle, report = _compile(Path(args.spec))
    if bundle is None:
        print("Every operation was refused; nothing to emit.")
        return 2
    files = emit_folder(bundle, args.out)
    print(f"Wrote {len(files)} files to {args.out} (hash {bundle['bundle_hash'][:12]})")
    return 0 if bundle["report"]["all_passed"] else 1


def cmd_mcp_validator(_: argparse.Namespace) -> int:
    from .mcp_validator.server import main as run

    run()
    return 0


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="revenant")
    sub = p.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="compile specs and run validators")
    v.add_argument("path")
    v.add_argument("--strict", action="store_true", help="exit 2 when every operation is refused")
    v.set_defaults(fn=cmd_verify)
    c = sub.add_parser("compile", help="compile a spec into a generated app folder")
    c.add_argument("spec")
    c.add_argument("--out", required=True)
    c.set_defaults(fn=cmd_compile)
    m = sub.add_parser("mcp-validator", help="run the validator MCP server on stdio")
    m.set_defaults(fn=cmd_mcp_validator)
    args = p.parse_args(argv)
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
