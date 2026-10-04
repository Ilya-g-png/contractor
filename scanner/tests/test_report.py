import hashlib
import json
import time

import pytest

from dogwatch.config import PackageDecl, PolicyConfig
from dogwatch.report import build_report, serialize_canonical

RAW = b'[[python.packages]]\nname = "acme"\nroot = "src"\n'
NON_ASCII_RAW = (
    "# Überprüfung der Pakete — 日本語のコメント\n"
    '[[python.packages]]\nname = "acme"\nroot = "src"  # répertoire\n'
).encode()


def _cfg(raw: bytes = RAW, path_arg: str = "dogwatch.toml") -> PolicyConfig:
    return PolicyConfig(path_arg, raw, (PackageDecl("acme", "src"),))


def test_build_report_sets_envelope_fields() -> None:
    report = build_report(_cfg(path_arg="../fixtures/minimal/dogwatch.toml"), "0.1.0")

    assert report == {
        "schema_version": "0.1",
        "scanner": {"name": "dogwatch", "version": "0.1.0"},
        "policy": {
            "path": "dogwatch.toml",
            "digest": {"sha256": hashlib.sha256(RAW).hexdigest()},
        },
        "findings": [],
    }


def test_serialized_report_matches_normative_shape() -> None:
    digest = hashlib.sha256(RAW).hexdigest()
    expected = (
        "{\n"
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
        '  "schema_version": "0.1"\n'
        "}\n"
    ).encode()

    assert serialize_canonical(build_report(_cfg(), "0.1.0")) == expected


def test_serialize_canonical_is_the_dc3_expression() -> None:
    obj = {"b": [1, {"z": None, "a": "é"}], "a": True}

    assert serialize_canonical(obj) == (
        json.dumps(
            obj, sort_keys=True, indent=2, ensure_ascii=False, separators=(",", ": ")
        )
        + "\n"
    ).encode("utf-8")


def test_serializing_twice_is_byte_identical() -> None:
    first = serialize_canonical(build_report(_cfg(), "0.1.0"))
    second = serialize_canonical(build_report(_cfg(), "0.1.0"))

    assert first == second


def test_serialized_bytes_satisfy_inv_d3() -> None:
    output = serialize_canonical(build_report(_cfg(NON_ASCII_RAW), "0.1.0"))

    assert not output.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in output
    assert output.endswith(b"}\n")
    assert not output.endswith(b"\n\n")
    assert serialize_canonical(json.loads(output)) == output
    assert list(json.loads(output)) == [
        "findings",
        "policy",
        "scanner",
        "schema_version",
    ]


def test_non_ascii_is_written_as_literal_utf8() -> None:
    output = serialize_canonical(build_report(_cfg(path_arg="dögwatch.toml"), "0.1.0"))

    assert '"path": "dögwatch.toml"'.encode() in output
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
    baseline = serialize_canonical(build_report(_cfg(NON_ASCII_RAW), "0.1.0"))

    monkeypatch.setenv("TZ", tz)
    monkeypatch.setenv("LC_ALL", lc_all)
    time.tzset()
    try:
        output = serialize_canonical(build_report(_cfg(NON_ASCII_RAW), "0.1.0"))
    finally:
        monkeypatch.undo()
        time.tzset()

    assert output == baseline
