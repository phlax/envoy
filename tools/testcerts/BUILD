load("@rules_cc//cc:defs.bzl", "cc_binary")
load(
    "//bazel:envoy_build_system.bzl",
    "envoy_cc_test",
)

licenses(["notice"])  # Apache 2

package(default_visibility = ["//visibility:public"])

exports_files(["certs.bzl"])

# Hermetic, in-process test certificate generator.
#
# This deliberately does NOT use `envoy_cc_binary` and does NOT depend on
# `//bazel:crypto`/`//bazel:ssl` (the label_flags that can be switched to the
# OpenSSL compatibility layer). It links BoringSSL directly so that the
# fixtures it emits are identical no matter which TLS provider Envoy itself is
# built against.
cc_binary(
    name = "gen",
    srcs = ["gen.cc"],
    deps = ["@boringssl//:crypto"],
)

envoy_cc_test(
    name = "gen_test",
    srcs = ["gen_test.cc"],
    data = [
        "//test/common/tls/ocsp/test_data:certs",
        "//test/common/tls/test_data:certs",
        "//test/config/integration/certs",
    ],
    rbe_pool = "linux_x64_small",
    deps = [
        "//source/common/tls/ocsp:ocsp_lib",
        "//test/common/tls:ssl_test_utils",
        "//test/test_common:environment_lib",
        "//test/test_common:simulated_time_system_lib",
        "//test/test_common:utility_lib",
    ],
)
