load("@envoy_toolshed//:macros.bzl", "json_data")
load("@envoy_toolshed//:utils.bzl", "json_merge")
load("@io_bazel_rules_go//proto:compiler.bzl", "go_proto_compiler")
load(
    ":external_proto_deps.bzl",
    "EXTERNAL_PROTO_CC_BAZEL_DEP_MAP",
    "EXTERNAL_PROTO_GO_BAZEL_DEP_MAP",
    "EXTERNAL_PROTO_IMPORT_BAZEL_DEP_MAP",
)

licenses(["notice"])  # Apache 2

exports_files([
    "extensions.bzl",
    "repository_locations.bzl",
    "repository_locations_utils.bzl",
    "utils.bzl",
    "deps.yaml",
])

go_proto_compiler(
    name = "vtprotobuf_plugin_go",
    options = [
        "features=marshal_strict+size",
        "buildTag=vtprotobuf",
    ],
    plugin = "@com_github_planetscale_vtprotobuf//cmd/protoc-gen-go-vtproto",
    suffix = "_vtproto.pb.go",
    valid_archive = False,
    visibility = ["//visibility:public"],
)

json_merge(
    name = "repository_locations",
    filter = """
    .[0] as $data
    | $data
    | keys
    | reduce .[] as $k ({};
        . + if ($data[$k].version and $data[$k].version != "MISSING"
                and ($data[$k].urls | length) > 0
                and $data[$k].project_name != "MISSING")
            then {($k): (
              $data[$k]
              | .version as $ver
              | if .license_url and $ver then
                  .license_url |= (
                    gsub("{version}"; $ver)
                    | gsub("{dash_version}"; ($ver | gsub("[.]"; "-")))
                    | gsub("{underscore_version}"; ($ver | gsub("[.]"; "_")))
                  )
                else . end
            )}
            else {} end
      )
    """,
    visibility = ["//visibility:public"],
    yaml_srcs = [":deps.yaml"],
)

json_data(
    name = "external_proto_deps",
    data = dict(
        cc = EXTERNAL_PROTO_CC_BAZEL_DEP_MAP,
        go = EXTERNAL_PROTO_GO_BAZEL_DEP_MAP,
        imports = EXTERNAL_PROTO_IMPORT_BAZEL_DEP_MAP,
    ),
)
