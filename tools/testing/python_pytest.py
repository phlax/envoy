#!/usr/bin/env python3

# Usage:
#
#   bazel run //tools/testing:python_pytest -- -h
#
# or (with pytest installed):
#
#   ./tools/testing/python_pytest.py -h
#

import argparse
import sys

import pytest

from tools.base import runner, utils


class PytestRunner(runner.Runner):

    @property
    def cov_collect(self) -> str:
        return self.args.cov_collect

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Add arguments to the arg parser"""
        parser.add_argument("--cov-collect", default=None, help="Collect coverage data to path")

    def pytest_args(self, coveragerc: str) -> list:
        return self.extra_args + [f"--cov-config={coveragerc}"]

    def run(self) -> int:
        if not self.cov_collect:
            return pytest.main(self.extra_args)

        with utils.custom_coverage_data(self.cov_collect) as coveragerc:
            return pytest.main(self.pytest_args(coveragerc))


def main(*args) -> int:
    return PytestRunner(*args).run()


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
