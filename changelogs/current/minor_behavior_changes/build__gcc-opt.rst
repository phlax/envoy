The GCC reference build (``--config=gcc``) is now built and tested in Envoy CI with ``-c opt``, for
consistency with the Clang build and to optimize CI. This has no effect on any production binaries
produced by the project, but downstream projects that build with GCC and wish to continue building
with ``-c fastbuild`` may require some adjustment.
