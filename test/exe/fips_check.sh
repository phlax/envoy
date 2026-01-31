#!/usr/bin/env bash

set -e


# env vars dont really work in bazels env - so replace with correct var
OBJDUMP="${OBJDUMP//\$\{LLVM_DIRECTORY\}/$LLVM_DIRECTORY}"

# TODO(phlax): Cleanup once bzlmod migration is complete
# Determine workspace directory (envoy in WORKSPACE mode, _main in bzlmod mode)
# shellcheck source=test/srcdir.sh
source "${TEST_SRCDIR}/_main/test/srcdir.sh" 2>/dev/null || source "${TEST_SRCDIR}/envoy/test/srcdir.sh"
ENVOY_BIN="${ENVOY_SRCDIR}/test/exe/all_extensions_build_test"

# FIPS requires a consistency self-test. In practice, the FIPS binary has
# special markers for the start and the end of the crypto code which we can use
# to validate that the binary was built in FIPS mode.
${OBJDUMP:-objdump} -t "${ENVOY_BIN}" | grep BORINGSSL_bcm_text_start
