GCC builds (``--config=gcc``) now use toolshed's hermetic GCC 13.4.0 toolchain with static libstdc++,
hermetic lld, and Envoy's hermetic sysroot (the same as Clang). For a system GCC installation, use
the root module's ``gcc_extension.host(path = "...")`` tag from
``@envoy_toolshed//toolchains/gcc:extensions.bzl``.
