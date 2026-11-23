import dataclasses
import hashlib
import itertools
import json
import time

import pytest

from dogwatch import __version__
from dogwatch.config import DogwatchConfig, PackageDecl
from dogwatch.diagnostics import SOURCE_SYNTAX_INVALID, Diagnostic, Severity
from dogwatch.report import (
    Finding,
    Locator,
    OpenApiProvenance,
    ProvenanceBase,
    ProvenanceCandidate,
    Status,
    WaiverResult,
    build_report,
    derive_status,
    exit_code_for_status,
    serialize_canonical,
)

RAW = b'[[python.packages]]\nname = "acme"\nroot = "src"\n'
NON_ASCII_RAW = (
    "# Überprüfung der Pakete — 日本語のコメント\n"
    '[[python.packages]]\nname = "acme"\nroot = "src"  # répertoire\n'
).encode()
FORBIDDEN_FIELDS = (
    "commit_sha",
    "object_format",
    "dirty",
    "base_sha",
    "evaluation_date",
    "scan_started_at",
    "scan_finished_at",
    "report_id",
)
FINDING_KEYS = {
    "source",
    "check_id",
    "severity",
    "message",
    "fingerprint",
    "waiver",
    "locator",
}
DIAGNOSTIC_KEYS = {"source", "id", "severity", "message"}


def _cfg(raw: bytes = RAW, path_arg: str = "dogwatch.toml") -> DogwatchConfig:
    return DogwatchConfig(path_arg, raw, (PackageDecl("acme", "src"),), (), (), ())


def _finding(
    severity: Severity = "error",
    path: str = "src/acme/a.py",
    line: int | None = None,
    check_id: str = "no-db",
    fingerprint: str = "fp-1",
    source: str = "python",
    message: str = "acme.a imports acme.db",
) -> Finding:
    return Finding(
        source=source,
        check_id=check_id,
        severity=severity,
        message=message,
        fingerprint=fingerprint,
        locator=Locator(path, line=line),
    )


def _diagnostic(
    severity: Severity = "error",
    source: str = "dogwatch",
    id: str = SOURCE_SYNTAX_INVALID,
    message: str = "src/acme/a.py:3: invalid syntax",
) -> Diagnostic:
    return Diagnostic(source, id, severity, message)


def _openapi_finding(waiver: WaiverResult | None = None) -> Finding:
    return Finding(
        source="openapi",
        check_id="request-property-became-required",
        severity="error",
        message="Request property 'name' became required.",
        fingerprint="openapi/v1:" + "a" * 64,
        locator=Locator(
            "api/openapi.yaml",
            operation="POST /pets",
            json_pointer="/paths/~1pets/post",
        ),
        waiver=waiver,
        provenance=OpenApiProvenance(
            base=ProvenanceBase(
                "refs/heads/main", "c" * 40, "api/openapi.yaml", "b" * 64
            ),
            candidate=ProvenanceCandidate("api/openapi.yaml", "d" * 64),
        ),
    )


# --- Envelope (DC-R1) ------------------------------------------------------


def test_build_report_sets_envelope_fields() -> None:
    report = build_report(_cfg(path_arg="../fixtures/minimal/dogwatch.toml"), "0.1.0")

    assert report == {
        "schema_version": "0.3",
        "status": "pass",
        "scanner": {"name": "dogwatch", "version": "0.1.0"},
        "policy": {
            "path": "dogwatch.toml",
            "digest": {"sha256": hashlib.sha256(RAW).hexdigest()},
        },
        "findings": [],
        "diagnostics": [],
    }


def test_envelope_keys_are_exact_with_findings_and_diagnostics() -> None:
    report = build_report(
        _cfg(), __version__, [_finding("warning")], [_diagnostic("info")]
    )

    assert set(report) == {
        "schema_version",
        "status",
        "scanner",
        "policy",
        "findings",
        "diagnostics",
    }
    assert report["schema_version"] == "0.3"
    assert not set(FORBIDDEN_FIELDS) & set(report)


def test_provenance_fields_are_present() -> None:
    report = build_report(_cfg(NON_ASCII_RAW, "conf/dogwatch.toml"), __version__)

    assert report["scanner"] == {"name": "dogwatch", "version": __version__}
    assert report["policy"]["path"] == "dogwatch.toml"
    assert report["policy"]["digest"]["sha256"] == (
        hashlib.sha256(NON_ASCII_RAW).hexdigest()
    )


def test_serialized_report_matches_normative_shape() -> None:
    digest = hashlib.sha256(RAW).hexdigest()
    expected = (
        "{\n"
        '  "diagnostics": [],\n'
        '  "findings": [],\n'
        '  "policy": {\n'
        '    "digest": {\n'
        f'      "sha256": "{digest}"\n'
        "    },\n"
        '    "path": "dogwatch.toml"\n'
        "  },\n"
        '  "scanner": {\n'
        '    "name": "dogwatch",\n'
        '    "version": "0.1.0"\n'
        "  },\n"
        '  "schema_version": "0.3",\n'
        '  "status": "pass"\n'
        "}\n"
    ).encode()

    assert serialize_canonical(build_report(_cfg(), "0.1.0")) == expected


# --- Status derivation (DC-R7) and exit mapping ----------------------------


@pytest.mark.parametrize(
    ("findings", "diagnostics", "expected"),
    [
        ((), (), "pass"),
        ((), (_diagnostic("error"),), "inconclusive"),
        ((), (_diagnostic("error", "openapi", "openapi-tool-failed"),), "inconclusive"),
        ((_finding("error"),), (), "fail"),
        ((_finding("error"),), (_diagnostic("error"),), "inconclusive"),
        ((_finding("error"),), (_diagnostic("warning"),), "fail"),
        ((_finding("warning"), _finding("info")), (_diagnostic("warning"),), "pass"),
        ((_finding("info"),), (_diagnostic("info"),), "pass"),
    ],
    ids=[
        "empty",
        "error-diagnostic",
        "adapter-error-diagnostic",
        "error-finding",
        "error-finding-and-error-diagnostic",
        "error-finding-and-warning-diagnostic",
        "warning-and-info-only",
        "info-only",
    ],
)
def test_derive_status(
    findings: tuple[Finding, ...],
    diagnostics: tuple[Diagnostic, ...],
    expected: Status,
) -> None:
    assert derive_status(findings, diagnostics) == expected
    assert build_report(_cfg(), "0.1.0", findings, diagnostics)["status"] == expected


@pytest.mark.parametrize(
    ("status", "code"), [("pass", 0), ("fail", 1), ("inconclusive", 2)]
)
def test_exit_code_for_status(status: Status, code: int) -> None:
    assert exit_code_for_status(status) == code


# --- Projection (DC-R6) ----------------------------------------------------


def test_finding_projection_has_exact_keys_and_null_waiver() -> None:
    finding = Finding(
        "python",
        "no-db",
        "error",
        "acme.a imports acme.db",
        "fp-1",
        Locator("src/acme/a.py", 3, 7, "acme.a", "acme.db"),
    )

    [projected] = build_report(_cfg(), "0.1.0", [finding])["findings"]

    assert set(projected) == FINDING_KEYS
    assert projected == {
        "source": "python",
        "check_id": "no-db",
        "severity": "error",
        "message": "acme.a imports acme.db",
        "fingerprint": "fp-1",
        "waiver": None,
        "locator": {
            "path": "src/acme/a.py",
            "line": 3,
            "column": 7,
            "source_module": "acme.a",
            "target_module": "acme.db",
        },
    }


def test_openapi_finding_projects_provenance_and_waiver() -> None:
    waiver = WaiverResult("Migration window is approved.", "2027-01-31")

    [projected] = build_report(_cfg(), "0.1.0", [_openapi_finding(waiver)])["findings"]

    assert projected == {
        "source": "openapi",
        "check_id": "request-property-became-required",
        "severity": "error",
        "message": "Request property 'name' became required.",
        "fingerprint": "openapi/v1:" + "a" * 64,
        "waiver": {
            "matched": True,
            "reason": "Migration window is approved.",
            "expires": "2027-01-31",
        },
        "locator": {
            "path": "api/openapi.yaml",
            "operation": "POST /pets",
            "json_pointer": "/paths/~1pets/post",
        },
        "provenance": {
            "base": {
                "ref": "refs/heads/main",
                "commit": "c" * 40,
                "path": "api/openapi.yaml",
                "sha256": "b" * 64,
            },
            "candidate": {"path": "api/openapi.yaml", "sha256": "d" * 64},
        },
    }


def test_waived_openapi_error_does_not_fail_the_report() -> None:
    waived = _openapi_finding(WaiverResult("Migration window is approved."))

    assert derive_status((waived,), ()) == "pass"


def test_locator_omits_none_fields() -> None:
    [projected] = build_report(_cfg(), "0.1.0", [_finding()])["findings"]

    assert projected["locator"] == {"path": "src/acme/a.py"}
    assert projected["waiver"] is None
    assert b"null" not in serialize_canonical(projected["locator"])


@pytest.mark.parametrize(
    ("locator", "field", "value"),
    [
        (Locator("src/acme/a.py", line=2), "line", 2),
        (Locator("src/acme/a.py", column=2), "column", 2),
        (Locator("src/acme/a.py", source_module="acme.a"), "source_module", "acme.a"),
        (Locator("src/acme/a.py", target_module="acme.b"), "target_module", "acme.b"),
    ],
)
def test_locator_emits_each_optional_field_alone(
    locator: Locator, field: str, value: int | str
) -> None:
    finding = dataclasses.replace(_finding(), locator=locator)

    [projected] = build_report(_cfg(), "0.1.0", [finding])["findings"]

    assert projected["locator"] == {"path": "src/acme/a.py", field: value}


def test_diagnostic_projection_has_exact_keys() -> None:
    diagnostic = _diagnostic("warning", "openapi", "openapi-tool-timeout", "slow")

    [projected] = build_report(_cfg(), "0.1.0", (), [diagnostic])["diagnostics"]

    assert set(projected) == DIAGNOSTIC_KEYS
    assert projected == {
        "source": "openapi",
        "id": "openapi-tool-timeout",
        "severity": "warning",
        "message": "slow",
    }
    assert "check_id" not in projected


def test_entities_are_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        _finding().check_id = "other"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        Locator("a.py").line = 1  # type: ignore[misc]


# --- Canonical order (DC-R8) and determinism -------------------------------

FINDINGS = (
    _finding(path="src/acme/b.py", line=1),
    _finding(path="src/acme/a.py", line=10),
    _finding(path="src/acme/a.py", line=2),
    _finding(path="src/acme/a.py"),
    _finding(path="src/acme/a.py", line=2, check_id="aa-rule"),
    _finding(path="src/acme/a.py", line=2, fingerprint="fp-0"),
    _finding(path="src/acme/a.py", line=2, source="openapi"),
)
DIAGNOSTICS = (
    _diagnostic(source="openapi", id="openapi-tool-failed", message="exit 3"),
    _diagnostic(message="src/acme/z.py:1: invalid syntax"),
    _diagnostic(message="src/acme/a.py:1: invalid syntax"),
    _diagnostic("warning", "dogwatch", "aa-first", "w"),
)


def test_findings_are_sorted_canonically() -> None:
    report = build_report(_cfg(), "0.1.0", FINDINGS)

    keys = [
        (
            f["locator"]["path"],
            f["locator"].get("line", 0),
            f["check_id"],
            f["fingerprint"],
            f["source"],
        )
        for f in report["findings"]
    ]
    assert keys == [
        ("src/acme/a.py", 0, "no-db", "fp-1", "python"),
        ("src/acme/a.py", 2, "aa-rule", "fp-1", "python"),
        ("src/acme/a.py", 2, "no-db", "fp-0", "python"),
        ("src/acme/a.py", 2, "no-db", "fp-1", "openapi"),
        ("src/acme/a.py", 2, "no-db", "fp-1", "python"),
        ("src/acme/a.py", 10, "no-db", "fp-1", "python"),
        ("src/acme/b.py", 1, "no-db", "fp-1", "python"),
    ]


def test_diagnostics_are_sorted_canonically() -> None:
    report = build_report(_cfg(), "0.1.0", (), DIAGNOSTICS)

    assert [(d["source"], d["id"], d["message"]) for d in report["diagnostics"]] == [
        ("dogwatch", "aa-first", "w"),
        ("dogwatch", SOURCE_SYNTAX_INVALID, "src/acme/a.py:1: invalid syntax"),
        ("dogwatch", SOURCE_SYNTAX_INVALID, "src/acme/z.py:1: invalid syntax"),
        ("openapi", "openapi-tool-failed", "exit 3"),
    ]


def test_any_permutation_serializes_to_identical_bytes() -> None:
    baseline = serialize_canonical(build_report(_cfg(), "0.1.0", FINDINGS, DIAGNOSTICS))

    diagnostic_orders = list(itertools.permutations(DIAGNOSTICS))
    for i, findings in enumerate(itertools.permutations(FINDINGS)):
        diagnostics = diagnostic_orders[i % len(diagnostic_orders)]
        output = serialize_canonical(
            build_report(_cfg(), "0.1.0", list(findings), list(diagnostics))
        )
        assert output == baseline


def test_serialize_canonical_is_the_dc3_expression() -> None:
    obj = {"b": [1, {"z": None, "a": "é"}], "a": True}

    assert serialize_canonical(obj) == (
        json.dumps(
            obj, sort_keys=True, indent=2, ensure_ascii=False, separators=(",", ": ")
        )
        + "\n"
    ).encode("utf-8")


def test_serializing_twice_is_byte_identical() -> None:
    first = serialize_canonical(build_report(_cfg(), "0.1.0", FINDINGS, DIAGNOSTICS))
    second = serialize_canonical(build_report(_cfg(), "0.1.0", FINDINGS, DIAGNOSTICS))

    assert first == second


def test_serialized_bytes_are_canonical() -> None:
    output = serialize_canonical(
        build_report(_cfg(NON_ASCII_RAW), "0.1.0", FINDINGS, DIAGNOSTICS)
    )

    assert not output.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in output
    assert output.endswith(b"}\n")
    assert not output.endswith(b"\n\n")
    assert serialize_canonical(json.loads(output)) == output
    assert list(json.loads(output)) == [
        "diagnostics",
        "findings",
        "policy",
        "scanner",
        "schema_version",
        "status",
    ]


def test_non_ascii_is_written_as_literal_utf8() -> None:
    finding = _finding(message="Überprüfung — 日本語")
    diagnostic = _diagnostic(message="répertoire invalide")

    output = serialize_canonical(
        build_report(_cfg(path_arg="dögwatch.toml"), "0.1.0", [finding], [diagnostic])
    )

    assert '"path": "dögwatch.toml"'.encode() in output
    assert '"message": "Überprüfung — 日本語"'.encode() in output
    assert '"message": "répertoire invalide"'.encode() in output
    assert b"\\u" not in output


def test_non_ascii_config_digest_is_sha256_of_raw_bytes() -> None:
    report = build_report(_cfg(NON_ASCII_RAW), "0.1.0")

    assert report["policy"]["digest"]["sha256"] == (
        hashlib.sha256(NON_ASCII_RAW).hexdigest()
    )


@pytest.mark.parametrize(
    ("tz", "lc_all"),
    [
        ("UTC", "C"),
        ("America/Los_Angeles", "en_US.UTF-8"),
        ("Asia/Kolkata", "tr_TR.UTF-8"),
        ("Pacific/Chatham", "ja_JP.UTF-8"),
    ],
)
def test_serialized_bytes_are_stable_across_tz_and_locale(
    monkeypatch: pytest.MonkeyPatch, tz: str, lc_all: str
) -> None:
    baseline = serialize_canonical(
        build_report(_cfg(NON_ASCII_RAW), "0.1.0", FINDINGS, DIAGNOSTICS)
    )

    monkeypatch.setenv("TZ", tz)
    monkeypatch.setenv("LC_ALL", lc_all)
    time.tzset()
    try:
        output = serialize_canonical(
            build_report(_cfg(NON_ASCII_RAW), "0.1.0", FINDINGS, DIAGNOSTICS)
        )
    finally:
        monkeypatch.undo()
        time.tzset()

    assert output == baseline
