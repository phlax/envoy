#!/usr/bin/env python3
"""Tests for update_deps.py"""

import json
import os
import pathlib
import tempfile
import unittest
from contextlib import redirect_stderr
from io import StringIO

import yaml

def _yaml_load(text):
    return yaml.safe_load(text) or {}

def _yaml_dump(data, path):
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True))

from tools.dependency import update_deps


class ParseModuleBazelTest(unittest.TestCase):

    def _write(self, tmpdir, content):
        p = pathlib.Path(tmpdir) / "MODULE.bazel"
        p.write_text(content)
        return p

    def test_basic_dep(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write(
                td, 'bazel_dep(name = "abseil-cpp", version = "20260107.1")\n')
            deps = update_deps.parse_module_bazel(p)
        self.assertEqual(deps, {"abseil-cpp": "20260107.1"})

    def test_multiple_deps(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write(
                td,
                'bazel_dep(name = "abseil-cpp", version = "20260107.1")\n'
                'bazel_dep(name = "re2", version = "2025-08-12.bcr.1")\n',
            )
            deps = update_deps.parse_module_bazel(p)
        self.assertIn("abseil-cpp", deps)
        self.assertIn("re2", deps)
        self.assertEqual(deps["abseil-cpp"], "20260107.1")

    def test_dep_with_repo_name(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write(
                td,
                """
                bazel_dep(
                    name = "protobuf",
                    version = "35.1.bcr.envoy",
                    repo_name = "com_google_protobuf",
                )
                """,
            )
            deps = update_deps.parse_module_bazel(p)
        self.assertIn("protobuf", deps)
        self.assertEqual(deps["protobuf"], "35.1.bcr.envoy")

    def test_dev_dependency(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write(
                td,
                """
                bazel_dep(
                    name = "googletest",
                    version = "1.17.0",
                    dev_dependency = True,
                )
                """,
            )
            deps = update_deps.parse_module_bazel(p)
        self.assertIn("googletest", deps)


class ParseLockfileTest(unittest.TestCase):

    def _write_lock(self, tmpdir, data):
        p = pathlib.Path(tmpdir) / "MODULE.bazel.lock"
        p.write_text(json.dumps(data))
        return p

    def test_bcr_source_json_found(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_lock(
                td,
                {
                    "lockFileVersion": 1,
                    "registryFileHashes": {
                        "https://bcr.bazel.build/modules/abseil-cpp/20260107.1/source.json":
                        "abc123",
                    },
                    "selectedYankedVersions": {},
                    "moduleExtensions": {},
                },
            )
            src_map, ext_specs = update_deps.parse_lockfile(p)
        self.assertIn("abseil-cpp", src_map)
        self.assertEqual(
            src_map["abseil-cpp"],
            "https://bcr.bazel.build/modules/abseil-cpp/20260107.1/source.json",
        )

    def test_toolshed_source_json_found(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_lock(
                td,
                {
                    "lockFileVersion": 1,
                    "registryFileHashes": {
                        "https://raw.githubusercontent.com/envoyproxy/toolshed/abc123/"
                        "bazel-registry/modules/cel-cpp/0.14.0.envoy/source.json":
                        "deadbeef",
                    },
                    "selectedYankedVersions": {},
                    "moduleExtensions": {},
                },
            )
            src_map, _ext = update_deps.parse_lockfile(p)
        self.assertIn("cel-cpp", src_map)

    def test_extension_repo_specs(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._write_lock(
                td,
                {
                    "lockFileVersion": 1,
                    "registryFileHashes": {},
                    "selectedYankedVersions": {},
                    "moduleExtensions": {
                        "//bazel:extensions.bzl%envoy_dependencies_extension": {
                            "general": {
                                "generatedRepoSpecs": {
                                    "quiche": {
                                        "repoRuleId": "http_archive",
                                        "attributes": {
                                            "urls": [
                                                "https://github.com/google/quiche/archive/"
                                                "deadbeef.tar.gz"
                                            ],
                                            "version": "",
                                        },
                                    }
                                }
                            }
                        }
                    },
                },
            )
            _src_map, ext_specs = update_deps.parse_lockfile(p)
        self.assertIn("quiche", ext_specs)
        self.assertIn(
            "https://github.com/google/quiche/archive/deadbeef.tar.gz",
            ext_specs["quiche"]["urls"],
        )


class ParseRepositoryLocationsTest(unittest.TestCase):

    def test_basic_parse(self):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "repository_locations.bzl"
            p.write_text(
                'REPOSITORY_LOCATIONS_SPEC = dict(\n'
                '    quiche = dict(\n'
                '        version = "89d6d17edc0f0b79f38edf6fac9e5c8bf5f3cfd7",\n'
                '        sha256 = "abc",\n'
                '        urls = ["https://github.com/google/quiche/archive/{version}.tar.gz"],\n'
                '    ),\n'
                ')\n'
            )
            result = update_deps.parse_repository_locations(p)
        self.assertIn("quiche", result)
        self.assertEqual(
            result["quiche"]["version"], "89d6d17edc0f0b79f38edf6fac9e5c8bf5f3cfd7")
        self.assertIn(
            "https://github.com/google/quiche/archive/"
            "89d6d17edc0f0b79f38edf6fac9e5c8bf5f3cfd7.tar.gz",
            result["quiche"]["urls"],
        )

    def test_absent_file(self):
        result = update_deps.parse_repository_locations(pathlib.Path("/nonexistent.bzl"))
        self.assertEqual(result, {})

    def test_malformed_file_returns_empty_without_eval(self):
        with tempfile.TemporaryDirectory() as td:
            p = pathlib.Path(td) / "repository_locations.bzl"
            p.write_text('REPOSITORY_LOCATIONS_SPEC = dict(quiche = nope("boom"))\n')
            stderr = StringIO()
            with redirect_stderr(stderr):
                result = update_deps.parse_repository_locations(p)
        self.assertEqual(result, {})
        self.assertIn("failed to parse", stderr.getvalue())


class UpdateDepsYamlTest(unittest.TestCase):

    def _make_deps_file(self, tmpdir, content: dict) -> pathlib.Path:
        p = pathlib.Path(tmpdir) / "deps.yaml"
        _yaml_dump(content, p)
        return p

    def test_version_updated_from_module(self):
        with tempfile.TemporaryDirectory() as td:
            deps_path = self._make_deps_file(
                td,
                {"abseil-cpp": {
                    "project_name": "Abseil",
                    "project_desc": "Desc",
                    "project_url": "https://abseil.io",
                    "release_date": "2026-01-07",
                    "use_category": ["dataplane_core"],
                    "license": "Apache-2.0",
                    "license_url": "...",
                    "cpe": "N/A",
                }},
            )
            update_deps.update_deps_yaml(
                deps_path,
                module_deps={"abseil-cpp": "20260107.1"},
                source_json_map={},
                ext_repo_specs={},
                repo_locations={},
                fetch_urls=False,
                verbose=False,
            )
            result = _yaml_load(deps_path.read_text())
        self.assertEqual(result["abseil-cpp"]["version"], "20260107.1")
        # Existing metadata preserved
        self.assertEqual(result["abseil-cpp"]["project_name"], "Abseil")

    def test_missing_version_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            deps_path = self._make_deps_file(
                td,
                {"some-dep": {
                    "project_name": "SomeDep",
                    "project_desc": "Desc",
                    "project_url": "https://example.com",
                    "release_date": "2024-01-01",
                    "use_category": ["build"],
                    "license": "MIT",
                    "license_url": "...",
                    "cpe": "N/A",
                }},
            )
            # No version from MODULE.bazel, no version from repo_locations
            update_deps.update_deps_yaml(
                deps_path,
                module_deps={"some-dep": ""},
                source_json_map={},
                ext_repo_specs={},
                repo_locations={},
                fetch_urls=False,
                verbose=False,
            )
            result = _yaml_load(deps_path.read_text())
        self.assertEqual(result["some-dep"]["version"], update_deps.MISSING)

    def test_stub_created_for_new_dep(self):
        with tempfile.TemporaryDirectory() as td:
            deps_path = pathlib.Path(td) / "deps.yaml"
            # deps.yaml does not exist yet
            update_deps.update_deps_yaml(
                deps_path,
                module_deps={"new-dep": "1.2.3"},
                source_json_map={},
                ext_repo_specs={},
                repo_locations={},
                fetch_urls=False,
                verbose=False,
            )
            result = _yaml_load(deps_path.read_text())
        self.assertIn("new-dep", result)
        self.assertEqual(result["new-dep"]["version"], "1.2.3")
        self.assertEqual(result["new-dep"]["project_name"], update_deps.MISSING)
        self.assertIn(update_deps.MISSING, result["new-dep"]["use_category"])

    def test_url_from_repo_locations(self):
        with tempfile.TemporaryDirectory() as td:
            deps_path = self._make_deps_file(
                td,
                {"quiche": {
                    "project_name": "QUICHE",
                    "project_desc": "QUIC impl",
                    "project_url": "https://quiche.googlesource.com/quiche",
                    "release_date": "2024-01-01",
                    "use_category": ["dataplane_core"],
                    "license": "BSD-3-Clause",
                    "license_url": "...",
                    "cpe": "N/A",
                }},
            )
            update_deps.update_deps_yaml(
                deps_path,
                module_deps={},
                source_json_map={},
                ext_repo_specs={},
                repo_locations={
                    "quiche": {
                        "version": "89d6d17edc0f0b79f38edf6fac9e5c8bf5f3cfd7",
                        "urls": [
                            "https://github.com/google/quiche/archive/"
                            "89d6d17edc0f0b79f38edf6fac9e5c8bf5f3cfd7.tar.gz"
                        ],
                    }
                },
                fetch_urls=False,
                verbose=False,
            )
            result = _yaml_load(deps_path.read_text())
        self.assertEqual(
            result["quiche"]["version"], "89d6d17edc0f0b79f38edf6fac9e5c8bf5f3cfd7")
        self.assertIn(
            "https://github.com/google/quiche/archive/"
            "89d6d17edc0f0b79f38edf6fac9e5c8bf5f3cfd7.tar.gz",
            result["quiche"]["urls"],
        )

    def test_url_from_extension_repo_specs(self):
        with tempfile.TemporaryDirectory() as td:
            deps_path = self._make_deps_file(
                td,
                {"quiche": {
                    "project_name": "QUICHE",
                    "project_desc": "QUIC impl",
                    "project_url": "https://quiche.googlesource.com/quiche",
                    "release_date": "2024-01-01",
                    "use_category": ["dataplane_core"],
                    "license": "BSD-3-Clause",
                    "license_url": "...",
                    "cpe": "N/A",
                }},
            )
            update_deps.update_deps_yaml(
                deps_path,
                module_deps={},
                source_json_map={},
                ext_repo_specs={
                    "quiche": {
                        "version": "deadbeef",
                        "urls": ["https://github.com/google/quiche/archive/deadbeef.tar.gz"],
                    },
                    "system_python": {
                        "version": "3.11.0",
                        "urls": ["https://example.invalid/system_python.tar.gz"],
                    },
                },
                repo_locations={},
                fetch_urls=False,
                verbose=False,
            )
            result = _yaml_load(deps_path.read_text())
        self.assertEqual(result["quiche"]["version"], "deadbeef")
        self.assertEqual(
            result["quiche"]["urls"],
            ["https://github.com/google/quiche/archive/deadbeef.tar.gz"],
        )
        self.assertNotIn("system_python", result)

    def test_module_dep_takes_precedence_over_repo_locations(self):
        with tempfile.TemporaryDirectory() as td:
            deps_path = self._make_deps_file(
                td,
                {"googleapis": {
                    "project_name": "Google APIs",
                    "project_desc": "Desc",
                    "project_url": "https://example.com",
                    "release_date": "2024-01-01",
                    "use_category": ["build"],
                    "license": "Apache-2.0",
                    "license_url": "...",
                    "cpe": "N/A",
                }},
            )
            update_deps.update_deps_yaml(
                deps_path,
                module_deps={"googleapis": "module-version"},
                source_json_map={},
                ext_repo_specs={},
                repo_locations={
                    "googleapis": {
                        "version": "repo-version",
                        "urls": ["https://wrong.invalid/googleapis.tar.gz"],
                    },
                },
                fetch_urls=False,
                verbose=False,
            )
            result = _yaml_load(deps_path.read_text())
        self.assertEqual(result["googleapis"]["version"], "module-version")
        self.assertNotIn("urls", result["googleapis"])

    def test_idempotent(self):
        """Running twice with no dependency changes produces no diff."""
        with tempfile.TemporaryDirectory() as td:
            deps_path = pathlib.Path(td) / "deps.yaml"
            module_deps = {"my-dep": "2.0.0"}
            kwargs = dict(
                module_deps=module_deps,
                source_json_map={},
                ext_repo_specs={},
                repo_locations={},
                fetch_urls=False,
                verbose=False,
            )
            update_deps.update_deps_yaml(deps_path, **kwargs)
            content1 = deps_path.read_text()
            update_deps.update_deps_yaml(deps_path, **kwargs)
            content2 = deps_path.read_text()
        self.assertEqual(content1, content2)

    def test_url_from_lock_not_registry(self):
        """Fetched source.json data writes upstream archive URLs, never registry URLs."""
        with tempfile.TemporaryDirectory() as td:
            registry_dir = pathlib.Path(td) / "registry" / "modules" / "abseil-cpp" / "20260107.1"
            registry_dir.mkdir(parents=True)
            source_json = registry_dir / "source.json"
            upstream_url = (
                "https://github.com/abseil/abseil-cpp/releases/download/"
                "20260107.1/abseil-cpp-20260107.1.tar.gz"
            )
            source_json.write_text(json.dumps({"url": upstream_url}))
            lockfile = pathlib.Path(td) / "MODULE.bazel.lock"
            lockfile.write_text(
                json.dumps({
                    "lockFileVersion": 1,
                    "registryFileHashes": {
                        source_json.as_uri(): "abc123",
                    },
                    "selectedYankedVersions": {},
                    "moduleExtensions": {},
                }))
            source_json_map, _ext_specs = update_deps.parse_lockfile(lockfile)
            deps_path = self._make_deps_file(
                td,
                {"abseil-cpp": {
                    "project_name": "Abseil",
                    "project_desc": "Desc",
                    "project_url": "https://abseil.io",
                    "release_date": "2026-01-07",
                    "use_category": ["dataplane_core"],
                    "license": "Apache-2.0",
                    "license_url": "...",
                    "cpe": "N/A",
                }},
            )
            update_deps.update_deps_yaml(
                deps_path,
                module_deps={"abseil-cpp": "20260107.1"},
                source_json_map=source_json_map,
                ext_repo_specs={},
                repo_locations={},
                fetch_urls=True,
                verbose=False,
            )

            result = _yaml_load(deps_path.read_text())
        self.assertEqual(result["abseil-cpp"]["urls"], [upstream_url])
        for u in result["abseil-cpp"]["urls"]:
            self.assertNotIn("bcr.bazel.build", u)


class ResolvePathsTest(unittest.TestCase):

    def test_api_paths_resolve_from_workspace_root(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = pathlib.Path(td)
            args = update_deps.build_arg_parser().parse_args(["--module", "api/MODULE.bazel"])
            paths = update_deps.resolve_paths(args, workspace)
        self.assertEqual(paths[0], workspace / "api" / "MODULE.bazel")
        self.assertEqual(paths[1], workspace / "api" / "bazel" / "deps.yaml")
        self.assertEqual(paths[2], workspace / "api" / "MODULE.bazel.lock")
        self.assertEqual(
            paths[3],
            workspace / "api" / "bazel" / "repository_locations.bzl",
        )


class MainTest(unittest.TestCase):

    def test_main_requires_build_workspace_directory(self):
        old_workspace = os.environ.pop("BUILD_WORKSPACE_DIRECTORY", None)
        stderr = StringIO()
        try:
            with redirect_stderr(stderr):
                rc = update_deps.main(["--quiet"])
        finally:
            if old_workspace is not None:
                os.environ["BUILD_WORKSPACE_DIRECTORY"] = old_workspace
        self.assertEqual(rc, 1)
        self.assertIn("bazel run //tools/dependency:update_deps", stderr.getvalue())

    def test_main_updates_workspace_relative_paths(self):
        with tempfile.TemporaryDirectory() as td:
            workspace = pathlib.Path(td)
            (workspace / "bazel").mkdir()
            (workspace / "MODULE.bazel").write_text(
                'bazel_dep(name = "abseil-cpp", version = "20260107.1")\n')
            (workspace / "bazel" / "repository_locations.bzl").write_text(
                "REPOSITORY_LOCATIONS_SPEC = dict()\n")
            deps_path = workspace / "bazel" / "deps.yaml"
            deps_path.write_text(
                yaml.dump({
                    "abseil-cpp": {
                        "project_name": "Abseil",
                        "project_desc": "Desc",
                        "project_url": "https://abseil.io",
                        "release_date": "2026-01-07",
                        "use_category": ["dataplane_core"],
                        "license": "Apache-2.0",
                        "license_url": "...",
                        "cpe": "N/A",
                        "version": "old",
                    },
                },
                          default_flow_style=False,
                          sort_keys=False,
                          allow_unicode=True))
            old_workspace = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
            os.environ["BUILD_WORKSPACE_DIRECTORY"] = str(workspace)
            try:
                rc = update_deps.main(["--quiet"])
            finally:
                if old_workspace is None:
                    del os.environ["BUILD_WORKSPACE_DIRECTORY"]
                else:
                    os.environ["BUILD_WORKSPACE_DIRECTORY"] = old_workspace
            result = _yaml_load(deps_path.read_text())
        self.assertEqual(rc, 0)
        self.assertEqual(result["abseil-cpp"]["version"], "20260107.1")


if __name__ == "__main__":
    unittest.main()
