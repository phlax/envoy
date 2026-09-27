load("@bazel_skylib//lib:selects.bzl", "selects")
load("@envoy//bazel:envoy_build_system.bzl", "envoy_mobile_package")

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
