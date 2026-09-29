Removed the obsolete Clang Bazel configuration. Clang with libc++ is
now the default toolchain and requires no configuration flag. GCC with libstdc++ remains available
via ``--config=gcc``. Other compiler/standard-library combinations require a user-provided toolchain.
