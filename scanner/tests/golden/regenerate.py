import sys

from dogwatch.output import write_report
from tests.golden.harness import (
    REPO_ROOT,
    discover_configs,
    expected_outcome,
    golden_path,
    run_scanner,
)


def main() -> int:
    configs = discover_configs()
    if not configs:
        sys.stderr.write(f"regenerate: no fixtures/*/dogwatch.toml under {REPO_ROOT}\n")
        return 1
    status = 0
    for config in configs:
        golden = golden_path(config)
        relative = golden.relative_to(REPO_ROOT).as_posix()
        expected_code, expected_stderr = expected_outcome(config)
        result = run_scanner(config, 0)
        if result.returncode != expected_code or result.stderr != expected_stderr:
            sys.stderr.write(
                f"regenerate: {relative} exited {result.returncode} "
                f"instead of {expected_code}:\n"
                + result.stderr.decode("utf-8", "replace")
            )
            status = 1
            continue
        write_report(result.output, str(golden))
        print(f"regenerated {relative}")
    return status


if __name__ == "__main__":
    sys.exit(main())
