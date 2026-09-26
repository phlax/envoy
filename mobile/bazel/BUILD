load("@bazel_skylib//lib:selects.bzl", "selects")
load("@envoy//bazel:envoy_build_system.bzl", "envoy_mobile_package")
load("@rules_java//toolchains:default_java_toolchain.bzl", "default_java_toolchain")

licenses(["notice"])  # Apache 2

envoy_mobile_package()

config_setting(
    name = "exclude_certificates",
    values = {"define": "exclude_certificates=true"},
)

exports_files([
    "pom_template.xml",
    "test_manifest.xml",
])

alias(
    name = "zipper",
    actual = "@bazel_tools//tools/zip:zipper",
)

alias(
    name = "jni",
    actual = "@rules_java//toolchains:jni",
    visibility = ["//library/jni:__pkg__"],
)

alias(
    name = "objc_dummy",
    actual = "@bazel_tools//tools/objc:dummy.c",
    visibility = ["//library/jni:__pkg__"],
)

# autoformat requires that there be no @bazel_tools references outside of //bazel,
# so we alias all of the relevant platforms for determining wheel packaging here
alias(
    name = "darwin_arm64",
    actual = "@bazel_tools//src/conditions:darwin_arm64",
)

alias(
    name = "darwin_x86_64",
    actual = "@bazel_tools//src/conditions:darwin_x86_64",
)

alias(
    name = "darwin",
    actual = "@bazel_tools//src/conditions:darwin",
)

alias(
    name = "linux_aarch64",
    actual = "@bazel_tools//src/conditions:linux_aarch64",
)

alias(
    name = "linux_x86_64",
    actual = "@bazel_tools//src/conditions:linux_x86_64",
)

config_setting(
    name = "exec_linux",
    constraint_values = ["@platforms//os:linux"],
)

config_setting(
    name = "exec_macos",
    constraint_values = ["@platforms//os:macos"],
)

config_setting(
    name = "exec_aarch64",
    constraint_values = ["@platforms//cpu:aarch64"],
)

config_setting(
    name = "exec_x86_64",
    constraint_values = ["@platforms//cpu:x86_64"],
)

selects.config_setting_group(
    name = "exec_linux_aarch64",
    match_all = [
        ":exec_linux",
        ":exec_aarch64",
    ],
)

selects.config_setting_group(
    name = "exec_linux_x86_64",
    match_all = [
        ":exec_linux",
        ":exec_x86_64",
    ],
)

selects.config_setting_group(
    name = "exec_macos_aarch64",
    match_all = [
        ":exec_macos",
        ":exec_aarch64",
    ],
)

selects.config_setting_group(
    name = "exec_macos_x86_64",
    match_all = [
        ":exec_macos",
        ":exec_x86_64",
    ],
)

alias(
    name = "dokka_java_runtime",
    actual = select({
        ":exec_linux_aarch64": "@remotejdk17_linux_aarch64//:jdk",
        ":exec_linux_x86_64": "@remotejdk17_linux//:jdk",
        ":exec_macos_aarch64": "@remotejdk17_macos_aarch64//:jdk",
        ":exec_macos_x86_64": "@remotejdk17_macos//:jdk",
    }),
    visibility = ["//visibility:public"],
)

# Keep JavaBuilder on the concrete JDK 25 runtime because rules_java's BazelJavaBuilder is built
# for newer bytecode than JDK 17, while Android builds still compile Java 8 bytecode and
# test/runtime toolchain resolution below stays on JDK 17.
[
    default_java_toolchain(
        name = "envoy_mobile_java_toolchain_" + suffix,
        exec_compatible_with = constraints,
        java_runtime = "@remotejdk25_%s//:jdk" % suffix,
        javabuilder_jvm_opts = ["--sun-misc-unsafe-memory-access=allow"],
        source_version = "8",
        target_version = "8",
    )
    for suffix, constraints in {
        "linux": [
            "@platforms//os:linux",
            "@platforms//cpu:x86_64",
        ],
        "linux_aarch64": [
            "@platforms//os:linux",
            "@platforms//cpu:aarch64",
        ],
        "macos": [
            "@platforms//os:macos",
            "@platforms//cpu:x86_64",
        ],
        "macos_aarch64": [
            "@platforms//os:macos",
            "@platforms//cpu:aarch64",
        ],
    }.items()
]

# Envoy Mobile's JVM test stack (Robolectric 4.16, Netty 4.1.x ALPN, Mockito) does not yet
# work on the JDK 25 runtime that @envoy registers by default, so the root module pins its Java
# runtime to 17 for builds and tests under mobile/. TODO(phlax): drop this once the test
# dependencies support newer JDK runtimes.
_JDK17_PLATFORMS = {
    "linux": [
        "@platforms//os:linux",
        "@platforms//cpu:x86_64",
    ],
    "linux_aarch64": [
        "@platforms//os:linux",
        "@platforms//cpu:aarch64",
    ],
    "macos": [
        "@platforms//os:macos",
        "@platforms//cpu:x86_64",
    ],
    "macos_aarch64": [
        "@platforms//os:macos",
        "@platforms//cpu:aarch64",
    ],
}

[
    toolchain(
        name = "envoy_mobile_java_runtime_toolchain_" + suffix,
        target_compatible_with = constraints,
        toolchain = "@remotejdk17_%s//:jdk" % suffix,
        toolchain_type = "@bazel_tools//tools/jdk:runtime_toolchain_type",
    )
    for suffix, constraints in _JDK17_PLATFORMS.items()
]
