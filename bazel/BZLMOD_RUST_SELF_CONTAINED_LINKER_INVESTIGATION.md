# BZLMOD Rust self-contained linker investigation

## Summary

`rules_rust` does **not** emit `-Clink-self-contained` for this link. The only linker-selection inputs added by the Bazel toolchain path are `--codegen=linker=.../cc_wrapper.sh` and `--codegen=link-arg=-fuse-ld=lld`, where `-fuse-ld=lld` comes from `toolchains_llvm` and is forwarded by `rules_rust` into `rustc`.[^rr-rustc-link][^llvm-lld] The committed `bzlmod-envoy` branch and WORKSPACE `main` use materially the same LLVM-minimal/sysroot wiring, so that is **not** the branch-only delta.[^envoy-bzlmod-llvm][^envoy-main-llvm][^toolshed-llvm][^toolshed-sysroot] The source-level evidence also refutes the theory that the bzlmod `rust.toolchain(...)` tag drops `extra_rustc_flags` / `extra_exec_rustc_flags`: the extension forwards them all the way into the generated `rust_toolchain`, and `rules_rust` appends the command-line build-setting variants **after** the toolchain variants.[^rr-ext-forward][^rr-repos-forward][^rr-rustc-extra] The best fix for Envoy's migration is therefore to disable self-contained linking via the **exec build setting** `--@rules_rust//rust/settings:extra_exec_rustc_flags=-Clink-self-contained=no` (and only add the non-exec sibling if a target-config Rust link also needs it), not by changing LLVM wiring or `toolchain_linker_preference`.[^rr-settings-extra][^rr-rustc-extra][^rr-toolchain-pref]

## Reproduction

The failure under investigation is the user-supplied bzlmod build of `//test/config_test:config_test`, where a proc-macro crate (`yoke_derive`) is compiled on the exec platform with:

```text
--crate-type=proc-macro
--target=x86_64-unknown-linux-gnu
--codegen=linker=external/toolchains_llvm++llvm+llvm_toolchain/bin/cc_wrapper.sh
--codegen=link-arg=-fuse-ld=lld
...
error: the self-contained linker was requested, but it wasn't found in the target's sysroot, or in rustc's sysroot
```

In this environment I could not capture a fresh local `aquery` for that target because analysis currently stops earlier on Android SDK repository setup (`rules_android++android_sdk_repository_extension+androidsdk`). The current PR's failing GitHub Action visible from this checkout is also unrelated: CodeQL run `31366790357` fails on `No Android SDK apis found...`, not on the Rust linker error.[^codeql-android]

## Root cause analysis

### 1. The self-contained request is **not** emitted by `rules_rust`

`rules_rust` constructs the Rust link invocation in `rust/private/rustc.bzl`. When a crate is linked, it calls `get_linker_and_args()`, then emits `--codegen=linker=%s` and one `--codegen=link-arg=%s` per linker arg.[^rr-rustc-link] There is no `-Clink-self-contained` emission in that path.

The linker args themselves come from the resolved C++ toolchain. `toolchains_llvm` hardcodes `-fuse-ld=lld` in `toolchain/cc_toolchain_config.bzl`, and its tool paths make `gcc` be `cc_wrapper.sh` while `ld` is `ld.lld`.[^llvm-lld] That exactly matches the observed `rustc` command shape in the issue statement.

So the precise answer to "which flag is causing the issue?" is:

- the only relevant emitted linker-selection flag is `--codegen=link-arg=-fuse-ld=lld`, originating in `toolchains_llvm`.[^rr-rustc-link][^llvm-lld]
- the self-contained request itself is therefore coming from **rustc's own behavior for that target/linker combination**, not from an explicit `rules_rust`-emitted `-Clink-self-contained=...` flag.[^rr-rustc-link]

### 2. `toolchain_linker_preference=cc` did not help because the build was already using `cc`

`rules_rust` documents `toolchain_linker_preference` as:

- `rust`: use `rust_toolchain.linker`
- `cc`: use the configured `cc_toolchain`
- `none`: prefer `cc`, fall back to `rust` if no `cc_toolchain` is available.[^rr-toolchain-pref]

The toolchain implementation reads that setting and only overrides behavior if the build setting is not `none`.[^rr-toolchain-impl] The observed failing command already used the C++ toolchain path:

- `--codegen=linker=.../cc_wrapper.sh`
- `--codegen=link-arg=-fuse-ld=lld`

So forcing `--@rules_rust//rust/settings:toolchain_linker_preference=cc` was a no-op for this case: it preserved the same `cc_wrapper.sh` + `-fuse-ld=lld` combination.[^rr-toolchain-pref][^rr-toolchain-impl][^llvm-lld]

### 3. WORKSPACE and bzlmod use the same LLVM-minimal/sysroot mechanism

On Envoy `main`, WORKSPACE mode configures `llvm_toolchain(...)` with:

- the same `@llvm_minimal_linux_x64`, `@llvm_minimal_linux_arm64`, and `@llvm_minimal_macos_arm64` toolchain roots
- the same `@sysroot_linux_amd64//:sysroot` and `@sysroot_linux_arm64//:sysroot` sysroots.[^envoy-main-llvm]

On the bzlmod branch, `MODULE.bazel` configures the `llvm` extension with the same roots and sysroots.[^envoy-bzlmod-llvm]

And the toolshed bzlmod extensions are thin wrappers over the same setup functions:

- `llvm_minimal_extension` just calls `setup_llvm_minimal()`[^toolshed-llvm]
- `llvm_toolchain_alias_extension` creates `llvm_toolchain_llvm` from those same `llvm_minimal_*` repos[^toolshed-llvm]
- `sysroot_extension` just calls `setup_sysroots(...)`.[^toolshed-sysroot]

So the WORKSPACE-vs-bzlmod delta is **not** "different LLVM artifacts" or "different sysroot artifacts". The canonical repo names differ under bzlmod (`envoy_toolshed++...`, `toolchains_llvm++...`), but the configured roots/sysroots are the same artifacts wired through different registration machinery.[^envoy-bzlmod-llvm][^envoy-main-llvm][^toolshed-llvm][^toolshed-sysroot]

### 4. The real checked-in Envoy delta is in Rust toolchain registration, not LLVM wiring

The committed `bzlmod-envoy` branch currently has:

- `rust.repository_set(...)` for `rust_linux_s390x`
- `rust.toolchain(...)` with only `wasm32-unknown-unknown` and `wasm32-wasi`
- **no** checked-in `extra_rustc_flags` or `extra_exec_rustc_flags`.[^envoy-module-rust]

Upstream WORKSPACE `main` has:

- `rust_repository_set(...)` for `rust_linux_s390x`
- `rust_register_toolchains(...)` with `wasm32-unknown-unknown`, `wasm32-wasip1`, `x86_64-unknown-linux-gnu`, and `aarch64-unknown-linux-gnu`.[^envoy-main-rust]

That means the committed bzlmod branch is still not in full parity with WORKSPACE Rust toolchain registration. But that parity gap does **not** explain why `toolchain_linker_preference=cc` did nothing, and it does not change the source-level finding that the emitted linker-selection flag is `-fuse-ld=lld` rather than an explicit `-Clink-self-contained`.

## Why the added flags didn't work

I could not confirm the claimed "bzlmod toolchain tag drops the flags" from source. The `rules_rust` bzlmod extension forwards `extra_rustc_flags` and `extra_exec_rustc_flags` into `rust_register_toolchains(...)`, which forwards them into `rust_repository_set(...)`, which forwards them into `rust_toolchain_repository(...)`.[^rr-ext-forward][^rr-repos-forward]

Inside the generated `rust_toolchain`, `collect_extra_rustc_flags()` applies flags in this order:

1. `extra_rustc_flags_for_crate_types`
2. toolchain `extra_exec_rustc_flags` / `extra_rustc_flags`
3. command-line build settings `--@rules_rust//rust/settings:extra_rustc_flags`
4. command-line build settings `--@rules_rust//rust/settings:extra_exec_rustc_flags`.[^rr-rustc-extra]

That ordering matters:

- the **toolchain-tag attributes are not dropped** by the bzlmod extension
- the **build-setting flags are later**, so they are the highest-confidence path when overriding another `-C...` choice.[^rr-rustc-extra]

In other words, the source code supports the build-setting explanation and refutes the "module extension discarded my flags" explanation.

## WORKSPACE vs bzlmod comparison

| Topic | WORKSPACE `main` | bzlmod branch | Finding |
| --- | --- | --- | --- |
| Rust registration | `rust_register_toolchains(...)` includes `wasm32-wasip1`, `x86_64-unknown-linux-gnu`, `aarch64-unknown-linux-gnu`.[^envoy-main-rust] | checked-in `rust.toolchain(...)` only includes `wasm32-unknown-unknown`, `wasm32-wasi`.[^envoy-module-rust] | Real parity gap in committed branch. |
| Rust extra flags | no checked-in extra Rust flags in WORKSPACE config.[^envoy-bazelrc] | no checked-in extra Rust flags in committed `MODULE.bazel` either.[^envoy-module-rust] | The repo state does not show a committed extension-drop bug. |
| LLVM roots | `bazel/toolchains.bzl` uses `@llvm_minimal_linux_x64`, `@llvm_minimal_linux_arm64`, `@llvm_minimal_macos_arm64`.[^envoy-main-llvm] | `MODULE.bazel` uses the same three toolchain roots.[^envoy-bzlmod-llvm] | Same artifacts. |
| Sysroots | `bazel/toolchains.bzl` uses `@sysroot_linux_amd64//:sysroot` and `@sysroot_linux_arm64//:sysroot`.[^envoy-main-llvm] | `MODULE.bazel` uses the same two sysroots.[^envoy-bzlmod-llvm] | Same artifacts. |
| toolshed wrappers | N/A | `llvm_minimal_extension` and `sysroot_extension` just call `setup_llvm_minimal()` / `setup_sysroots(...)`.[^toolshed-llvm][^toolshed-sysroot] | Wrapper-only difference. |
| injected linker flags | `toolchains_llvm` injects `-fuse-ld=lld`.[^llvm-lld] | same | Not a bzlmod-only delta. |
| linker preference default | `none` = prefer `cc` if available.[^rr-toolchain-pref][^rr-toolchain-impl] | same | Explains why forcing `=cc` did nothing. |

## Fix options evaluated

| Candidate | Works? | Why |
| --- | --- | --- |
| `--@rules_rust//rust/settings:extra_exec_rustc_flags=-Clink-self-contained=no` | **Recommended** | This is the exact exec-config escape hatch that `rules_rust` documents for proc-macros/build scripts, and it is appended after toolchain flags.[^rr-settings-extra][^rr-rustc-extra] |
| `--@rules_rust//rust/settings:extra_rustc_flags=-Clink-self-contained=no` | Maybe needed later | Same mechanism, but only for non-exec Rust actions; the failing action here is an exec-platform proc-macro.[^rr-settings-extra][^rr-rustc-extra] |
| `rust.toolchain(extra_exec_rustc_flags = [...])` | Should work in principle | Source says the bzlmod extension forwards it. It is weaker than the build setting because the build-setting flags are appended later.[^rr-ext-forward][^rr-repos-forward][^rr-rustc-extra] |
| `extra_rustc_flags_for_crate_types = {"proc-macro": [...]}` | Plausible but not best | `rules_rust` supports per-crate-type flags, and it would target this proc-macro specifically, but it still relies on toolchain regeneration rather than the documented build-setting override path.[^rr-toolchain-attrs][^rr-rustc-extra] |
| `--@rules_rust//rust/settings:toolchain_linker_preference=cc` | **Does not fix this** | The failing command was already using the `cc` path (`cc_wrapper.sh` + `-fuse-ld=lld`).[^rr-toolchain-pref][^rr-toolchain-impl][^llvm-lld] |
| Change triples (`wasm32-wasi` → `wasm32-wasip1`, add x86_64/aarch64) | Needed for parity, not the fix proven here | This is a real WORKSPACE-parity cleanup for the committed branch, but it does not change the source-level origin of the failing linker selection.[^envoy-main-rust][^envoy-module-rust] |

### Recommendation

For Envoy's bzlmod migration, the single best fix is:

```text
build --@rules_rust//rust/settings:extra_exec_rustc_flags=-Clink-self-contained=no
```

Put it in the bzlmod path's `.bazelrc` / CI invocation that exercises the failing proc-macro build. If a non-exec Rust link later shows the same behavior, add the non-exec sibling:

```text
build --@rules_rust//rust/settings:extra_rustc_flags=-Clink-self-contained=no
```

This recommendation follows directly from the `rules_rust` source: those build settings are the documented global override points for exec and non-exec Rust actions, and they are appended after toolchain-level flags.[^rr-settings-extra][^rr-rustc-extra]

## Appendix

### Commands run

- `git fetch --unshallow origin && git fetch origin main:refs/remotes/origin/main`
- `git fetch upstream main:refs/remotes/upstream/main`
- GitHub Actions inspection:
  - listed recent runs for `phlax/envoy` and PR `envoyproxy/envoy#42890`
  - fetched failed job logs for CodeQL run `31366790357`
- local Bazel probe:
  - `/tmp/fix-bazel-truststore.sh`
  - `bazel aquery --config=clang 'mnemonic("Rustc", deps(//test/config_test:config_test))'`

### Raw evidence notes

- The current checkout's `MODULE.bazel` still lacks the user-described local experiments (`extra_exec_rustc_flags`, `extra_rustc_flags`, and the extra Linux target triples); the checked-in file only has `wasm32-unknown-unknown` and `wasm32-wasi`.[^envoy-module-rust]
- The current accessible GitHub failure in this environment is Android SDK setup, not the Rust self-contained-linker failure.[^codeql-android]

[^rr-rustc-link]: `bazelbuild/rules_rust` `rust/private/rustc.bzl:1125-1140`.
[^llvm-lld]: `bazel-contrib/toolchains_llvm` `toolchain/cc_toolchain_config.bzl:279-282,638-645`.
[^envoy-bzlmod-llvm]: `phlax/envoy` `/home/runner/work/envoy/envoy/MODULE.bazel:181-225`.
[^envoy-main-llvm]: `envoyproxy/envoy` `bazel/toolchains.bzl:68-94`.
[^toolshed-llvm]: `envoyproxy/toolshed` `bazel/compile/extensions.bzl:157-175,212-230`.
[^toolshed-sysroot]: `envoyproxy/toolshed` `bazel/sysroot/extensions.bzl:5-31`.
[^rr-ext-forward]: `bazelbuild/rules_rust` `rust/extensions.bzl:96-123,201-220`.
[^rr-repos-forward]: `bazelbuild/rules_rust` `rust/repositories.bzl:262-281,1273-1296`.
[^rr-rustc-extra]: `bazelbuild/rules_rust` `rust/private/rustc.bzl:1210,1240-1275`.
[^rr-settings-extra]: `bazelbuild/rules_rust` `rust/private/rustc.bzl:2617-2652`.
[^rr-toolchain-pref]: `bazelbuild/rules_rust` `rust/settings/settings.bzl:287-301`.
[^rr-toolchain-impl]: `bazelbuild/rules_rust` `rust/toolchain.bzl:518-537`.
[^envoy-module-rust]: `phlax/envoy` `/home/runner/work/envoy/envoy/MODULE.bazel:330-347`.
[^envoy-main-rust]: `envoyproxy/envoy` `bazel/dependency_imports.bzl:71-90`.
[^envoy-bazelrc]: `phlax/envoy` `/home/runner/work/envoy/envoy/.bazelrc:98-100`.
[^rr-toolchain-attrs]: `bazelbuild/rules_rust` `rust/toolchain.bzl:709-717`.
[^codeql-android]: GitHub Actions job log for `envoyproxy/envoy` run `31366790357`, job `CodeQL-Build`: `No Android SDK apis found in the Android SDK at /usr/local/lib/android/sdk`.
