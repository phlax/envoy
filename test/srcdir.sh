#!/usr/bin/env bash
# Detect the Envoy workspace directory in the Bazel runfiles tree.
# Sets ENVOY_SRCDIR and exports it. Source this file; do not execute it.
# TODO(phlax): Cleanup once bzlmod migration is complete
if [[ -z "${TEST_WORKSPACE}" ]]; then
    echo "Error: TEST_WORKSPACE is not set" >&2
    exit 1
fi
ENVOY_SRCDIR="${TEST_SRCDIR}/${TEST_WORKSPACE}"
export ENVOY_SRCDIR
