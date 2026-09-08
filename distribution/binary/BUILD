load("@rules_pkg//pkg:mappings.bzl", "pkg_files")
load("@rules_pkg//pkg:pkg.bzl", "pkg_tar")
load("//distribution/binary:compiler.bzl", "bundled")

licenses(["notice"])  # Apache 2

bundled(
    name = "envoy",
    mode = "opt",
    stripopts = ["--strip-all"],
    targets = {
        "//distribution:envoy-binary-stripped": "envoy",
        "//distribution:envoy-contrib-binary-stripped": "envoy-contrib",
        "//distribution:envoy-binary": "dbg/envoy",
        "//distribution:envoy-dwarf": "dbg/envoy.dwp",
        "//distribution:envoy-contrib-binary": "dbg/envoy-contrib",
        "//distribution:envoy-contrib-dwarf": "dbg/envoy-contrib.dwp",
        "@su-exec": "utils/su-exec",
    },
)

pkg_files(
    name = "release_files",
    srcs = [":envoy"],
    strip_prefix = "envoy/opt",
)

# Test cert/key used by the google-vrp image. These are generated, publicly
# known *test* credentials (see certs-README.txt) generated at build time (see
# @envoy_toolshed//certs), so they cannot be ADDed from the Docker build
# context. They are carried only in the docker-only release tarball below
# (":release_docker") and are not part of ":release" / the signed release
# artifacts.
pkg_files(
    name = "vrp_cert_files",
    srcs = [
        "certs-README.txt",
        "//test/config/integration/certs:servercert.pem",
        "//test/config/integration/certs:serverkey.pem",
    ],
    prefix = "certs",
)

pkg_files(
    name = "debug_files",
    srcs = [":envoy-debug"],
    prefix = "debug",
)

# The release tarball that feeds the signing/distribution chain
# (`//distribution:signed` -> `release.signed.tar.zst`). This must not carry
# the vrp test certs (see ":vrp_cert_files").
pkg_tar(
    name = "release",
    srcs = [
        ":release_files",
    ],
    compressor = "@zstd//:zstd_cli",
    compressor_args = "-T0",
    extension = "tar.zst",
)

# A superset of ":release" that also carries the vrp test certs. This is
# consumed only by the Docker build (see distribution/docker/Dockerfile-envoy)
# and must never feed the signing/distribution chain.
pkg_tar(
    name = "release_docker",
    srcs = [
        ":release_files",
        ":vrp_cert_files",
    ],
    compressor = "@zstd//:zstd_cli",
    compressor_args = "-T0",
    out = "release.docker.tar.zst",
)
