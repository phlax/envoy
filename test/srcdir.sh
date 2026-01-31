#!/usr/bin/env bash
# Detect the Envoy workspace directory in the Bazel runfiles tree.
# In WORKSPACE mode the directory is named "envoy"; under bzlmod it is "_main".
# Sets ENVOY_SRCDIR and exports it. Source this file; do not execute it.
# TODO(phlax): Cleanup once bzlmod migration is complete
if [[ -d "${TEST_SRCDIR}/_main" ]]; then
    ENVOY_SRCDIR="${TEST_SRCDIR}/_main"
elif [[ -d "${TEST_SRCDIR}/envoy" ]]; then
    ENVOY_SRCDIR="${TEST_SRCDIR}/envoy"
else
    echo "Error: Could not find workspace directory at ${TEST_SRCDIR}/_main or ${TEST_SRCDIR}/envoy" >&2
    exit 1
fi
export ENVOY_SRCDIR
