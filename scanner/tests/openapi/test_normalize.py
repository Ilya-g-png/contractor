import hashlib
import json

from dogwatch.contracts import OpenApiContractDecl
from dogwatch.openapi.normalize import normalize_openapi_changes
from dogwatch.report import OpenApiProvenance, ProvenanceBase, ProvenanceCandidate

DECL = OpenApiContractDecl("public-api", "api/openapi.yaml")
PROVENANCE = OpenApiProvenance(
    ProvenanceBase("HEAD~1", "a" * 40, DECL.path, "b" * 64),
    ProvenanceCandidate(DECL.path, "c" * 64),
)


def _record(**changes: object) -> dict[str, object]:
    record: dict[str, object] = {
        "id": "api-path-removed",
        "text": "operation removed",
        "level": 3,
        "fingerprint": "123456abcdef",
        "operation": "get /pets/{id}",
    }
    record.update(changes)
    return record


def test_normalizes_locator_provenance_and_pinned_identity() -> None:
    result = normalize_openapi_changes(DECL, [_record()], PROVENANCE)
    assert result.diagnostics == ()
    finding = result.findings[0]
    assert finding.source == "openapi"
    assert finding.check_id == "api-path-removed"
    assert finding.severity == "error"
    assert finding.message == "operation removed"
    assert finding.locator.path == DECL.path
    assert finding.locator.operation == "GET /pets/{id}"
    assert finding.locator.json_pointer == "/paths/~1pets~1{id}/get"
    assert finding.provenance == PROVENANCE
    identity = [
        DECL.id,
        finding.check_id,
        {
            "path": DECL.path,
            "operation": "GET /pets/{id}",
            "json_pointer": "/paths/~1pets~1{id}/get",
        },
        "123456abcdef",
    ]
    expected = hashlib.sha256(
        json.dumps(identity, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()
    assert finding.fingerprint == f"openapi/v1:{expected}"


def test_message_and_severity_do_not_change_identity_but_tool_identity_does() -> None:
    first = normalize_openapi_changes(DECL, [_record()], PROVENANCE).findings[0]
    changed = normalize_openapi_changes(
        DECL, [_record(text="new wording", level=2)], PROVENANCE
    ).findings[0]
    distinct = normalize_openapi_changes(
        DECL, [_record(fingerprint="abcdef123456")], PROVENANCE
    ).findings[0]
    assert changed.fingerprint == first.fingerprint
    assert changed.severity == "warning"
    assert distinct.fingerprint != first.fingerprint


def test_document_locator_and_deterministic_order() -> None:
    records = [
        _record(operation="POST /z", fingerprint="ffffffffffff"),
        _record(operation="", path="/pets"),
        _record(operation="GET /a", fingerprint="aaaaaaaaaaaa"),
    ]
    first = normalize_openapi_changes(DECL, records, PROVENANCE)
    second = normalize_openapi_changes(DECL, list(reversed(records)), PROVENANCE)
    assert first == second
    assert [finding.locator.operation for finding in first.findings] == [
        "GET /a",
        "POST /z",
        "document",
    ]
    assert first.findings[-1].locator.json_pointer == "/paths/~1pets"


def test_unknown_record_discards_all_findings() -> None:
    result = normalize_openapi_changes(
        DECL, [_record(), _record(operation="bad locator")], PROVENANCE
    )
    assert result.findings == ()
    assert result.diagnostics[0].id == "openapi-tool-failed"
    assert result.diagnostics[0].severity == "error"
