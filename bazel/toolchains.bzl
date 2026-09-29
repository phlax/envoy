load("@envoy_repo//:compiler.bzl", "USE_LIBSTDCPP")
load("@llvm_toolchain_llvm//:llvm.bzl", "LLVM_IS_HOST", "LLVM_LIB_DIR", "LLVM_MAJOR", "LLVM_MAJOR_MINOR", "LLVM_VERSION")

LIBCLANG_CPP = "@llvm_toolchain_llvm//:%s/libclang-cpp.so.%s" % (LLVM_LIB_DIR, LLVM_MAJOR_MINOR)

# Distro-packaged LLVM splits libLLVM.so out of libclang-cpp.so; the hermetic bundle folds it in.
LIBLLVM = ("@llvm_toolchain_llvm//:%s/libLLVM.so.%s" % (LLVM_LIB_DIR, LLVM_MAJOR_MINOR)) if LLVM_IS_HOST else None
