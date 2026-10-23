"""Module extensions for Envoy build configuration, dependency metadata, and repositories."""

load("@envoy_toolshed//compile:llvm_minimal.bzl", "llvm_toolchain_alias", "setup_llvm_minimal")
load("@envoy_toolshed//repository:utils.bzl", "arch_alias")
load("//bazel/external/cargo/remote:crates.bzl", "crate_repositories")
load(":envoy_build_config.bzl", "default_envoy_build_config")
load(":repo.bzl", "envoy_repo")

_LOCKFILE_LABEL = Label("//:MODULE.bazel.lock")
_MODULES_SEGMENT = "/modules/"
_SOURCE_JSON_SUFFIX = "/source.json"

def _gcc_execute(repository_ctx, arguments):
    result = repository_ctx.execute(arguments, environment = {"LC_ALL": "C"})
    if result.return_code != 0:
        fail("Host GCC command %r failed (exit code %s): %s" % (arguments, result.return_code, result.stderr))
    return result

def _detect_gcc_version(repository_ctx, gcc, declared_version):
    banner = _gcc_execute(repository_ctx, [gcc, "--version"]).stdout
    if "clang" in banner.lower():
        fail("Host GCC must be GCC, not clang: %s" % gcc)
    version = _gcc_execute(repository_ctx, [gcc, "-dumpfullversion", "-dumpversion"]).stdout.strip()
    components = version.split(".")
    if not version or not all([component.isdigit() for component in components]):
        fail("Could not parse the installed GCC version: %r" % version)
    if declared_version and declared_version.split(".")[0] != components[0]:
        fail("envoy_gcc.host(gcc_version = %r) does not match the installed GCC version %s" % (declared_version, version))
    return version

def _gcc_builtin_include_directories(repository_ctx, gxx):
    repository_ctx.file("include_probe.cc", "")
    result = _gcc_execute(repository_ctx, [
        gxx,
        "-E",
        "-x",
        "c++",
        str(repository_ctx.path("include_probe.cc")),
        "-v",
    ])
    directories = []
    in_search_list = False
    complete = False
    for line in result.stderr.split("\n"):
        line = line.strip()
        if line == "#include <...> search starts here:":
            in_search_list = True
        elif in_search_list and line == "End of search list.":
            complete = True
            break
        elif in_search_list:
            directory = repository_ctx.path(line)
            if not line.startswith("/") or not directory.exists:
                fail("Invalid host GCC builtin include directory: %r" % line)
            directories.append(str(directory.realpath))
    repository_ctx.delete("include_probe.cc")
    if not complete or not directories:
        fail("Could not detect host GCC builtin C++ include directories: %s" % result.stderr)
    return directories

def _gcc_tool_path(repository_ctx, gcc_root, gcc, tool):
    candidate = gcc_root.get_child("bin/" + tool)
    if candidate.exists:
        return str(candidate)
    value = _gcc_execute(repository_ctx, [gcc, "-print-prog-name=" + tool]).stdout.strip()
    if value.startswith("/") and repository_ctx.path(value).exists:
        return value
    if value and "/" not in value:
        resolved = repository_ctx.which(value)
        if resolved:
            return str(resolved)
    fail("Could not resolve host GCC tool %r under %s or through %s -print-prog-name" % (tool, gcc_root, gcc))

def _host_gcc_repo_impl(repository_ctx):
    repository_ctx.file("BUILD.bazel", 'package(default_visibility = ["//visibility:public"])\n')
    if not repository_ctx.attr.path:
        return
    if not repository_ctx.os.name.lower().startswith("linux"):
        fail("envoy_gcc.host supports only native Linux hosts")
    arch = repository_ctx.os.arch.lower()
    if arch in ["x86_64", "amd64"]:
        cpu = "k8"
        platform_cpu = "x86_64"
    elif arch in ["aarch64", "arm64"]:
        cpu = "aarch64"
        platform_cpu = "aarch64"
    else:
        fail("Unsupported host GCC architecture: %s" % arch)
    if not repository_ctx.attr.path.startswith("/"):
        fail("envoy_gcc.host path must be an absolute GCC installation prefix")
    gcc_root = repository_ctx.path(repository_ctx.attr.path)
    gcc = str(gcc_root.get_child("bin/gcc"))
    gxx = str(gcc_root.get_child("bin/g++"))
    version = _detect_gcc_version(repository_ctx, gcc, repository_ctx.attr.gcc_version)
    target = _gcc_execute(repository_ctx, [gcc, "-dumpmachine"]).stdout.strip()
    if target.split("-")[0] != platform_cpu or "linux" not in target:
        fail("Host GCC target %r does not match the native Linux %s host" % (target, platform_cpu))
    includes = _gcc_builtin_include_directories(repository_ctx, gxx)
    tool_paths = {"gcc": gcc}
    for tool in ["ar", "as", "cpp", "dwp", "gcov", "nm", "objcopy", "objdump", "strip"]:
        tool_paths[tool] = _gcc_tool_path(repository_ctx, gcc_root, gcc, tool)
    tool_paths["ld"] = _gcc_tool_path(repository_ctx, gcc_root, gcc, "ld.bfd")
    linker_directory = str(repository_ctx.path(tool_paths["ld"]).dirname)
    repository_ctx.file("BUILD.bazel", """
load("@rules_cc//cc/toolchains:cc_toolchain.bzl", "cc_toolchain")
# buildifier: disable=bzl-visibility
load("@rules_cc//cc/private/toolchain:unix_cc_toolchain_config.bzl", "cc_toolchain_config")

package(default_visibility = ["//visibility:public"])

# Host tools and headers are intentionally external to the sandbox; this is not an RBE toolchain.
filegroup(name = "empty")

cc_toolchain_config(
    name = "config",
    abi_libc_version = "local",
    abi_version = "local",
    compile_flags = ["-fstack-protector", "-Wall", "-fno-omit-frame-pointer"],
    compiler = "gcc",
    coverage_compile_flags = ["--coverage"],
    coverage_link_flags = ["--coverage"],
    cpu = %r,
    cxx_builtin_include_directories = %r,
    cxx_flags = ["-std=c++20"],
    dbg_compile_flags = ["-g"],
    host_system_name = "local",
    link_flags = [%r, "-fuse-ld=bfd", "-Wl,-z,relro,-z,now", "-pass-exit-codes"],
    link_libs = ["-l:libstdc++.a", "-lm"],
    opt_compile_flags = ["-g0", "-O2", "-D_FORTIFY_SOURCE=1", "-DNDEBUG", "-ffunction-sections", "-fdata-sections"],
    opt_link_flags = ["-Wl,--gc-sections"],
    supports_start_end_lib = False,
    target_libc = "local",
    target_system_name = %r,
    tool_paths = %r,
    toolchain_identifier = %r,
    unfiltered_compile_flags = [
        "-no-canonical-prefixes",
        "-fno-canonical-system-headers",
        "-Wno-builtin-macro-redefined",
        "-D__DATE__=\\"redacted\\"",
        "-D__TIME__=\\"redacted\\"",
        "-D__TIMESTAMP__=\\"redacted\\"",
    ],
)

cc_toolchain(
    name = "compiler",
    all_files = ":empty",
    ar_files = ":empty",
    as_files = ":empty",
    compiler_files = ":empty",
    dwp_files = ":empty",
    linker_files = ":empty",
    objcopy_files = ":empty",
    strip_files = ":empty",
    supports_param_files = True,
    toolchain_config = ":config",
    toolchain_identifier = %r,
)

toolchain(
    name = "cc_toolchain",
    exec_compatible_with = ["@platforms//os:linux", "@platforms//cpu:%s"],
    target_compatible_with = ["@platforms//os:linux", "@platforms//cpu:%s"],
    target_settings = ["@envoy//bazel:gcc_requested"],
    toolchain = ":compiler",
    toolchain_type = "@bazel_tools//tools/cpp:toolchain_type",
)
""" % (
        cpu,
        includes,
        "-B" + linker_directory + "/",
        target,
        tool_paths,
        "envoy-host-gcc-" + version,
        "envoy-host-gcc-" + version,
        platform_cpu,
        platform_cpu,
    ))

_host_gcc_repo = repository_rule(
    implementation = _host_gcc_repo_impl,
    local = True,
    attrs = {
        "gcc_version": attr.string(default = ""),
        "path": attr.string(default = ""),
    },
)

def _envoy_gcc_impl(module_ctx):
    host = None
    for module in module_ctx.modules:
        for tag in module.tags.host:
            if not module.is_root:
                fail("envoy_gcc_extension.host may only be specified by the root module")
            if host != None:
                fail("envoy_gcc_extension.host may only be specified once")
            if not tag.path:
                fail("envoy_gcc.host path must be an absolute GCC installation prefix")
            host = tag
    _host_gcc_repo(
        name = "envoy_gcc_host",
        gcc_version = host.gcc_version if host else "",
        path = host.path if host else "",
    )

_host_gcc = tag_class(
    attrs = {
        "gcc_version": attr.string(default = ""),
        "path": attr.string(mandatory = True),
    },
)

envoy_gcc_extension = module_extension(
    implementation = _envoy_gcc_impl,
    tag_classes = {"host": _host_gcc},
)

def _module_dep_from_lock_entry(url):
    if not url.endswith(_SOURCE_JSON_SUFFIX):
        return None

    parts = url.split(_MODULES_SEGMENT)
    if len(parts) != 2:
        fail("Unexpected module registry URL in MODULE.bazel.lock: %s" % url)

    registry = parts[0] + "/"
    module_parts = parts[1][:-len(_SOURCE_JSON_SUFFIX)].split("/")
    if len(module_parts) != 2:
        fail("Unexpected module registry URL in MODULE.bazel.lock: %s" % url)

    return struct(
        module_name = module_parts[0],
        registry = registry,
        version = module_parts[1],
    )

def _envoy_mod_graph_repo_impl(repository_ctx):
    lockfile = json.decode(repository_ctx.read(repository_ctx.attr.lockfile))
    registry_file_hashes = lockfile.get("registryFileHashes", {})
    deps = {}

    for url in registry_file_hashes:
        module_dep = _module_dep_from_lock_entry(url)
        if module_dep == None:
            continue
        if module_dep.module_name in deps:
            fail("MODULE.bazel.lock has multiple source.json entries for module %s" % module_dep.module_name)

        module_url = "%smodules/%s/%s/" % (module_dep.registry, module_dep.module_name, module_dep.version)
        deps[module_dep.module_name] = {
            "module_url": module_url,
            "registry": module_dep.registry,
            "urls": [module_url],
            "version": module_dep.version,
        }

    repository_ctx.file(
        "BUILD.bazel",
        "exports_files([\"deps.json\"], visibility = [\"//visibility:public\"])\n",
    )
    repository_ctx.file("deps.json", json.encode(deps))

_envoy_mod_graph_repo = repository_rule(
    implementation = _envoy_mod_graph_repo_impl,
    attrs = {
        "lockfile": attr.label(allow_single_file = True, mandatory = True),
    },
)

def _envoy_module_graph_impl(module_ctx):
    _envoy_mod_graph_repo(
        name = "envoy_mod_graph",
        lockfile = _LOCKFILE_LABEL,
    )

def _envoy_build_config_impl(module_ctx):
    default_envoy_build_config(name = "envoy_build_config")

envoy_build_config_ext = module_extension(
    implementation = _envoy_build_config_impl,
)

envoy_module_graph_extension = module_extension(
    implementation = _envoy_module_graph_impl,
    doc = """
    Extension that watches MODULE.bazel.lock and materializes resolved module
    dependency metadata as @envoy_mod_graph//:deps.json.
    """,
)

def _envoy_repo_impl(module_ctx):
    """Implementation of the envoy_repo module extension.

    This extension creates the envoy_repo repository which provides version
    information and container metadata for RBE builds.

    Args:
        module_ctx: The module extension context
    """
    envoy_repo()

envoy_repo_extension = module_extension(
    implementation = _envoy_repo_impl,
    doc = """
    Extension for the envoy_repo repository.

    This extension creates the @envoy_repo repository which provides:
    - Version information (VERSION, API_VERSION)
    - Container metadata for RBE builds (containers.bzl)
    - LLVM compiler configuration
    - Repository path information

    This is required for RBE toolchain configuration and various build utilities.
    """,
)

def _wasm_cargo_impl(module_ctx):
    direct_deps = crate_repositories()
    return module_ctx.extension_metadata(
        root_module_direct_deps = [repo.repo for repo in direct_deps],
        root_module_direct_dev_deps = [],
        reproducible = True,
    )

wasm_cargo = module_extension(implementation = _wasm_cargo_impl)

_LLVM_MIGRATION = """
`envoy_llvm_extension` (@envoy//bazel:extensions.bzl) is deprecated and will be removed.
Migrate your MODULE.bazel to the toolshed extension:

    llvm_toolchain_alias_ext = use_extension(
        "@envoy_toolshed//compile:extensions.bzl",
        "llvm_toolchain_alias_extension",
    )
    # Optional, root module only, to use a host LLVM install:
    # llvm_toolchain_alias_ext.host(path = "/usr/lib/llvm-22")
    use_repo(llvm_toolchain_alias_ext, "llvm_toolchain_llvm")

See bazel/README.md and bazel/tests/codeql for a complete example.
"""

# TODO(phlax): Remove once downstream modules have migrated.
def _envoy_llvm_impl(module_ctx):
    # buildifier: disable=print
    print("DEPRECATED: " + _LLVM_MIGRATION)
    for module in module_ctx.modules:
        if module.tags.host:
            # A host tag here can no longer redirect Envoy's own @llvm_toolchain_llvm
            # (that now comes from the toolshed extension), so fail rather than
            # silently produce an unused repo.
            fail(
                "envoy_llvm_extension.host() is no longer supported (set by module %r)." % module.name +
                _LLVM_MIGRATION,
            )

    # Deprecated no-tag path: mirror toolshed's llvm_toolchain_alias_extension so an
    # existing `use_repo(envoy_llvm_ext, "llvm_toolchain_llvm")` keeps resolving.
    setup_llvm_minimal()
    llvm_toolchain_alias(
        name = "llvm_toolchain_llvm",
        minimal_linux_x64 = "@llvm_minimal_linux_x64//:BUILD.bazel",
        minimal_linux_arm64 = "@llvm_minimal_linux_arm64//:BUILD.bazel",
        minimal_macos_arm64 = "@llvm_minimal_macos_arm64//:BUILD.bazel",
    )

_host_llvm = tag_class(
    attrs = {
        "llvm_version": attr.string(default = ""),
        "path": attr.string(mandatory = True),
    },
)

envoy_llvm_extension = module_extension(
    implementation = _envoy_llvm_impl,
    tag_classes = {"host": _host_llvm},
    doc = "Deprecated: use @envoy_toolshed//compile:extensions.bzl%llvm_toolchain_alias_extension.",
)

# TODO(phlax): Remove once envoy-examples (and any other registry modules) use
# @envoy_toolshed//repository:extensions.bzl%arch_alias_extension directly.
def _envoy_toolchains_impl(module_ctx):
    # buildifier: disable=print
    print(
        "DEPRECATED: `envoy_toolchains_extension` is deprecated; use " +
        "@envoy_toolshed//repository:extensions.bzl%arch_alias_extension with " +
        "`.alias(name = \"clang_platform\", amd64 = \"@envoy//bazel/platforms/rbe:linux_x64\", " +
        "aarch64 = \"@envoy//bazel/platforms/rbe:linux_arm64\")` and " +
        "`use_repo(arch_alias_ext, \"clang_platform\")`.",
    )
    arch_alias(
        name = "clang_platform",
        aliases = {
            "amd64": str(Label("//bazel/platforms/rbe:linux_x64")),
            "aarch64": str(Label("//bazel/platforms/rbe:linux_arm64")),
        },
    )

envoy_toolchains_extension = module_extension(
    implementation = _envoy_toolchains_impl,
    doc = "Deprecated: use @envoy_toolshed arch_alias_extension instead.",
)
