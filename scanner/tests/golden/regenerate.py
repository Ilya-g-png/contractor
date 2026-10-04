import sys

from dogwatch.output import write_report
from tests.golden.harness import REPO_ROOT, discover_configs, golden_path, run_scanner


def main() -> int:
    configs = discover_configs()
    if not configs:
        sys.stderr.write(f"regenerate: no fixtures/*/dogwatch.toml under {REPO_ROOT}\n")
        return 1
    status = 0
    for config in configs:
        golden = golden_path(config)
        relative = golden.relative_to(REPO_ROOT).as_posix()
        result = run_scanner(config, 0)
        if result.returncode != 0 or result.stderr:
            sys.stderr.write(
                f"regenerate: {relative} failed (exit {result.returncode}):\n"
                + result.stderr.decode("utf-8", "replace")
            )
            status = 1
            continue
        write_report(result.output, str(golden))
        print(f"regenerated {relative}")
    return status


if __name__ == "__main__":
    sys.exit(main())
