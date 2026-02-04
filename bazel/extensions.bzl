"""Module extensions for Envoy's non-module dependencies.

This file defines module extensions to support Envoy's bzlmod migration while
respecting existing WORKSPACE patches and custom BUILD files.
"""

load("@envoy_api//bazel:envoy_http_archive.bzl", "envoy_http_archive")
load("@envoy_api//bazel:external_deps.bzl", "load_repository_locations")
load("@envoy_toolshed//repository:utils.bzl", "arch_alias")
load("//bazel/external/cargo:crates.bzl", "raze_fetch_remote_crates")
load(":repo.bzl", "envoy_repo")
load(":repository_locations.bzl", "REPOSITORY_LOCATIONS_SPEC")

REPOSITORY_LOCATIONS = load_repository_locations(REPOSITORY_LOCATIONS_SPEC)

def external_http_archive(name, **kwargs):
    envoy_http_archive(
        name,
        locations = REPOSITORY_LOCATIONS,
        **kwargs
    )

def _default_envoy_build_config_impl(ctx):
    ctx.file("WORKSPACE", "")
    ctx.file("BUILD.bazel", "")
    ctx.symlink(ctx.attr.config, "extensions_build_config.bzl")

default_envoy_build_config = repository_rule(
    implementation = _default_envoy_build_config_impl,
    attrs = {
        "config": attr.label(default = "@envoy//source/extensions:extensions_build_config.bzl"),
    },
)

def _envoy_build_config_impl(module_ctx):
    default_envoy_build_config(name = "envoy_build_config")

envoy_build_config_ext = module_extension(
    implementation = _envoy_build_config_impl,
)

def _envoy_dependencies_impl(module_ctx):
    """Implementation of the envoy_dependencies module extension.

    Args:
        module_ctx: The module extension context
    """
    external_http_archive(
        name = "quiche",
        patch_cmds = ["find quiche/ -type f -name \"*.bazel\" -delete"],
        build_file = "@envoy//bazel/external:quiche.BUILD",
        repo_mapping = {"@com_google_absl": "@abseil-cpp"},
    )

def _envoy_repo_impl(module_ctx):
    """Implementation of the envoy_repo module extension.

    This extension creates the envoy_repo repository which provides version
    information and container metadata for RBE builds.

    Args:
        module_ctx: The module extension context
    """
    envoy_repo()

def _envoy_toolchains_impl(module_ctx):
    """Implementation of the envoy_toolchains module extension.

    This extension registers toolchains needed for Envoy builds in bzlmod mode,
    including the clang_platform alias used in various BUILD files.

    In WORKSPACE mode, this is handled by calling envoy_toolchains() from WORKSPACE.
    In bzlmod mode, we need to use this extension to make the same repositories available.

    Args:
        module_ctx: The module extension context
    """

    # Create the clang_platform repository using arch_alias
    # Note: We can't call envoy_toolchains() directly here because it uses native.register_toolchains
    # which is not allowed in module extensions. Instead, we only create the arch_alias repository.
    arch_alias(
        name = "clang_platform",
        aliases = {
            "amd64": "@envoy//bazel/platforms/rbe:linux_x64",
            "aarch64": "@envoy//bazel/platforms/rbe:linux_arm64",
        },
    )

# Define the module extensions
envoy_dependencies_extension = module_extension(
    implementation = _envoy_dependencies_impl,
    doc = """
    Extension for Envoy runtime dependencies not available in BCR or requiring patches.

    This extension calls the same envoy_dependencies() function used by WORKSPACE mode,
    but with bzlmod=True. This ensures both build systems load dependencies identically,
    making the migration clear and reviewable.

    Dependencies already in BCR are skipped automatically via conditional checks.
    For WORKSPACE mode, call envoy_dependencies() directly from WORKSPACE.

    See the module documentation above for maintenance guidelines.
    """,
)

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

envoy_toolchains_extension = module_extension(
    implementation = _envoy_toolchains_impl,
    doc = """
    Extension for Envoy toolchain setup in bzlmod mode.

    This extension creates toolchain-related repositories needed for Envoy builds:
    - clang_platform: Architecture-specific platform aliases for RBE builds

    In WORKSPACE mode, these are created by calling envoy_toolchains() from WORKSPACE.
    In bzlmod mode, this extension provides the same functionality.

    Note: Toolchain registration itself is handled by MODULE.bazel using the LLVM
    toolchain extension. This extension only creates auxiliary repositories.
    """,
)

def _crates_deps_impl(module_ctx):
    deps = []
    for repo in raze_fetch_remote_crates():
        if not repo.is_dev_dep:
            deps.append(repo.repo)

    return module_ctx.extension_metadata(
        root_module_direct_deps = deps,
        root_module_direct_dev_deps = [],
    )

crates_deps = module_extension(
    doc = "Dependencies for bazel/external/cargo.",
    implementation = _crates_deps_impl,
)
