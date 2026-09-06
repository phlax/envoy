"""Bazel rules for generating test certificate fixtures.

The fixtures in `test/common/tls/test_data`, `test/common/tls/ocsp/test_data`
and `test/config/integration/certs` used to be checked in and refreshed by hand
with a `certs.sh` script that shelled out to the OpenSSL CLI (and, in one case,
to `docker run ... faketime`). They are now produced at build time by
//tools/testcerts:gen, which links BoringSSL directly.

The generator stamps certificates with a validity window that starts on Jan 1 of
the year the build runs in, so fixtures never age out of validity. The year comes
from the `STABLE_CERT_EPOCH_YEAR` entry that `bazel/get_workspace_status` writes
into `bazel-out/stable-status.txt`.
"""

def generated_certs(name, spec, outs, srcs = [], static_srcs = [], visibility = None):
    """Generates test certificates from `spec` and bundles them into a filegroup.

    Args:
      name: name of the resulting filegroup. Consumers depend on this via
        `data = [...]`.
      spec: the fixture spec file consumed by //tools/testcerts:gen.
      outs: every file the generator writes for this spec. The generator fails
        if the spec asks for an output that is not declared here.
      srcs: generator inputs (keys, `.cfg` files, password files).
      static_srcs: checked-in fixtures that are not generated but that consumers
        expect to find alongside the generated ones.
      visibility: visibility of the generated targets.
    """
    native.genrule(
        name = name + "_gen",
        srcs = [spec] + srcs,
        outs = outs,
        cmd = " ".join([
            "YEAR=$$(sed -n -E 's/^STABLE_CERT_EPOCH_YEAR (.*)$$/\\1/p'",
            "< bazel-out/stable-status.txt);",
            "[ -n \"$$YEAR\" ] || YEAR=$$(date -u +%Y);",
            "$(location //tools/testcerts:gen)",
            "--spec $(location " + spec + ")",
            "--in-dir $$(dirname $(location " + spec + "))",
            "--out-dir $(RULEDIR)",
            "--year \"$$YEAR\";",
            "missing=\"\";",
            "for out in $(OUTS); do",
            "  if [ ! -e \"$$out\" ]; then missing=\"$$missing $$out\"; fi;",
            "done;",
            "if [ -n \"$$missing\" ]; then",
            "  echo \"//tools/testcerts:gen did not create declared output(s):$$missing\" >&2;",
            "  exit 1;",
            "fi;",
        ]),
        # Undocumented attr to depend on the workspace status files; see
        # source/common/version/BUILD for the same pattern.
        # https://github.com/bazelbuild/bazel/issues/4942
        stamp = 1,
        tools = ["//tools/testcerts:gen"],
        visibility = visibility,
    )

    native.filegroup(
        name = name,
        srcs = outs + static_srcs,
        visibility = visibility,
    )
