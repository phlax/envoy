load("//bazel:envoy_build_system.bzl", "envoy_package")
load(":distros.bzl", "pkg_distro")

pkg_distro("debian_buster")

envoy_package()

pkg_distro(
    "debian_bullseye",
    distro = "debian",
    tag = "bullseye-slim",
)

pkg_distro(
    "ubuntu_impish",
    distro = "ubuntu",
    tag = "21.10",
)

pkg_distro(
    "ubuntu_hirstute",
    distro = "ubuntu",
    tag = "21.04",
)

pkg_distro(
    "redhat_8.1",
    distro = "registry.access.redhat.com/ubi8/ubi",
    tag = "8.1",
)

pkg_distro(
    "redhat_8.2",
    distro = "registry.access.redhat.com/ubi8/ubi",
    tag = "8.2",
)

pkg_distro(
    "redhat_8.3",
    distro = "registry.access.redhat.com/ubi8/ubi",
    tag = "8.3",
)

pkg_distro(
    "redhat_8.4",
    distro = "registry.access.redhat.com/ubi8/ubi",
    tag = "8.4",
)
