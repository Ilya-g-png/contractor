from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from dogwatch.config import DogwatchConfig
from dogwatch.contracts import OpenApiContractDecl
from dogwatch.diagnostics import Diagnostic
from dogwatch.openapi.git import read_baseline, resolve_baseline_ref
from dogwatch.openapi.model import BaselineReference
from dogwatch.openapi.normalize import normalize_openapi_changes
from dogwatch.openapi.policy import apply_openapi_policy
from dogwatch.openapi.preflight import preflight_candidate, preflight_pair
from dogwatch.openapi.runner import run_oasdiff
from dogwatch.openapi.tool import resolve_verified_oasdiff
from dogwatch.report import (
    Finding,
    OpenApiProvenance,
    ProvenanceBase,
    ProvenanceCandidate,
)

ComparisonState = Literal["no-change", "completed", "policy-failed", "inconclusive"]


@dataclass(frozen=True)
class OpenApiComparison:
    contract_id: str
    baseline: BaselineReference | None
    state: ComparisonState
    findings: tuple[Finding, ...]
    diagnostics: tuple[Diagnostic, ...]


@dataclass(frozen=True)
class ComparisonResult:
    comparisons: tuple[OpenApiComparison, ...]
    findings: tuple[Finding, ...]
    diagnostics: tuple[Diagnostic, ...]


def compare_openapi_contracts(
    cfg: DogwatchConfig,
    baseline_ref: str | None,
    candidate_root: Path,
    *,
    cache_dir: Path | None = None,
    evaluation_date: date | None = None,
) -> ComparisonResult:
    if not cfg.contracts:
        return ComparisonResult((), (), ())
    if not baseline_ref:
        diagnostic = Diagnostic(
            "openapi",
            "openapi-baseline-ref-required",
            "error",
            "OpenAPI contracts require --baseline-ref",
        )
        return _aggregate(
            tuple(_failed(decl, None, (diagnostic,)) for decl in cfg.contracts)
        )
    resolution = resolve_baseline_ref(candidate_root, baseline_ref)
    if resolution.reference is None:
        return _aggregate(
            tuple(_failed(decl, None, resolution.diagnostics) for decl in cfg.contracts)
        )
    baseline = resolution.reference
    tool_cache = cache_dir or candidate_root / ".dogwatch" / "oasdiff"
    today = evaluation_date or date.today()
    comparisons = tuple(
        _compare(cfg, decl, baseline, candidate_root, tool_cache, today)
        for decl in cfg.contracts
    )
    return _aggregate(comparisons)


def _compare(
    cfg: DogwatchConfig,
    decl: OpenApiContractDecl,
    baseline: BaselineReference,
    candidate_root: Path,
    cache_dir: Path,
    evaluation_date: date,
) -> OpenApiComparison:
    candidate = preflight_candidate(candidate_root, decl)
    base = read_baseline(candidate_root, baseline, decl)
    pair = preflight_pair(candidate, base)
    if pair.inputs is None:
        return _failed(decl, baseline, pair.diagnostics)
    candidate_input, base_input = pair.inputs
    tool = resolve_verified_oasdiff(cache_dir)
    if tool.executable is None:
        return _failed(decl, baseline, tool.diagnostics)
    run = run_oasdiff(
        tool.executable, base_input.canonical_json, candidate_input.canonical_json
    )
    if run.records is None:
        return _failed(decl, baseline, run.diagnostics)
    provenance = OpenApiProvenance(
        base=ProvenanceBase(
            baseline.supplied_ref,
            baseline.resolved_commit,
            decl.path,
            base_input.raw_sha256,
        ),
        candidate=ProvenanceCandidate(decl.path, candidate_input.raw_sha256),
    )
    normalized = normalize_openapi_changes(decl, run.records, provenance)
    if normalized.diagnostics:
        return _failed(decl, baseline, normalized.diagnostics)
    processed = tuple(
        apply_openapi_policy(finding, cfg, decl.id, evaluation_date)
        for finding in normalized.findings
    )
    findings = tuple(finding for finding, _ in processed)
    diagnostics = tuple(diagnostic for _, group in processed for diagnostic in group)
    state: ComparisonState = (
        "no-change"
        if not findings
        else "policy-failed"
        if any(f.severity == "error" and f.waiver is None for f in findings)
        else "completed"
    )
    return OpenApiComparison(decl.id, baseline, state, findings, diagnostics)


def _failed(
    decl: OpenApiContractDecl,
    baseline: BaselineReference | None,
    diagnostics: tuple[Diagnostic, ...],
) -> OpenApiComparison:
    return OpenApiComparison(decl.id, baseline, "inconclusive", (), diagnostics)


def _aggregate(comparisons: tuple[OpenApiComparison, ...]) -> ComparisonResult:
    return ComparisonResult(
        comparisons,
        tuple(finding for comparison in comparisons for finding in comparison.findings),
        tuple(
            diagnostic
            for comparison in comparisons
            for diagnostic in comparison.diagnostics
        ),
    )
