load(":defs.bzl", "gcc_unavailable")

licenses(["notice"])  # Apache 2

# Hermetic GCC from toolshed, selected with `--config=gcc` (`--//bazel:use_gcc`).
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

gcc_unavailable(name = "unavailable")

# Registered after the real GCC toolchains: when GCC is requested for a Linux target that no GCC
# toolchain supports (eg aarch64), fail instead of silently falling through to Clang.
toolchain(
    name = "unavailable_toolchain",
    target_compatible_with = ["@platforms//os:linux"],
    target_settings = ["//bazel:gcc_requested"],
    toolchain = ":unavailable",
    toolchain_type = "@bazel_tools//tools/cpp:toolchain_type",
)
