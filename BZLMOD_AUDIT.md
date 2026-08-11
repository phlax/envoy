# Audit: `bzlmod-envoy` ↔ `envoyproxy/envoy:main` — discretely landable changes

Audit of the full diff between `bzlmod-envoy` (branch head `06eaf80c8f`) and `main`
(merge-base `6d396b91b0`, 3 commits behind current `main`), classifying every change
against three criteria:

- **works in WORKSPACE** (does not depend on bzlmod being enabled)
- **can be landed discretely** (single-concern PR, justifiable on its own merits)
- **does not require further thought/testing** (mechanical, defensive, or already dual-mode)

Changes meeting all three criteria are listed in [Section 1](#1-landable-now).
[Section 2](#2-landable-as-mechanical-rename-prs) lists dep renames that are landable
but need a mechanical WORKSPACE-side companion change (precedented: phlax/envoy#43254,
phlax/envoy#43265, phlax/envoy#43272, phlax/envoy#42943). Sections 3–4 enumerate the
remainder for completeness (needs-thought / bzlmod-only).

## Branch shape

The branch is 3 commits:

| Commit | Subject | Notes |
|---|---|---|
| `06eaf80c8f` | bazel: Enable bzlmod | The big one — deletes WORKSPACE, flips `.bazelrc`, MODULE.bazel(.lock)s, patch deletions. **Also flattens the dual-mode `select()`s introduced by the commit below into bzlmod-only labels.** |
| `524b5c40ea` | bazel: Add compatibility stubs for bzlmod | Almost entirely the landable class — dual-mode runfiles handling, `//bazel:bzlmod_mode` config setting + `select()`-guarded deps. |
| `80e6c0d371` | docs: Add bzlmod support | `docs/MODULE.bazel` only — bzlmod-only. |

> **Key extraction note:** for several files (e.g. `source/common/event/BUILD`,
> `source/extensions/filters/common/lua/BUILD`) the *branch tip* state is bzlmod-only
> (`@libevent`, `@luajit` directly), but the *intermediate commit* `524b5c40ea` contains
> the dual-mode form:
>
> ```python
> deps = select({
>     "//bazel:bzlmod_mode": ["@libevent"],
>     "//conditions:default": ["//bazel/foreign_cc:event"],
> }),
> ```
>
> When landing, cherry-pick from `524b5c40ea`, not the tip.

---

## 1. Landable now

Everything here works under WORKSPACE, is single-concern, and needs no design work.

### 1.1 Dual-mode runfiles / workspace-name handling (from `524b5c40ea`)

All of these try the WORKSPACE name first (or detect which layout exists) and only fall
back to bzlmod names (`_main`, `+` canonical suffix), so they are no-ops under WORKSPACE.

| File | Change |
|---|---|
| `test/test_common/environment.cc` | `runfilesDirectory()`: try apparent name, then canonical `workspace+`, then `$TEST_WORKSPACE`; `runfilesPath()`: try `_main` then `envoy`, verifying existence, with old behaviour as fallback |
| `test/server/config_validation/server_test.cc` | Use `runfilesDirectory() + "/test/..."` instead of hardcoding the `envoy` workspace name — defers detection to the helper above |
| `test/extensions/common/aws/signers/sigv4_signer_corpus_test.cc`, `sigv4a_signer_corpus_test.cc` | `awsTestdataDir()` helper globs `external/` for any `aws-c-auth-testdata*` variant, falls back to the plain WORKSPACE name |
| `test/common/runtime/filesystem_setup.sh` | Detect `${TEST_SRCDIR}/_main` vs `${TEST_SRCDIR}/envoy`, error if neither |
| `test/exe/fips_check.sh` | Same dual-mode detection |
| `test/integration/hotrestart_test.sh` | Dual-mode detection, `ENVOY_SRCDIR` used consistently throughout |
| `test/integration/run_envoy_test.sh` | Dual-mode detection |
| `test/integration/sds_dynamic_key_rotation_setup.sh` | Dual-mode detection |
| `test/integration/test_utility.sh` | Dual-mode detection |
| `test/integration/admin_html/test_server_test.sh` | Dual-mode detection |
| `test/tools/router_check/test/route_tests.sh` | Dual-mode detection |
| `test/extensions/filters/network/thrift_proxy/driver/generate_fixture.sh` | Dual-mode detection with clear error message |

> **Caveat noted in the tracking issue (Stage 2):** this workspace-name detection is
> currently duplicated per-file. It works and is landable as-is, but the issue calls for
> consolidating it into one canonical helper per language before the final flip. Landing
> the per-file form now does not block that consolidation — but if the consolidation is
> imminent, land the helper first and convert these files to it in the same sweep.
> Either way the *behaviour* is WORKSPACE-safe and discrete.

### 1.2 `//bazel:bzlmod_mode` compat flag + `select()`-guarded deps (from `524b5c40ea`)

| File | Change |
|---|---|
| `bazel/BUILD` | Adds `bool_flag` `enable_bzlmod` (default `False`) and `config_setting` `bzlmod_mode` — inert under WORKSPACE |
| `source/common/event/BUILD` | `//bazel/foreign_cc:event` vs `@libevent` via `select()` on `bzlmod_mode` |
| `source/common/filesystem/BUILD` | Same pattern |
| `source/extensions/filters/common/lua/BUILD` | `//bazel/foreign_cc:luajit` vs `@luajit` via `select()` |
| `source/extensions/geoip_providers/maxmind/BUILD` | Same pattern |
| `tools/type_whisperer/file_descriptor_set_text.bzl`, `type_database.bzl` | `_normalize_workspace_name()` strips `~`/`+` canonical suffixes and handles `_main`; no behaviour change under WORKSPACE |

### 1.3 Python / tooling fixes

| File | Change |
|---|---|
| `api/tools/generate_listeners_test.py`, `api/tools/tap2pcap_test.py` | Replace TEST_SRCDIR workspace-name probing with `os.path.dirname(os.path.abspath(__file__))` — mode-agnostic and simpler |
| `test/config_test/static_config_validation.py` | Skip non-YAML files; tolerate `yaml.parser.ParserError` — robustness fix |
| `tools/api_versioning/generate_api_version_header.py` | Add missing `#!/usr/bin/env python` shebang |
| `tools/base/requirements.txt` | Add `wheel==0.45.1` (hash-pinned) |
| `tools/spelling/spelling_dictionary.txt` | Add `bzlmod`, `hardcode`, `workspaces` |

### 1.4 Small build/dep fixes

| File | Change |
|---|---|
| `contrib/golang/filters/http/test/test_data/go.mod`, `contrib/golang/router/cluster_specifier/test/test_data/simple/go.mod` | Routine `github.com/cncf/xds/go` bump (`20251110…` → `20251210…`) |
| `source/extensions/dynamic_modules/sdk/rust/Cargo.toml` + `Cargo.lock` | Pin `log = "=0.4.27"` |
| `bazel/external/cargo/Cargo.toml`, `Cargo.raze.lock`, `crates.bzl` | Pin `protobuf = "=2.24.1"`; raze lock header; `crates.bzl` returns repo struct |
| `test/extensions/dynamic_modules/stat_sink/BUILD` | Add missing `//source/extensions/filters/http/dynamic_modules:abi_impl` dep |
| `test/extensions/dynamic_modules/test_data/rust/*.rs`, `source/extensions/dynamic_modules/sdk/rust/src/*.rs` | Formatting/line-wrap only (rustfmt), no logic change |
| `tools/testdata/protoxform/envoy/v2/BUILD` | Dep reordering only |

### 1.5 CI / format misc

| File | Change |
|---|---|
| `ci/format_pre.sh` | Add `':!MODULE.bazel'` to a git-grep exclusion list — harmless under WORKSPACE |
| `mobile/tools/check_format.sh` | Remove obsolete per-file exclusions — the files are format-clean either way |

### 1.6 Patch deletions that pair with WORKSPACE-valid version bumps

These patches become unnecessary because the fix is in a newer upstream version that can
be taken under WORKSPACE too. Each lands as "bump dep X + drop patch" (precedent: the
protoc prebuilt toolchain change, envoyproxy/envoy#46568):

| Patch | Pairing |
|---|---|
| `bazel/pgv.patch` | Repo-rename-only patch; drop with the rename (Section 2) |
| `bazel/abseil.patch` | Version bump obsoletes it |
| `bazel/proto-field-extraction-protobuf-v35.patch` | Fix present in bumped version |
| `bazel/proto_processing_lib.patch` | Fix present in bumped version |
| `bazel/com_google_protoconverter.patch` | Fix present in bumped version |
| `bazel/emsdk.patch` | emsdk 4.0.6 → 4.0.23 bump obsoletes it |

Safe minor version bumps landable on their own: `aspect_bazel_lib` 2.21.2 → 2.22.0,
`emsdk` 4.0.6 → 4.0.23, `envoy_toolshed` 0.4.2 → 0.4.5.

---

## 2. Landable as mechanical rename PRs

Pure dependency renames to bzlmod-aligned (BCR) names. Each works under WORKSPACE
**provided the same PR renames the repo in `bazel/repository_locations.bzl` /
`bazel/repositories.bzl`** (and rule files that reference it). This is exactly the
Stage-1 "continue dep renames" class from the tracker, with existing precedent
(phlax/envoy#43254, #43265, #43272, #42943). Mechanical, CI-validated, but each rename
PR touches the WORKSPACE dep layer, so they are listed separately from Section 1.

| Old name | New (BCR-aligned) name | Notable referencing files |
|---|---|---|
| `com_google_googleapis` | `googleapis` | `api/bazel/api_build_system.bzl`, `bazel/envoy_internal.bzl`, `envoy/config/BUILD`, `api/envoy/config/rbac/v{2,3}/BUILD`, `api/envoy/extensions/rate_limit_descriptors/expr/v3/BUILD`, `tools/protoprint/BUILD` |
| `com_github_grpc_grpc` | `grpc` | `api/bazel/api_build_system.bzl`, `bazel/envoy_internal.bzl`, `tools/protoprint/BUILD` |
| `grpc_httpjson_transcoding` | `grpc-httpjson-transcoding` | `bazel/envoy_internal.bzl` |
| `proxy_wasm_cpp_host` | `proxy-wasm-cpp-host` | wasm runtime BUILD files (7 files) |
| `proxy_wasm_cpp_sdk` | `proxy-wasm-cpp-sdk` | wasm test_data BUILD files |
| `proxy_wasm_rust_sdk` | `proxy-wasm-rust-sdk` | wasm test_data BUILD files (3 files) |
| `kafka_source` | `kafka_message` | `contrib/kafka/filters/network/source/BUILD` (2 genrules) |
| `bazel_gazelle` | `gazelle` | dep layer |
| `abseil_cpp` (rules refs) | `abseil-cpp` | dep layer |
| `c_ares` | `c-ares` | dep layer |
| `com_google_protobuf` (locations key) | `protobuf` | dep layer |
| `proto_converter` | `proto-converter` | dep layer |
| `proto_field_extraction` | `proto-field-extraction` | dep layer |
| `proto_processing` | `proto-processing` | dep layer |
| `confluentinc_librdkafka` | `librdkafka` | dep layer |
| `hessian2_codec` | `hessian2-codec` | dep layer |
| `sql_parser` | `sql-parser` | dep layer |
| `aws_c_auth_testdata` | `aws-c-auth-testdata` | dep layer + AWS corpus tests (Section 1.1 handles both) |
| `yaml_cpp` | `yaml-cpp` | dep layer |
| `msgpack_cxx` | `msgpack-cxx` | dep layer |
| `cel_spec` | `cel-spec` | dep layer |
| `zlib_ng` | `zlib-ng` | dep layer |
| `opentelemetry_cpp` | `opentelemetry-cpp` | dep layer |
| `vpp_vcl` | `vpp-vcl` | dep layer |
| `libprotobuf-mutator//:libprotobuf_mutator` | `@libprotobuf-mutator` (default target) | `test/fuzz/BUILD`, fuzz BUILD files |
| `bazel_compdb` | `bazel-compdb` | `tools/gen_compilation_database.py` |
| `robolectric` | `rules_robolectric` | `mobile/bazel/envoy_mobile_android_test.bzl` |

The branch's `bazel/repository_locations_aliases.bzl` (`MODULE_NAME_ALIASES`) records the
handful of names that intentionally *stay* different from the module name
(`benchmark`→`google_benchmark`, `buildtools`→`buildifier_prebuilt`, etc.) — useful as
the canonical rename checklist.

---

## 3. Needs thought (works or could work under WORKSPACE, but not "no further thought")

| Area | Files | Why it needs thought |
|---|---|---|
| Aspect-based deps mechanism | `tools/dependency/BUILD`, deleted `validate.py`/`validate_test.py`, new `validate_reachability_test.py` | Complete redesign using an `@envoy_toolshed//dependency:reachability.bzl` aspect; tracker explicitly calls this out as Stage 2 ("adapt for WORKSPACE") |
| Proto descriptor machinery | `bazel/envoy_build_system.bzl` (`envoy_proto_descriptor`), `api/bazel/cc_proto_descriptor_library/builddefs.bzl`, `tools/protoc/BUILD` | Refactor onto `@envoy_toolshed//toolchains:utils.bzl` helpers + dynamic include-path computation; plausible under WORKSPACE but needs testing |
| api_proto_plugin path handling | `tools/api_proto_plugin/plugin.bzl`, `utils.py`, `tools/proto_format/format_api.py`, `tools/proto_format/BUILD` | Repo-agnostic label parsing and `external/envoy_api~~`/`external/xds+` variants; dual-mode in intent but parsing-logic changes warrant test coverage |
| `tools/gen_compilation_database.py` | — | Mixes the `bazel-compdb` rename (Section 2) with `external/_main` handling; split before landing |
| Version *downgrades* forced by BCR lag | `c-ares` 1.34.8→1.34.6, `opentelemetry-cpp` 1.28.0→1.24.0, `perfetto` 57.2→53.0, `libevent` 2.2.2-alpha→2.1.12-stable, `qatlib`, `dd_trace_cpp`, `liburing`, `gperftools`, `thrift`, `rules_java`, `rules_fuzzing`, … | Not landable and not desirable — these are the Stage-0 "stage the newer version in the toolshed bazel-registry where BCR lags" cases; each needs a registry decision, not a main-branch change |
| Major upgrade | `rules_proto_grpc` 4.6.0 → 5.8.0 (+ `rules_proto_grpc_cpp` split) | Major-version jump; needs its own validation |
| `re2` bump | 2024-07-02 → 2025-08-12 | Landable in principle but a large jump; test before landing |
| nghttp2 patch deletions | `bazel/nghttp2*.patch` (3) | Likely obsoleted by nghttp2 1.66.0; verify fixes are upstream, then pair with a WORKSPACE bump |
| Removed deps | `dragonbox`, `fp16`, `simdutf`, `highway`, `fast_float`, `libpfm`, `dlb`, `elfutils`, … | Deletions tied to V8/other dep restructuring; each needs a "why is this safe under WORKSPACE" answer |
| `bazel/rules_rust.patch` update | — | Targets rules_rust 0.69.0; only lands with the corresponding rules_rust bump |
| `test/exe/build_id_test.sh`, `envoy_static_test.sh`, `pie_test.sh`, `version_out_test.sh` | — | Tip hardcodes `${TEST_SRCDIR}/_main`; trivially fixable to the dual-mode pattern of Section 1.1 — do that instead of landing as-is |
| `ci/docker-compose.yml` toolshed mount | — | Dev convenience (`../../toolshed:/toolshed`); harmless but probably not wanted upstream as-is |

---

## 4. bzlmod-only (do not land until the flip)

- `.bazelrc` flip (`--enable_bzlmod`, `--noenable_workspace`, registries, per-dep flags)
- `WORKSPACE` deletion; `MODULE.bazel` rewrite + `MODULE.bazel.lock` (root, docs, mobile, `bazel/tests/external`, `ci/osx-build-config`)
- `bazel/extensions.bzl`, `mobile/bazel/extensions.bzl` (module extensions)
- `bazel/repository_locations_aliases.bzl` (bzlmod alias map — though useful as a rename checklist, Section 2)
- Deletion of the WORKSPACE dep plumbing: `bazel/api_binding.bzl`, `api_repositories.bzl`, `bazel_deps.bzl`, `dependency_imports*.bzl`, `repositories_extra.bzl`, `python_dependencies.bzl`, `proto_toolchain.bzl`, `bazel/external/fips_build.bzl`
- The ~23 patch deletions where the dep moved to a BCR module that carries the patches (boringssl, grpc, protobuf, googletest, rules_*, toolchains_llvm, v8, qat*, thrift, icu, luajit, hyperscan/vectorscan, librdkafka, cel-cpp, …) and the deleted `bazel/external/*.BUILD` files whose content now lives in BCR modules (`boringssl_fips.BUILD`, `libprotobuf_mutator.BUILD`, `zlib_ng.BUILD`)
- `@envoy_toolshed++…+` canonical-path references: `compat/openssl/prefixer/BUILD`, `source/extensions/dynamic_modules/sdk/rust/BUILD` (llvm toolchain / sysroot aliases)
- `@boringssl` → `@boringssl-source` rename in `compat/openssl/` (name only exists under the bzlmod layout)
- `ci/do_ci.sh` `external/su-exec+` hardcoding, `--consistent_labels` query changes; `ci/mac_ci_steps.sh` `+envoy_build_config_ext+envoy_build_config` override
- `mobile/` migration: `MODULE.bazel` rewrite, `envoy_mobile_dependencies.bzl` gutting, deletion of `envoy_mobile_repositories.bzl` / `envoy_mobile_toolchains.bzl` / `android_configure.bzl` / mobile patches, `test_extensions.cc` include-path change
- `tools/code_format/BUILD` `@buildtools//buildifier` → `@buildifier_prebuilt//:buildifier`
- `docs/` migration: `docs/MODULE.bazel`, deletion of `docs/WORKSPACE` + `docs/bazel/repositories_extra.bzl`, `docs/.bazelrc`
- `bazel/all_repository_locations_test.sh` (new; assumes bzlmod layout)

---

## Suggested landing order

1. **Section 1.1 + 1.2** as one or two PRs — essentially re-land commit `524b5c40ea`
   ("bazel: Add compatibility stubs for bzlmod") on main, plus the dual-mode fix-ups for
   the four `test/exe/*.sh` scripts that the tip left hardcoded.
2. **Section 1.3–1.5** as tiny independent PRs (each is a one-liner-to-small fix).
3. **Section 1.6** version-bump+patch-drop PRs, one dep per PR.
4. **Section 2** rename PRs, grouped by dep (wasm trio first — repos already exist under
   both spellings; then kafka; then googleapis/grpc which touch the most files).
5. Section 3 items feed Stages 2–3 of the tracker and are out of scope for this audit's
   "land now" list.

Landing 1–4 removes roughly all of the non-`MODULE.bazel.lock`, non-patch-deletion bulk
from the migration diff, leaving the final flip PR at approximately: `.bazelrc` +
`MODULE.bazel(.lock)` + `bazel/extensions.bzl` + WORKSPACE-plumbing deletions + the
BCR-carried patch deletions.
