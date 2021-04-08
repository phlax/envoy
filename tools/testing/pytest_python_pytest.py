#
# Runs pytest against the target:
#
#    //tools/testing/python_pytest
#
# Can be run as follows:
#
# bazel run //tools/testing:pytest_python_pytest
#

import sys

from tools.testing import python_pytest


def main(*args) -> int:
    return python_pytest.main(*args, "--cov", "tools.testing")


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:]))
