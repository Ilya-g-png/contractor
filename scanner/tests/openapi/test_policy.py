from dataclasses import replace
from datetime import date

from dogwatch.config import DogwatchConfig
from dogwatch.contracts import OpenApiContractDecl
from dogwatch.openapi.normalize import normalize_openapi_changes
from dogwatch.openapi.policy import apply_openapi_policy
from dogwatch.openapi_policy import OpenApiSeverityDecl, OpenApiWaiverDecl
from dogwatch.report import OpenApiProvenance, ProvenanceBase, ProvenanceCandidate

DECL = OpenApiContractDecl("public-api", "api/openapi.yaml")
PROVENANCE = OpenApiProvenance(
    ProvenanceBase("HEAD", "a" * 40, DECL.path, "b" * 64),
    ProvenanceCandidate(DECL.path, "c" * 64),
)
RECORD = {
    "id": "api-path-removed",
    "text": "removed",
    "level": 3,
    "fingerprint": "abcdef123456",
    "operation": "GET /pets",
}
FINDING = normalize_openapi_changes(DECL, [RECORD], PROVENANCE).findings[0]


def _config(
    *,
    severities: tuple[OpenApiSeverityDecl, ...] = (),
    waivers: tuple[OpenApiWaiverDecl, ...] = (),
) -> DogwatchConfig:
    return DogwatchConfig(
        "dogwatch.toml", b"", (), (), (), (DECL,), severities, waivers
    )


def _waiver(
    contract_id: str = DECL.id,
    check_id: str = FINDING.check_id,
    operation: str = FINDING.locator.operation or "document",
    fingerprint: str = FINDING.fingerprint,
    baseline_sha256: str = PROVENANCE.base.sha256,
) -> OpenApiWaiverDecl:
    return OpenApiWaiverDecl(
        contract_id,
        check_id,
        operation,
        fingerprint,
        baseline_sha256,
        "approved",
        "2027-01-31",
    )


def test_reclassification_changes_only_effective_severity() -> None:
    config = _config(
        severities=(OpenApiSeverityDecl(FINDING.check_id, "warning", "allowed"),)
    )
    result, diagnostics = apply_openapi_policy(
        FINDING, config, DECL.id, date(2026, 11, 24)
    )
    assert diagnostics == ()
    assert result == replace(FINDING, severity="warning")


def test_exact_unexpired_waiver_remains_visible() -> None:
    config = _config(waivers=(_waiver(),))
    result, diagnostics = apply_openapi_policy(
        FINDING, config, DECL.id, date(2027, 1, 31)
    )
    assert diagnostics == ()
    assert result.fingerprint == FINDING.fingerprint
    assert result.waiver is not None
    assert result.waiver.matched
    assert result.waiver.reason == "approved"
    assert result.waiver.expires == "2027-01-31"


def test_every_waiver_identity_field_must_match() -> None:
    for changes in (
        {"contract_id": "another"},
        {"check_id": "another"},
        {"operation": "POST /pets"},
        {"fingerprint": "openapi/v1:" + "0" * 64},
        {"baseline_sha256": "0" * 64},
    ):
        result, diagnostics = apply_openapi_policy(
            FINDING, _config(waivers=(_waiver(**changes),)), DECL.id, date(2026, 11, 24)
        )
        assert result.waiver is None
        assert diagnostics == ()


def test_expired_waiver_is_inactive_with_policy_diagnostic() -> None:
    result, diagnostics = apply_openapi_policy(
        FINDING, _config(waivers=(_waiver(),)), DECL.id, date(2027, 2, 1)
    )
    assert result.waiver is None
    assert diagnostics[0].id == "openapi-policy-expired"
