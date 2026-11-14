"""Everything published for an arch, from any host (`ci/do_ci.sh release.publish.all`)."""

_RBE_EXEC_PLATFORM = str(Label("//distribution:rbe_exec_platform"))

def _arch_transition_impl(_settings, attr):
    return {
        "//command_line_option:platforms": [attr.platform],
        _RBE_EXEC_PLATFORM: attr.rbe_exec_platform,
    }

_arch_transition = transition(
    implementation = _arch_transition_impl,
    inputs = [],
    outputs = [
        "//command_line_option:platforms",
        _RBE_EXEC_PLATFORM,
    ],
)

def _arch_files_impl(ctx):
    outputs = {}
    for file in ctx.files.srcs:
        if file.basename in outputs:
            fail("publish: %s is published twice for %s" % (file.basename, ctx.attr.platform))
        output = ctx.actions.declare_file("%s/%s" % (ctx.label.name, file.basename))
        ctx.actions.symlink(output = output, target_file = file)
        outputs[file.basename] = output
    return [DefaultInfo(files = depset(outputs.values()))]

arch_files = rule(
    implementation = _arch_files_impl,
    doc = """`srcs` built for `platform`, at `<name>/<basename>`.

The binaries are compiled on `rbe_exec_platform` (through `bundled`, see
`//distribution/binary:compiler.bzl`), eg the arm64 workers for an arm64 release built from an x64
host, while the rest (eg the local packaging) runs on the host.""",
    attrs = {
        "platform": attr.string(
            doc = "The target platform.",
            mandatory = True,
        ),
        "rbe_exec_platform": attr.string(
            doc = "The RBE execution platform for the binaries, or empty for the build's.",
        ),
        "srcs": attr.label_list(
            allow_files = True,
            cfg = _arch_transition,
            mandatory = True,
        ),
        "_allowlist_function_transition": attr.label(
            default = "@bazel_tools//tools/allowlists/function_transition_allowlist",
        ),
    },
)
