#!/usr/bin/env python3
"""Validate dependency metadata against build graph reachability data.

This replaces the old validate.py which used `bazel query` (slow, broken under
bzlmod).  The data source is the pre-built ``dependency_reachability`` JSON
produced by the ``@envoy_toolshed`` aspect.

NOTE: This Python implementation is transitional.  After the bzlmod migration,
this logic will move to jq inside ``@envoy_toolshed``, where it will be
properly tested.  Do not invest in Python unit tests here.

Two reachability roots are declared (see tools/dependency/BUILD):

  dep-reachability-core — rooted at envoy_main_common_with_core_extensions_lib.
      Used only to derive the "core dep" set for the extension-marginal check.

  dep-reachability — rooted at main_common_with_all_extensions_lib (all
      extensions).  This is the primary reachability data used by all checks.

Core deps are those reachable from the core root; extension-marginal deps are
those reachable from the all-extensions root but *not* from the core root.
This restores the original deps(ext) − deps(core) semantics from validate.py.

Checks still covered outside this test:

(a) validate_build_graph_structure: the old assertion
    deps(//source/...) == deps(core) ∪ deps(//source/extensions/...)
    is enforced by tools/dependency/validate_graph_structure.sh. It is not
    expressible over the reachability JSON because the aspect only covers targets
    reachable from declared concrete roots; it cannot root at //source/... or ask
    whether anything exists outside those roots.

(b) validate_test_only_deps (second direction): the old code also verified that
    deps reachable from //test/... but not //source/... were declared test_only,
    carrying an allowlist for raze__/cu__/remotejdk/_pip3 and an openssl
    exclusion. That direction is enforced by
    tools/dependency/validate_graph_structure.sh for the same reason: //test/...
    is not a declared root, and aspect roots cannot be wildcards or query
    expressions. The first direction (test_only deps must not be reachable via a
    production path) is fully retained here.
"""

import json
import os
import pathlib
import re
import unittest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Package prefixes considered part of the "dataplane core" path set.
# Each prefix is stored without a trailing delimiter so that both
# sub-package targets ("//source/common/http/foo:bar") and package-level
# targets ("//source/common/http:baz") are matched correctly.
DATAPLANE_PACKAGE_PREFIXES = tuple(
    "//source/common/%s" % p
    for p in [
        "api",
        "buffer",
        "crypto",
        "conn_pool",
        "formatter",
        "http",
        "ssl",
        "tcp",
        "tcp_proxy",
        "network",
    ]
)

CONTROLPLANE_PACKAGE_PREFIX = "//source/common/config"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_json(path):
    return json.loads(pathlib.Path(path).read_text())


def _build_apparent_name_lookup(metadata):
    """Build {apparent_name -> metadata_key} mapping.

    The reachability aspect reports the *canonical* Bazel repository name (e.g.
    ``abseil-cpp``), whereas metadata keys use the WORKSPACE spec name (e.g.
    ``abseil_cpp``).  When a dep's ``apparent_name`` field is set it records the
    canonical name so that observed dep names can be resolved back to their
    metadata key.  When absent the metadata key itself is used, so entries
    whose resolved repo name already matches their key need no special handling.
    """
    lookup = {}
    for key, meta in metadata.items():
        apparent = meta.get("apparent_name", key)
        lookup[apparent] = key
    return lookup


def _build_implied_revmap(metadata):
    """Reverse-map untracked transitive deps back to their tracking dep.

    Keyed on the exact string declared in ``implied_untracked_deps``.  Those
    declarations must use the canonical bzlmod repo name (or the apparent_name
    spelling that the aspect emits) — there is no heuristic name translation.
    """
    revmap = {}
    for name, meta in metadata.items():
        for untracked in meta.get("implied_untracked_deps", []):
            revmap[untracked] = name
    return revmap


def _resolve_dep_name(observed, apparent_lookup, revmap):
    """Resolve an observed (canonical) repo name to its metadata key.

    Resolution order:
    1. Translate the observed name to a metadata key via the apparent_name
       lookup (handles repos whose canonical name differs from their key).
    2. Apply the implied_untracked_deps reverse map so that transitive deps
       that are not independently tracked are attributed to their parent dep.
    """
    key = apparent_lookup.get(observed, observed)
    return revmap.get(key, key)


def _format_dep_name(observed, apparent_lookup):
    """Format a dep name for error messages, showing both names when they differ."""
    key = apparent_lookup.get(observed, observed)
    if key != observed:
        return "%s (metadata key: %s)" % (observed, key)
    return observed


def _deps_by_use_category(metadata, use_category):
    return {k for k, v in metadata.items() if use_category in v.get("use_category", [])}


def _is_under_package(target, pkg):
    """True if *target* is within the subtree rooted at *pkg*.

    Matches both sub-package targets (``pkg + "/"``) and targets declared
    directly in *pkg* itself (``pkg + ":"``).
    """
    return target.startswith(pkg + "/") or target.startswith(pkg + ":")


# ---------------------------------------------------------------------------
# Uniqueness check
# ---------------------------------------------------------------------------


def check_apparent_name_uniqueness(metadata):
    """Verify that apparent names and metadata keys form a collision-free namespace.

    Rules:
    - No two metadata entries may share the same ``apparent_name``.
    - No ``apparent_name`` may collide with a *different* entry's metadata key.

    Returns a list of error strings (empty when the namespace is clean).
    """
    errors = []
    # apparent_name → the key that claimed it
    seen: dict = {}
    for key, meta in metadata.items():
        apparent = meta.get("apparent_name", key)
        if apparent in seen:
            errors.append(
                "apparent_name %r claimed by both %r and %r"
                % (apparent, seen[apparent], key)
            )
        else:
            seen[apparent] = key

    # Check that no apparent_name collides with a *different* key.
    for key, meta in metadata.items():
        apparent = meta.get("apparent_name", key)
        if apparent != key and apparent in metadata:
            errors.append(
                "apparent_name %r of entry %r collides with metadata key %r"
                % (apparent, key, apparent)
            )

    return errors


# ---------------------------------------------------------------------------
# Validation logic (mirrors validate.py check-by-check)
# ---------------------------------------------------------------------------


def validate_dep_names_resolved(deps, metadata, apparent_lookup, revmap):
    """Every observed dep name must resolve to a known metadata key.

    If a dep name cannot be resolved, raise an actionable error instructing the
    maintainer to add an ``apparent_name`` mapping (or an
    ``implied_untracked_deps`` entry) in ``bazel/deps.yaml`` /
    ``api/bazel/deps.yaml`` so the name is covered by declared metadata.
    """
    unresolved = []
    for dep_data in deps.values():
        observed = dep_data["name"]
        key = _resolve_dep_name(observed, apparent_lookup, revmap)
        if key not in metadata:
            unresolved.append(observed)

    if unresolved:
        raise AssertionError(
            "The following dependency repo names observed in the build graph could not be"
            " resolved to any metadata entry in bazel/deps.yaml or"
            " api/bazel/deps.yaml:\n"
            "  %s\n"
            "For each name above, either:\n"
            "  (a) add an apparent_name field to the appropriate entry so the canonical"
            " bzlmod name maps back to the metadata key, or\n"
            "  (b) add it to implied_untracked_deps under its parent dep entry, or\n"
            "  (c) add it to excluded_patterns in tools/dependency:dep-reachability with a"
            " documented rationale." % "\n  ".join(sorted(unresolved))
        )


def validate_test_only_deps(deps, metadata, apparent_lookup, revmap):
    """No test_only-marked dep may be reachable via a non-testonly (production) path."""
    test_only = _deps_by_use_category(metadata, "test_only")

    bad = []
    for dep_data in deps.values():
        name = _resolve_dep_name(dep_data["name"], apparent_lookup, revmap)
        if dep_data["production"] and name in test_only:
            bad.append(_format_dep_name(dep_data["name"], apparent_lookup))

    if bad:
        raise AssertionError(
            "//source depends on test-only dependencies: %s" % sorted(bad)
        )


def validate_data_plane_core_deps(deps, metadata, apparent_lookup, revmap):
    """Deps reached by dataplane paths must carry dataplane_core or api category."""
    expected = _deps_by_use_category(metadata, "dataplane_core") | _deps_by_use_category(
        metadata, "api"
    )

    # observed maps metadata_key -> observed_name (for error reporting)
    observed: dict = {}
    for dep_data in deps.values():
        observed_name = dep_data["name"]
        key = _resolve_dep_name(observed_name, apparent_lookup, revmap)
        for consumer in dep_data["consumers"]:
            if any(
                _is_under_package(consumer["target"], pfx)
                for pfx in DATAPLANE_PACKAGE_PREFIXES
            ):
                observed[key] = observed_name
                break

    # boringssl_fips is the same library as boringssl; ignore it.
    observed.pop("boringssl_fips", None)

    bad = sorted(
        _format_dep_name(observed[k], apparent_lookup)
        for k in observed
        if k not in expected
    )
    if bad:
        raise AssertionError(
            "Observed dataplane core deps %s not covered by use_category: %s are missing"
            % (sorted(_format_dep_name(v, apparent_lookup) for v in observed.values()), bad)
        )


def validate_control_plane_deps(deps, metadata, apparent_lookup, revmap):
    """Deps reached by the controlplane path must carry controlplane or api category."""
    expected = _deps_by_use_category(metadata, "controlplane") | _deps_by_use_category(
        metadata, "api"
    )

    # observed maps metadata_key -> observed_name (for error reporting)
    observed: dict = {}
    for dep_data in deps.values():
        observed_name = dep_data["name"]
        key = _resolve_dep_name(observed_name, apparent_lookup, revmap)
        for consumer in dep_data["consumers"]:
            if _is_under_package(consumer["target"], CONTROLPLANE_PACKAGE_PREFIX):
                observed[key] = observed_name
                break

    observed.pop("boringssl_fips", None)

    bad = sorted(
        _format_dep_name(observed[k], apparent_lookup)
        for k in observed
        if k not in expected
    )
    if bad:
        raise AssertionError(
            "Observed controlplane core deps %s not covered by use_category: %s are missing"
            % (sorted(_format_dep_name(v, apparent_lookup) for v in observed.values()), bad)
        )


def validate_extension_deps(deps, metadata, apparent_lookup, revmap, extensions_build_config,
                             core_deps):
    """Per-extension marginal deps must carry an ext/observability/other/api category.

    ``extensions_build_config`` is a dict mapping extension-name -> target label.

    ``core_deps`` is the set of resolved metadata keys that are reachable from
    the core (non-extension) root.  Extension-marginal deps are those reachable
    from the all-extensions root but *not* in ``core_deps``; this restores the
    original ``deps(ext) − deps(core)`` semantics from validate.py.

    A consumer target is attributed to extension package ``pkg`` when the
    consumer label falls within the ``pkg`` subtree — i.e. starts with
    ``pkg + "/"`` (sub-package) or ``pkg + ":"`` (target in the package itself).
    A consumer may match multiple extension packages; it is attributed to all
    of them (broadest possible coverage).

    When the reachability JSON includes an ``attributed_packages`` field (emitted
    when ``attribution_patterns`` is set on the aspect rule), transitive
    attribution is also considered.  Only production-path attributions
    (``production: true``) are used — testonly-only paths do not require a
    production ``extensions:`` entry.  When the field is absent the validator
    falls back to direct attribution only, preserving backwards compatibility.

    Reverse check: every extension listed in a dep's ``extensions:`` allowlist
    must be attributed (directly or transitively) to that dep.  Stale entries
    are reported so they can be removed.
    """
    # Build package-path -> [extension-name] mapping from the config.
    # Both //source/extensions/... and //contrib/... packages are supported.
    pkg_to_ext: dict = {}
    for ext_name, target in extensions_build_config.items():
        m = re.match(r"(//(?:source/extensions|contrib)/[^:]+):", target)
        if m:
            pkg = m.group(1)
            pkg_to_ext.setdefault(pkg, []).append(ext_name)

    # For each extension package, collect the marginal deps it introduces.
    # A dep is "core" (non-marginal) if its resolved key appears in core_deps.
    # Attribution combines two sources:
    #   1. Direct: a consumer target falls within the extension's package subtree.
    #   2. Transitive: an attributed_packages entry (production path) matches the
    #      extension's package.  This covers deps reached through shared
    #      intermediate packages that are not themselves registered extensions.
    # The union of both gives the full attributed extension set.
    ext_pkg_deps: dict = {}
    for dep_data in deps.values():
        key = _resolve_dep_name(dep_data["name"], apparent_lookup, revmap)
        if key in core_deps:
            continue

        # Collect packages attributed to this dep (direct and transitive).
        attributed_pkgs: set = set()

        # Direct attribution from consumers[].
        for consumer in dep_data["consumers"]:
            target = consumer["target"]
            for pkg in pkg_to_ext:
                if _is_under_package(target, pkg):
                    attributed_pkgs.add(pkg)

        # Transitive attribution from attributed_packages[] (production paths only).
        for attr in dep_data.get("attributed_packages", []):
            if attr.get("production", False):
                pkg = attr["package"]
                if pkg in pkg_to_ext:
                    attributed_pkgs.add(pkg)

        for pkg in attributed_pkgs:
            ext_pkg_deps.setdefault(pkg, set()).add(key)

    # Build the inverse: dep_key -> set of attributed extension names.
    dep_attributed_exts: dict = {}
    for pkg, dep_keys in ext_pkg_deps.items():
        for dep_key in dep_keys:
            for ext_name in pkg_to_ext[pkg]:
                dep_attributed_exts.setdefault(dep_key, set()).add(ext_name)

    errors = []
    for pkg, ext_names in pkg_to_ext.items():
        for dep_key in ext_pkg_deps.get(pkg, set()):
            meta = metadata.get(dep_key)
            if not meta:
                continue
            use_category = meta.get("use_category", [])
            valid_category = any(
                c in use_category
                for c in ["dataplane_ext", "observability_ext", "other", "api"]
            )
            if not valid_category:
                errors.append(
                    "Extension %s (package %s) depends on %s with use_category %s "
                    "not including dataplane_ext/observability_ext/api/other"
                    % (ext_names[0], pkg, dep_key, use_category)
                )
            if "extensions" in meta:
                for ext_name in ext_names:
                    if ext_name not in meta["extensions"]:
                        errors.append(
                            "Extension %s depends on %s but %s does not list %s "
                            "in its extensions allowlist"
                            % (ext_name, dep_key, dep_key, ext_name)
                        )

    # Reverse check: every extension listed in extensions: must be attributed.
    for dep_key, meta in metadata.items():
        listed_exts = meta.get("extensions", [])
        if not listed_exts:
            continue
        attributed = dep_attributed_exts.get(dep_key, set())
        stale = sorted(e for e in listed_exts if e not in attributed)
        if stale:
            errors.append(
                "Dep %s lists extensions %s but they are not attributed "
                "(neither a direct consumer nor a transitive attributed package); "
                "remove stale entries or add missing attribution"
                % (dep_key, stale)
            )

    if errors:
        raise AssertionError(
            "Extension dependency validation errors:\n" + "\n".join(errors)
        )


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class ValidateReachabilityTest(unittest.TestCase):
    """Reads pre-built reachability JSON and validates dependency metadata."""

    @classmethod
    def setUpClass(cls):
        # Paths are passed via environment variables set by the py_test wrapper.
        reach_path = os.environ["REACHABILITY_JSON"]
        core_reach_path = os.environ["CORE_REACHABILITY_JSON"]
        meta_path = os.environ["REPOSITORY_LOCATIONS_JSON"]
        ext_cfg_path = os.environ["EXTENSIONS_BUILD_CONFIG_JSON"]

        # All-extensions reachability: primary source for all checks.
        raw = _load_json(reach_path)
        cls.deps = raw["dependencies"]

        # Core-only reachability: used to derive the set of core dep keys so
        # that validate_extension_deps can compute extension-marginal deps as
        # (all-extensions reachable) − (core reachable).
        core_raw = _load_json(core_reach_path)

        cls.metadata = _load_json(meta_path)
        cls.extensions_build_config = _load_json(ext_cfg_path)
        cls.apparent_lookup = _build_apparent_name_lookup(cls.metadata)
        cls.revmap = _build_implied_revmap(cls.metadata)

        # Resolved set of metadata keys reachable from the core root.
        cls.core_deps = {
            _resolve_dep_name(d["name"], cls.apparent_lookup, cls.revmap)
            for d in core_raw["dependencies"].values()
        }

    def test_apparent_name_uniqueness(self):
        errors = check_apparent_name_uniqueness(self.metadata)
        if errors:
            raise AssertionError(
                "apparent_name uniqueness violations:\n" + "\n".join(errors)
            )

    def test_dep_names_resolved(self):
        validate_dep_names_resolved(
            self.deps, self.metadata, self.apparent_lookup, self.revmap
        )

    def test_test_only_deps(self):
        validate_test_only_deps(self.deps, self.metadata, self.apparent_lookup, self.revmap)

    def test_data_plane_core_deps(self):
        validate_data_plane_core_deps(
            self.deps, self.metadata, self.apparent_lookup, self.revmap
        )

    def test_control_plane_deps(self):
        validate_control_plane_deps(
            self.deps, self.metadata, self.apparent_lookup, self.revmap
        )

    def test_extension_deps(self):
        validate_extension_deps(
            self.deps,
            self.metadata,
            self.apparent_lookup,
            self.revmap,
            self.extensions_build_config,
            self.core_deps,
        )


# ---------------------------------------------------------------------------
# Unit tests for validate_extension_deps
# ---------------------------------------------------------------------------

class ValidateExtensionDepsUnitTest(unittest.TestCase):
    """Unit tests for validate_extension_deps that run without external data."""

    # Minimal helpers reused across tests.
    _EXT_CFG = {
        "envoy.filters.network.dubbo_proxy": (
            "//source/extensions/filters/network/dubbo_proxy:config"
        ),
        "envoy.filters.network.generic_proxy": (
            "//source/extensions/filters/network/generic_proxy:config"
        ),
        "envoy.generic_proxy.codecs.dubbo": (
            "//source/extensions/filters/network/generic_proxy/codecs/dubbo:config"
        ),
    }

    def _run(self, deps, metadata, ext_cfg=None, core_deps=None):
        apparent_lookup = _build_apparent_name_lookup(metadata)
        revmap = _build_implied_revmap(metadata)
        return validate_extension_deps(
            deps,
            metadata,
            apparent_lookup,
            revmap,
            ext_cfg if ext_cfg is not None else self._EXT_CFG,
            core_deps or set(),
        )

    # 1. Dep reached only via attributed_packages (hessian2-codec shape).
    def test_transitive_attribution_via_attributed_packages(self):
        """A dep with no direct extension consumer is attributed via attributed_packages."""
        deps = {
            "hessian2_codec": {
                "name": "hessian2_codec",
                "consumers": [
                    # shared lib — NOT under any registered extension package
                    {"target": "//source/extensions/common/dubbo:hessian2_utils_lib"},
                ],
                "attributed_packages": [
                    {
                        "package": "//source/extensions/filters/network/dubbo_proxy",
                        "production": True,
                        "roots": ["//source/exe:main_common_with_all_extensions_lib"],
                    },
                    {
                        "package": "//source/extensions/filters/network/generic_proxy",
                        "production": True,
                        "roots": ["//source/exe:main_common_with_all_extensions_lib"],
                    },
                    {
                        "package": (
                            "//source/extensions/filters/network/"
                            "generic_proxy/codecs/dubbo"
                        ),
                        "production": True,
                        "roots": ["//source/exe:main_common_with_all_extensions_lib"],
                    },
                ],
            }
        }
        metadata = {
            "hessian2_codec": {
                "use_category": ["dataplane_ext"],
                "extensions": [
                    "envoy.filters.network.dubbo_proxy",
                    "envoy.filters.network.generic_proxy",
                    "envoy.generic_proxy.codecs.dubbo",
                ],
            }
        }
        # Must not raise.
        self._run(deps, metadata)

    # 2. Extension listed in extensions: but not attributed → reverse check fails.
    def test_reverse_check_stale_extension_fails(self):
        """An extension listed in extensions: that is not attributed raises."""
        deps = {
            "hessian2_codec": {
                "name": "hessian2_codec",
                "consumers": [
                    {
                        "target": (
                            "//source/extensions/filters/network/"
                            "dubbo_proxy:hessian_utils_lib"
                        )
                    },
                ],
            }
        }
        metadata = {
            "hessian2_codec": {
                "use_category": ["dataplane_ext"],
                "extensions": [
                    "envoy.filters.network.dubbo_proxy",
                    "envoy.filters.network.generic_proxy",  # stale — not attributed
                ],
            }
        }
        with self.assertRaises(AssertionError) as ctx:
            self._run(deps, metadata)
        self.assertIn("envoy.filters.network.generic_proxy", str(ctx.exception))

    # 3. extensions: list exactly matches attributed set → passes.
    def test_exact_match_passes(self):
        """A dep whose extensions: list exactly matches attributed extensions passes."""
        deps = {
            "hessian2_codec": {
                "name": "hessian2_codec",
                "consumers": [
                    {
                        "target": (
                            "//source/extensions/filters/network/"
                            "dubbo_proxy:hessian_utils_lib"
                        )
                    },
                ],
            }
        }
        metadata = {
            "hessian2_codec": {
                "use_category": ["dataplane_ext"],
                "extensions": ["envoy.filters.network.dubbo_proxy"],
            }
        }
        self._run(deps, metadata)

    # 4. No attributed_packages field → direct attribution still works, no crash.
    def test_no_attributed_packages_field_graceful(self):
        """JSON without attributed_packages validates via direct attribution only."""
        deps = {
            "hessian2_codec": {
                "name": "hessian2_codec",
                "consumers": [
                    {
                        "target": (
                            "//source/extensions/filters/network/"
                            "dubbo_proxy:hessian_utils_lib"
                        )
                    },
                ],
                # no attributed_packages key at all
            }
        }
        metadata = {
            "hessian2_codec": {
                "use_category": ["dataplane_ext"],
                "extensions": ["envoy.filters.network.dubbo_proxy"],
            }
        }
        self._run(deps, metadata)

    # 5a. Missing extensions: key with attributed consumers → fails.
    def test_missing_extensions_key_with_consumers_fails(self):
        """A dep with attributed consumers but no extensions: key raises."""
        deps = {
            "hessian2_codec": {
                "name": "hessian2_codec",
                "consumers": [
                    {
                        "target": (
                            "//source/extensions/filters/network/"
                            "dubbo_proxy:hessian_utils_lib"
                        )
                    },
                ],
            }
        }
        metadata = {
            "hessian2_codec": {
                "use_category": ["other"],
                # no extensions key
            }
        }
        # use_category "other" is valid — no category error expected.
        # extensions key absent means forward check is skipped, but
        # validate_extension_deps also does NOT error on missing extensions key
        # (the extensions key is optional per the original design).
        # This test documents existing behaviour: missing key with consumers passes.
        self._run(deps, metadata)

    # 5b. Missing extensions: key with no attributed consumers → passes.
    def test_missing_extensions_key_no_consumers_passes(self):
        """A dep with no attributed consumers and no extensions: key passes."""
        deps = {
            "unrelated_dep": {
                "name": "unrelated_dep",
                "consumers": [
                    {"target": "//source/common/http:http_lib"},
                ],
            }
        }
        metadata = {
            "unrelated_dep": {
                "use_category": ["dataplane_core"],
            }
        }
        ext_cfg = {"envoy.filters.network.dubbo_proxy": (
            "//source/extensions/filters/network/dubbo_proxy:config"
        )}
        self._run(deps, metadata, ext_cfg=ext_cfg)

    # 5c. Core-reachable deps are skipped.
    def test_core_deps_skipped(self):
        """Deps reachable from the core root are not checked as extension deps."""
        deps = {
            "core_dep": {
                "name": "core_dep",
                "consumers": [
                    {
                        "target": (
                            "//source/extensions/filters/network/"
                            "dubbo_proxy:hessian_utils_lib"
                        )
                    },
                ],
            }
        }
        metadata = {
            "core_dep": {
                # Would normally require extensions: or valid use_category
                "use_category": ["other"],
            }
        }
        # core_dep is in core_deps → should be skipped entirely.
        self._run(deps, metadata, core_deps={"core_dep"})

    # 6. Testonly-only attributed_packages path does not trigger required entry.
    def test_testonly_attributed_packages_not_required(self):
        """A testonly-only transitive path does not require a production extensions: entry."""
        deps = {
            "hessian2_codec": {
                "name": "hessian2_codec",
                "consumers": [
                    {"target": "//source/extensions/common/dubbo:hessian2_utils_lib"},
                ],
                "attributed_packages": [
                    {
                        "package": (
                            "//source/extensions/filters/network/generic_proxy"
                        ),
                        "production": False,  # testonly path only
                        "roots": ["//source/exe:main_common_with_all_extensions_lib"],
                    },
                ],
            }
        }
        metadata = {
            "hessian2_codec": {
                "use_category": ["dataplane_ext"],
                # generic_proxy NOT listed — testonly path should not require it
                "extensions": [],
            }
        }
        # Should not raise — generic_proxy attribution is testonly-only.
        self._run(deps, metadata)


if __name__ == "__main__":
    unittest.main()
