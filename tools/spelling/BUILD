load("@rules_python//python:defs.bzl", "py_binary")
load(":defs.bzl", "hunspell_bin", "hunspell_dic", "hunspell_runtime")

licenses(["notice"])  # Apache 2

# The hermetic hunspell toolchain (envoy_toolshed), so the spell check needs nothing from the host.
hunspell_runtime(name = "hunspell_runtime")

hunspell_bin(name = "hunspell_bin")

hunspell_dic(name = "hunspell_dic")

py_binary(
    name = "check_spelling_pedantic",
    srcs = ["check_spelling_pedantic.py"],
    data = [
        ":hunspell_bin",
        ":hunspell_dic",
        ":hunspell_runtime",
        ":spelling_dictionary.txt",
    ],
    env = {
        "HUNSPELL": "$(rootpath :hunspell_bin)",
        "HUNSPELL_DICT": "$(rootpath :hunspell_dic)",
        "SPELLING_DICTIONARY": "$(rootpath :spelling_dictionary.txt)",
    },
)
