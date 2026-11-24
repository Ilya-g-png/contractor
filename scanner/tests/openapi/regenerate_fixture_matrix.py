import sys

from dogwatch.output import write_report
from tests.openapi.matrix_harness import FIXTURES, discover_cases, run_case


def main() -> int:
    cases = discover_cases()
    if not cases:
        sys.stderr.write(f"regenerate: no fixture cases under {FIXTURES}\n")
        return 1
    status = 0
    for case in cases:
        result = run_case(case)
        if result.exit_code != case.exit_code:
            sys.stderr.write(
                f"regenerate: {case.name} exited {result.exit_code} "
                f"instead of {case.exit_code}:\n{result.stderr}"
            )
            status = 1
            continue
        write_report(result.report, str(case.report_path))
        if result.invocations:
            (invocation,) = result.invocations
            write_report(invocation, str(case.invocation_path))
        print(f"regenerated {case.name}")
    return status


if __name__ == "__main__":
    sys.exit(main())
