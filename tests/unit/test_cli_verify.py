"""`revenant verify` on generated app folders, and the flag for generated operation ids."""

import json
import shutil
from pathlib import Path

import pytest
from revenant.cli import main
from revenant.compiler.ingest_openapi import ingest_openapi
from revenant.compiler.subset import classify_app

ROOT = Path(__file__).resolve().parents[2]
GENERATED = [ROOT / "generated" / "clinic-booking", ROOT / "generated" / "farmer-prices"]


def _run(*paths) -> int:
    with pytest.raises(SystemExit) as exc:
        main(["verify", *map(str, paths)])
    return exc.value.code


def test_committed_generated_folders_verify():
    assert _run(*GENERATED) == 0


def test_tampered_hash_fails(tmp_path, capsys):
    dst = tmp_path / "app"
    shutil.copytree(GENERATED[0], dst)
    b = json.loads((dst / "bundle.json").read_text())
    b["bundle_hash"] = "0" * 64
    (dst / "bundle.json").write_text(json.dumps(b))
    assert _run(dst) == 1
    assert "bundle_hash does not match" in capsys.readouterr().out


def test_broken_machine_fails_validators(tmp_path, capsys):
    """Delete an edge in the stored machine (and re-hash) -> a validator must flag it."""
    from revenant.compiler.emit import bundle_hash

    dst = tmp_path / "app"
    shutil.copytree(GENERATED[0], dst)
    b = json.loads((dst / "bundle.json").read_text())
    root = b["machine"]["states"][b["machine"]["root"]]
    first_key = sorted(k for k in root["transitions"] if k not in ("0", "00"))[0]
    del root["transitions"][first_key]
    hashed = json.loads(json.dumps(b))
    hashed["report"].pop("annotation", None)
    b["bundle_hash"] = bundle_hash(hashed)
    (dst / "bundle.json").write_text(json.dumps(b))
    assert _run(dst) == 1
    assert "V1_reachability" in capsys.readouterr().out


def test_missing_operation_id_is_generated_and_flagged():
    """Ingestion requirement 1.3: generated ids are flagged in the report."""
    spec = json.dumps(
        {
            "openapi": "3.0.3",
            "info": {"title": "T", "version": "1"},
            "paths": {
                "/items": {"get": {"summary": "List items"}},
                "/named": {"get": {"operationId": "named_op", "summary": "Named"}},
            },
        }
    )
    drafts, _ = ingest_openapi(spec)
    app, report = classify_app(drafts)
    assert report["generated_op_ids"] == ["get_items"]
    assert {d.id: d.id_generated for d in drafts} == {"get_items": True, "named_op": False}
