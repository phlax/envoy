load("@rules_shell//shell:sh_binary.bzl", "sh_binary")

licenses(["notice"])  # Apache 2

# Repro only, not for envoy: `--run_under=//test/repro:starved` runs a test on a single CPU shared
# with busy loops, to reproduce flakes that need a slow, contended first run.
sh_binary(
    name = "starved",
    srcs = ["starved.sh"],
)
