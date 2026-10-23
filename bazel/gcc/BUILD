licenses(["notice"])  # Apache 2

# Hermetic GCC from toolshed, selected with `--config=gcc` (`--@envoy//bazel:use_gcc`).
toolchain(
    name = "linux_x86_64_toolchain",
    exec_compatible_with = [
        "@platforms//os:linux",
        "@platforms//cpu:x86_64",
    ],
    target_compatible_with = [
        "@platforms//os:linux",
        "@platforms//cpu:x86_64",
    ],
    target_settings = ["//bazel:gcc_requested"],
    toolchain = "@gcc_linux_x86_64//:cc_toolchain",
    toolchain_type = "@bazel_tools//tools/cpp:toolchain_type",
)
