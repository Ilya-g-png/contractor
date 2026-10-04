import argparse
import os
import sys
from collections.abc import Sequence
from typing import NoReturn

from dogwatch import __version__
from dogwatch.config import load_policy
from dogwatch.diagnostics import EXIT_ERROR, EXIT_OK, DogwatchError, render
from dogwatch.output import STDOUT, write_report
from dogwatch.report import build_report, serialize_canonical

DEFAULT_CONFIG = "./dogwatch.toml"
DEFAULT_OUTPUT = "./dogwatch-report.json"


class _Parser(argparse.ArgumentParser):
    # Subcommand parsers would otherwise report as "dogwatch check: error:".
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        self.exit(EXIT_ERROR, f"dogwatch: error: {message}\n")


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="dogwatch")
    parser.add_argument(
        "--version", action="version", version=f"dogwatch {__version__}"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check")
    check.add_argument("--config", default=DEFAULT_CONFIG, metavar="PATH")
    check.add_argument("--output", default=DEFAULT_OUTPUT, metavar="PATH")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    config_arg: str = args.config
    output_arg: str = args.output
    try:
        policy = load_policy(config_arg)
    except DogwatchError as err:
        sys.stderr.write(render(err))
        return EXIT_ERROR
    if output_arg != STDOUT and _same_file(output_arg, config_arg):
        return _error(
            f"output path {output_arg} is the same file as config {config_arg}"
        )
    data = serialize_canonical(build_report(policy, __version__))
    try:
        write_report(data, output_arg)
    except OSError as exc:
        return _error(f"cannot write report to {output_arg}: {exc.strerror or exc}")
    return EXIT_OK


def _same_file(output_arg: str, config_arg: str) -> bool:
    if os.path.realpath(output_arg) == os.path.realpath(config_arg):
        return True
    return (
        os.path.exists(output_arg)
        and os.path.exists(config_arg)
        and os.path.samefile(output_arg, config_arg)
    )


def _error(message: str) -> int:
    sys.stderr.write(f"dogwatch: error: {message}\n")
    return EXIT_ERROR
