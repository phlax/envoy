load(
    "//bazel:envoy_build_system.bzl",
    "envoy_cc_test",
    "envoy_package",
)

licenses(["notice"])  # Apache 2

envoy_package()

# Each target below pins its RBE pools differently; the trace of a run over this package shows
# which pool every compile, link and test action of each target landed on. Not for merge.

envoy_cc_test(
    name = "probe_unpinned",
    srcs = ["probe_test.cc"],
)

envoy_cc_test(
    name = "probe_string",
    srcs = ["probe_test.cc"],
    rbe_pool = "linux_x64_medium",
)

envoy_cc_test(
    name = "probe_build_only",
    srcs = ["probe_test.cc"],
    rbe_pool = {"build": "linux_x64_medium"},
)

envoy_cc_test(
    name = "probe_link_only",
    srcs = ["probe_test.cc"],
    rbe_pool = {"link": "linux_x64_large"},
)

envoy_cc_test(
    name = "probe_build_link_test",
    srcs = ["probe_test.cc"],
    rbe_pool = {
        "build": "linux_x64_small",
        "link": "linux_x64_large",
        "test": "linux_x64_medium",
    },
)

envoy_cc_test(
    name = "probe_new_keys",
    srcs = ["probe_test.cc"],
    rbe_pool = {
        "default": {"build": "linux_x64_small"},
        "cto": {
            "build": "linux_x64_medium",
            "link": "linux_x64_large",
        },
        "openssl": {"build": "linux_x64_medium"},
        "asan": {"build": "linux_x64_large"},
        "fuzz_coverage": {"link": "linux_x64_medium"},
    },
)
