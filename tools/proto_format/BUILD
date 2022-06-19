load("//bazel:envoy_build_system.bzl", "envoy_package")
load("//tools/base:envoy_python.bzl", "envoy_genjson", "envoy_py_data")
load("//tools/protoxform:protoprint.bzl", "protoprint_rule")
load("@aspect_bazel_lib//lib:jq.bzl", "jq")
load("@envoy_repo//:path.bzl", "PATH")
load("@rules_python//python:defs.bzl", "py_binary")
load("@rules_pkg//pkg:mappings.bzl", "pkg_files", "strip_prefix")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")

load("@dev_pip3//:requirements.bzl", dev_requirement = "requirement")

licenses(["notice"])  # Apache 2

envoy_package()

# Bazel query doesnt support json output, and jq insists on inputs with json suffix,
# although can handle "raw" data also. For these reasons these queries have json
# suffix but are not valid json.
# See: https://github.com/aspect-build/bazel-lib/issues/162
genquery(
    name = "active_proto_targets_txt.json",
    expression = "labels(srcs, labels(deps, @envoy_api//versioning:active_protos))",
    scope = ["@envoy_api//versioning:active_protos"],
)

genquery(
    name = "frozen_proto_targets_txt.json",
    expression = "labels(srcs, labels(deps, @envoy_api//versioning:frozen_protos))",
    scope = ["@envoy_api//versioning:frozen_protos"],
)

jq(
    name = "proto_targets",
    srcs = [
        ":active_proto_targets_txt.json",
        ":frozen_proto_targets_txt.json",
    ],
    out = "proto_targets.json",
    args = ["-sR"],
    filter = """
    split("\n") |  map(select(length>0))
    """,
)

envoy_genjson(
    name = "data_srcs",
    srcs = [
        ":proto_targets",
        "@envoy_api//bazel:external_proto_deps",
    ],
    filter = """
    {proto_targets: .[0],
     external_proto_deps: .[1]}
    """,
)

envoy_py_data(
    name = "data",
    src = ":data_srcs",
)

protoprint_rule(
    name = "prettyprinted_srcs",
    deps = ["//tools/protoxform:api_protoxform"],
)

pkg_files(
    name = "prettyprinted_files",
    srcs = [":prettyprinted_srcs"],
    strip_prefix = strip_prefix.from_pkg(),
)

pkg_files(
    name = "prettyprinted_files_stripped",
    srcs = [":prettyprinted_files"],
    strip_prefix = "pkg",
)

pkg_tar(
    name = "prettyprinted",
    srcs = [":prettyprinted_files_stripped"],
)

pkg_files(
    name = "xformed_files",
    srcs = ["//tools/protoxform:api_protoxform"],
    strip_prefix = strip_prefix.from_pkg(),
)

pkg_tar(
    name = "xformed",
    srcs = [":xformed_files"],
)

py_binary(
    name = "format_api",
    srcs = ["format_api.py"],
    args = [
        "--api_root=%s/api" % PATH,
        "--protoprint=$(location //tools/protoxform:protoprint)",
        "--descriptor=$(location //tools/type_whisperer:api_type_db.pb_text)",
    ],
    data = [
        "//:.clang-format",
        "//:API_VERSION.txt",
        "//tools/type_whisperer:api_type_db.pb_text",
    ],
    deps = [
        ":data",
        "//tools/api_proto_plugin:utils",
        "//tools/protoxform:protoprint",
        dev_requirement("remote_pdb"),
    ],
)

genrule(
    name = "formatted_api",
    outs = ["formatted_api.tar"],
    cmd = """
    $(location :format_api) \
        --api_root=%s/api \
        --protoprint=$(location //tools/protoxform:protoprint) \
        --descriptor=$(location //tools/type_whisperer:api_type_db.pb_text) \
        --outfile=$@ \
        --xformed=$(location :xformed) \
        --protoprinted=$(location :prettyprinted) \
    """ % PATH,
    tools = [
        ":format_api",
        ":prettyprinted",
        ":xformed",
        "//tools/protoxform:protoprint",
        "//tools/type_whisperer:api_type_db.pb_text",
    ],
)

py_binary(
    name = "proto_sync",
    srcs = ["proto_sync.py"],
    args = [
        "--api_root=%s/api" % PATH,
        "--formatted=$(location :formatted_api)",
    ],
    data = [":formatted_api"],
)
