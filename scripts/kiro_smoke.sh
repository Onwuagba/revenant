#!/usr/bin/env bash
# Run the real Kiro headless annotation against the clinic draft.
# Skips cleanly (exit 0) without KIRO_API_KEY or kiro-cli. Writes the transcript
# to .kiro/evidence/ so a real run can be committed as evidence.
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -z "${KIRO_API_KEY:-}" ]] && ! kiro-cli whoami >/dev/null 2>&1; then echo "SKIP: no KIRO_API_KEY and not logged in"; exit 0; fi
if ! command -v kiro-cli >/dev/null; then echo "SKIP: kiro-cli not installed"; exit 0; fi
OUT=.kiro/evidence/smoke-$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$OUT"
python - "$OUT" <<'PY'
import json, sys
from pathlib import Path
from revenant.compiler.annotate.kiro_headless import run_kiro
from revenant.compiler.ingest_openapi import ingest_openapi
from revenant.compiler.subset import classify_app
out = Path(sys.argv[1])
drafts, _ = ingest_openapi(Path("examples/specs/clinic.openapi.yaml").read_bytes())
app, rep = classify_app(drafts, slug="clinic", title="Clinic Booking")
r = run_kiro(app, rep["refusals"], out / "runs")
(out / "result.json").write_text(json.dumps(r.report(), indent=2))
print(json.dumps(r.report(), indent=2))
sys.exit(0 if r.annotator == "kiro-cli" else 1)
PY
echo "Evidence written to $OUT (record it in .kiro/evidence/README.md)"
