"""Regenerate generated/clinic-booking and generated/farmer-prices (deterministic annotator)."""
from pathlib import Path

from revenant.api.seed import FARMER_TOOLS
from revenant.compiler.annotate.pipeline import compile_with_annotation
from revenant.compiler.emit import emit_folder
from revenant.compiler.ingest_mcp import ingest_mcp_tools
from revenant.compiler.ingest_openapi import ingest_openapi
from revenant.compiler.subset import classify_app

root = Path(__file__).resolve().parents[1]
drafts, _ = ingest_openapi((root / "examples/specs/clinic.openapi.yaml").read_bytes())
app, rep = classify_app(drafts, slug="clinic-booking", title="Clinic Booking")
emit_folder(compile_with_annotation(app, rep["refusals"]), root / "generated/clinic-booking")

drafts, ing = ingest_mcp_tools(FARMER_TOOLS)
app, rep = classify_app(drafts, slug="farmer-prices", title="Farmer Prices")
b = compile_with_annotation(app, rep["refusals"])
emit_folder(b, root / "generated/farmer-prices")
print("farmer-prices:", "all validators passed" if b["report"]["all_passed"] else "VIOLATIONS", b["bundle_hash"][:12])
