#!/usr/bin/env bash

set -euo pipefail

export BUILD_WORKSPACE_DIRECTORY="${BUILD_WORKSPACE_DIRECTORY:-$ENVOY_WORKSPACE_PATH}"

exec "$UPDATE_DEPS_BIN" "$@"
