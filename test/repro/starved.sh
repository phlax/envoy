#!/usr/bin/env bash
# Repro only, not for envoy. Runs "$@" pinned to one CPU, shared with STARVED_HOGS busy loops
# (default 3), so the test gets a fraction of one core.

hogs="${STARVED_HOGS:-3}"
pin=()
if command -v taskset >/dev/null 2>&1; then
    cpu="$(taskset -pc $$ 2>/dev/null | sed -e 's/.*: //' -e 's/[,-].*//')"
    pin=(taskset -c "${cpu:-0}")
else
    hogs=$(( hogs * $(nproc) ))
fi
echo "starved: ${hogs} busy loops, pinned: ${pin[*]:-no}" >&2

pids=()
for _ in $(seq "$hogs"); do
    "${pin[@]}" sh -c 'while :; do :; done' &
    pids+=("$!")
done
trap 'kill "${pids[@]}" 2>/dev/null' EXIT

"${pin[@]}" "$@"
