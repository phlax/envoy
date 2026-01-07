# This should match the schema defined in external_deps.bzl.

REPOSITORY_LOCATIONS_SPEC = dict(
    # BZLMOD: NEEDS UPDATE
    quiche = dict(
        version = "0580a14c23b7f7005abd2c18587f108ed6f1e93e",
        sha256 = "30a8bbb156d5e3739dc19741837df2d8191d18dc0506727f08f2db5f88a72328",
        urls = ["https://github.com/google/quiche/archive/{version}.tar.gz"],
        strip_prefix = "quiche-{version}",
    ),
)
