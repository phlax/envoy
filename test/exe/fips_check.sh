#!/usr/bin/env bash

set -eu

# env vars dont really work in bazels env - so replace with correct var
LLVM_DIRECTORY="${LLVM_DIRECTORY:-}"
OBJDUMP="${OBJDUMP:-}"
OBJDUMP="${OBJDUMP//\$\{LLVM_DIRECTORY\}/$LLVM_DIRECTORY}"

# TODO(phlax): Cleanup once bzlmod migration is complete
ENVOY_SRCDIR="${TEST_SRCDIR}/${TEST_WORKSPACE}"
ENVOY_BIN="${ENVOY_SRCDIR}/test/exe/all_extensions_build_test"

# FIPS requires a consistency self-test. In practice, the FIPS binary has
# special markers for the start and the end of the crypto code which we can use
# to validate that the binary was built in FIPS mode.
${OBJDUMP:-objdump} -t "${ENVOY_BIN}" | grep BORINGSSL_bcm_text_start
