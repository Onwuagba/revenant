"""Annotate -> merge -> compile -> repair pipeline with honest reporting."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..emit import compile_app
from ..ir import App
from .cache import AnnotationCache
from .deterministic import annotate_deterministic
from .kiro_headless import AGENT_VERSION, AnnotatorResult, run_kiro, spec_hash
from .merge import apply_annotations

MAX_REPAIRS = 2


def _violations(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {"validator": r["validator"], **v}
        for r in bundle["report"]["validators"]
        if not r["passed"]
        for v in r["violations"]
    ]


def _build(app: App, annotations: dict[str, Any]) -> dict[str, Any]:
    annotated, hidden = apply_annotations(app, annotations)
    return compile_app(annotated, hidden)


def compile_with_annotation(
    app: App,
    refusals: list[dict[str, Any]] | None = None,
    *,
    kiro_enabled: bool = False,
    cache: AnnotationCache | None = None,
    runs_root: Path = Path("runs"),
    kiro_bin: str = "kiro-cli",
    timeout: float = 120,
) -> dict[str, Any]:
    """Return a bundle whose ``report['annotation']`` says exactly what ran."""
    refusals = refusals or []
    key = spec_hash(app)
    result: AnnotatorResult

    cached = cache.get(key, AGENT_VERSION) if cache else None
    if cached is not None:
        result = AnnotatorResult("cached", cached, cached=True)
    elif kiro_enabled:
        result = run_kiro(app, refusals, runs_root, kiro_bin=kiro_bin, timeout=timeout)
    else:
        result = AnnotatorResult("deterministic", annotate_deterministic(app), fallback_reason="")

    bundle = _build(app, result.annotations)

    # Repair loop: only for a real Kiro result, at most MAX_REPAIRS runs.
    while (
        not bundle["report"]["all_passed"]
        and result.annotator == "kiro-cli"
        and result.repair_attempts < MAX_REPAIRS
    ):
        attempts = result.repair_attempts + 1
        fixed = run_kiro(
            app,
            refusals,
            runs_root,
            kiro_bin=kiro_bin,
            timeout=timeout,
            violations=_violations(bundle),
        )
        if fixed.annotator != "kiro-cli":
            result = AnnotatorResult(
                "deterministic",
                annotate_deterministic(app),
                fallback_reason="repair failed: " + fixed.fallback_reason,
                transcript_path=fixed.transcript_path,
                exit_code=fixed.exit_code,
                repair_attempts=attempts,
            )
            bundle = _build(app, result.annotations)
            break
        fixed.repair_attempts = attempts
        result, bundle = fixed, _build(app, fixed.annotations)

    # Kiro output is data; validators are the gate. If it still fails, fall back.
    if not bundle["report"]["all_passed"] and result.annotator in ("kiro-cli", "cached"):
        result = AnnotatorResult(
            "deterministic",
            annotate_deterministic(app),
            fallback_reason="validators rejected annotations",
            transcript_path=result.transcript_path,
            exit_code=result.exit_code,
            repair_attempts=result.repair_attempts,
        )
        bundle = _build(app, result.annotations)

    if cache and result.annotator == "kiro-cli" and bundle["report"]["all_passed"]:
        cache.put(key, AGENT_VERSION, result.annotations)

    bundle["report"]["annotation"] = result.report()
    # bundle_hash covers the IR/machine; the annotation report is metadata.
    return bundle
