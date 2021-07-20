load("//bazel:envoy_build_system.bzl", "envoy_package")
load("@distribution_pip3//:requirements.bzl", "requirement")
load("//tools/base:envoy_python.bzl", "envoy_py_binary")

licenses(["notice"])  # Apache 2

envoy_package()

exports_files([
    "distrotest.sh",
])

envoy_py_binary(
    name = "tools.distribution.verify",
    deps = [
        "//tools/base:checker",
        "//tools/docker:utils",
        requirement("pyyaml"),
    ],
)
