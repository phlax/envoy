load("@rules_python//python:defs.bzl", "py_binary")
load("@pytest_pip3//:requirements.bzl", "requirement")
load("//bazel:envoy_build_system.bzl", "envoy_package")

licenses(["notice"])  # Apache 2

envoy_package()

py_binary(
    name = "python_pytest",
    srcs = ["python_pytest.py"],
    visibility = ["//visibility:public"],
    deps = [
        requirement("pytest"),
    ],
)
