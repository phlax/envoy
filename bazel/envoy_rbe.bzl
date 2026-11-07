"""RBE execution pool selection for Envoy targets."""

_ENGFLOW_RBE_X86_64 = Label("//bazel:engflow_rbe_x86_64")

# Configurations a pool can be chosen for, each paired with the setting that matches an EngFlow
# x86_64 build in that configuration. Listed in order of increasing precedence: each configuration
# gets its own select() so that configurations which can be enabled together (fuzz coverage turns on
# both coverage and asan) never meet in one select(), and the later entry's pool wins.
_CONFIGS = [
    ("coverage", Label("//bazel:engflow_rbe_x86_64_coverage")),
    ("tsan", Label("//bazel:engflow_rbe_x86_64_tsan")),
    ("msan", Label("//bazel:engflow_rbe_x86_64_msan")),
    ("asan", Label("//bazel:engflow_rbe_x86_64_asan")),
]

# The pool a configuration's test action goes to when a target names none for it. The pools differ
# in the per-action memory limit (xsmall, the platform default, allows 3GiB; small 7GiB; large
# 12GiB) and only large has more than four cores. Memory is the only thing Envoy tests need more
# of, and only under msan, whose peak RSS runs up to three times asan's. These apply to the test
# execution only (the `test` execution group), never to compiling or linking it, and never when the
# target supplies a pool itself.
DEFAULT_RBE_POOLS = {
    "msan": "linux_x64_small",
}

def envoy_exec_properties(rbe_pool = None, exec_properties = {}, defaults = DEFAULT_RBE_POOLS):
    """Returns `exec_properties` with the RBE pool set for EngFlow x86_64 builds.

    `rbe_pool` is either a pool name, used in every configuration, or a dict mapping
    configurations ("default", "asan", "msan", "tsan", "coverage") to pool names; a configuration
    the dict does not name uses its "default" entry. A pin applies to every action of the target,
    as it always has. A configuration with no pin, on a target that supplies no `Pool` of its own,
    runs its test action on the `defaults` entry for that configuration, if any.

    Memory-heavy sanitizer builds are the reason to pin a pool, so prefer naming the configuration
    that needs it, e.g. `rbe_pool = {"msan": "linux_x64_large"}`, over pinning every configuration.
    """
    configs = [c for c, _ in _CONFIGS]
    if rbe_pool == None:
        pools = {}
    elif type(rbe_pool) == type(""):
        pools = {"default": rbe_pool}
    elif type(rbe_pool) == type({}):
        for config in rbe_pool:
            if config != "default" and config not in configs:
                fail("rbe_pool: unknown configuration %r (expected one of default, %s)" % (config, ", ".join(configs)))
        pools = dict(rbe_pool)
    else:
        fail("rbe_pool must be a pool name or a dict of configuration to pool name, got %r" % rbe_pool)
    default = pools.get("default")
    supplied = type(exec_properties) == type({}) and ("Pool" in exec_properties or "test.Pool" in exec_properties)
    props = exec_properties
    if default:
        props = props | select({
            _ENGFLOW_RBE_X86_64: {"Pool": default},
            "//conditions:default": {},
        })
    for config, setting in _CONFIGS:
        # The configuration's effective pool: its own entry, else the target-wide one. Emitted even
        # when it equals the target-wide pool, so that where two configurations are enabled at once
        # the later one in _CONFIGS wins regardless of which entries were spelled out.
        pool = pools.get(config, default)
        if pool:
            props = props | select({setting: {"Pool": pool}, "//conditions:default": {}})
        elif not supplied and defaults.get(config):
            props = props | select({setting: {"test.Pool": defaults[config]}, "//conditions:default": {}})
    return props
