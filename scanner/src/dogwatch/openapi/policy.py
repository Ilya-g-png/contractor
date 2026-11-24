from dataclasses import replace
from datetime import date

from dogwatch.config import DogwatchConfig
from dogwatch.diagnostics import Diagnostic
from dogwatch.report import Finding, WaiverResult


def apply_openapi_policy(
    finding: Finding,
    cfg: DogwatchConfig,
    contract_id: str,
    evaluation_date: date,
) -> tuple[Finding, tuple[Diagnostic, ...]]:
    if (
        finding.source != "openapi"
        or finding.provenance is None
        or finding.waiver is not None
    ):
        raise ValueError("policy requires an unprocessed OpenAPI finding")
    severity = next(
        (
            decl.severity
            for decl in cfg.openapi_severities
            if decl.check_id == finding.check_id
        ),
        finding.severity,
    )
    waiver = None
    diagnostics: list[Diagnostic] = []
    for decl in cfg.openapi_waivers:
        if (
            decl.contract_id != contract_id
            or decl.check_id != finding.check_id
            or decl.operation != finding.locator.operation
            or decl.fingerprint != finding.fingerprint
            or decl.baseline_sha256 != finding.provenance.base.sha256
        ):
            continue
        if (
            decl.expires is not None
            and date.fromisoformat(decl.expires) < evaluation_date
        ):
            diagnostics.append(
                Diagnostic(
                    "openapi",
                    "openapi-policy-expired",
                    "warning",
                    f"{contract_id}: waiver for {finding.check_id} "
                    f"expired on {decl.expires}",
                )
            )
        else:
            waiver = WaiverResult(reason=decl.reason, expires=decl.expires)
        break
    return replace(finding, severity=severity, waiver=waiver), tuple(diagnostics)
