"""Envoy-specific dependency reachability rule.

``rule()`` may only be called during ``.bzl`` initialization (top-level
evaluation), so the constructed rule cannot live in ``BUILD``.  This module
exists solely to construct it once, here, and re-export the wrapping macro for
use from ``tools/dependency/BUILD``.

The wasm runtime is selected via ``--//bazel:wasm_runtime=...`` (see the
``wasm_runtime`` string_flag and the ``wasm_v8`` / ``wasm_wamr`` /
``wasm_wasmtime`` config_settings in ``//bazel:BUILD``).

``flags``/``defines`` must be fixed at rule construction because transition
``outputs`` are static and cannot vary per target instantiation.  A single
constructed rule can be instantiated any number of times with different
``configs``.
"""

load(
    "@envoy_toolshed//dependency:reachability.bzl",
    "dependency_reachability_macro",
    "dependency_reachability_rule",
)

_envoy_dependency_reachability_rule = dependency_reachability_rule(
    flags = ["//bazel:wasm_runtime"],
)

envoy_dependency_reachability = dependency_reachability_macro(
    _envoy_dependency_reachability_rule,
)
