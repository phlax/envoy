#!/bin/bash

SHELLCHECK_SCRIPT_PATH="${1}"
shift
SHELLCHECK_PATH="$(cat "$SHELLCHECK_SCRIPT_PATH")"

exec "$SHELLCHECK_PATH" "$@"
