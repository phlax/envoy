#!/usr/bin/env python3

# TODO(phlax): Move this to toolshed

# This asserts the output of `bazel/repository_locations_filter.bzl`'s
# `BZLMOD_ALL_REPOSITORY_LOCATIONS_FILTER`, applied (by the
# `:all_repository_locations_test_fixture` target) to a completely synthetic
# fixture (`bazel/test/repository_locations/{modules,metadata1,metadata2}.json`).
#
# Using a synthetic fixture rather than real dependency data means this test
# validates the filter logic itself, and is unaffected by routine dependency
# version bumps.

import json
import pathlib
import sys

deps = json.loads(pathlib.Path(sys.argv[1]).read_text())

expected = json.loads(
    (pathlib.Path(__file__).parent / "test/repository_locations/expected.json").read_text())

assert deps == expected, deps
