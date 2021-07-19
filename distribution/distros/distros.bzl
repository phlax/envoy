load("@rules_pkg//:pkg.bzl", "pkg_tar")

def pkg_distro(
        name = None,
        dockerfile = "debian",
        tag = "",
        distro = "",
        visibility = ["//visibility:public"]):

    build_srcs = []

    if tag or distro:
        env_command = []

        if tag:
            env_command += ["echo 'tag: \"" + tag + "\"' >> $@"]

        if distro:
            env_command += ["echo 'distro: \'" + distro + "\'' >> $@"]

        native.genrule(
            name = "build-env-" + name,
            cmd = "\n".join(env_command),
            outs = [name + "/env"],
        )
        build_srcs += [":build-env-" + name]

    pkg_tar(
        name = "build-" + name,
        extension = "tar",
        package_dir = name,
        srcs = build_srcs,
    )
