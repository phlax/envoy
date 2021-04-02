
## The git push hook

Envoy CI checks the entire repo for a number of formatting and code issues.

Many of these can be caught and corrected with the checks provided in the git push hooks.


### Install the hook

```console
$ ./support/bootstrap

```

### Disabling all checks

You can disable all checks for a single push command with:

```console
$ git push --no-verify

```

### The push hook checks

#### DCO signoff

Ensures that all commits are digitally-signed by the author.

#### Code format (multi-language linter)

Runs `clang-tidy` and other code formatting utils on any changed code files of various types

##### requires: `buildifier` command set in `$BUILDIFIER_PATH`

See https://github.com/envoyproxy/envoy/blob/main/bazel/README.md#running-clang-format-without-docker for further information.

##### requires: `clang-format` command set in `$CLANG_FORMAT`

See https://github.com/envoyproxy/envoy/blob/main/bazel/README.md#running-clang-format-without-docker for further information.

##### General linting (glint)

Runs a check on non-binary files for 3 things:

- must have a new line at end of each file - usually not a blank line
- no trailing whitespace
- no mixed tabs and spaces for indentation

#### Flake8 python linter

Runs the python flake8 linter on any changed python files.

The config can be found in the `.flake8` file at the root of the repo.

##### requires: python flake8

For example, to install with pip:

```console

$ pip install flake8

```

You can run the `flake8` command against all files, as is done in CI with the following command in the root of the repo:

```console

$ flake8 .

```

#### Shellcheck

Runs shellcheck against any changed files that look as though they are shell scripts.

Provides mostly helpful suggestions on how to fix.

##### requires: `shellcheck` command set or in `$PATH`

See https://github.com/koalaman/shellcheck#installing for information on installing `shellcheck`.

#### Yapf python formatter

Runs the `yapf` formatter on python code that has changed.

The `yapf` config file is in the `.style.yapf` file in the root of the Envoy repository.

##### requires: python yapf

For example to install with pip:

```console

$ pip install yapf

```

You can run the `yapf` command against all files, as is done in CI with the following command in the root of the repo:

```console

$ yapf .

```

#### Spelling checks

Runs a spell checker on changed C++ and protobuf files.

Exclusions for words and files can be set in `tools/spelling/spelling_dictionary.txt` and `tools/spelling/spelling_skip_files.txt` respectively.

#### Protobuf api sync

Ensure that the `api` and `generated_api_shadow` directories are in sync.

##### requires: `bazel` command available or `$BAZEL_PATH` set

See https://github.com/envoyproxy/envoy/blob/main/bazel/README.md for information about installing bazel on your system.


#### Repositories

Ensures that any repositories in bazel files are properly defined.


### Configuring checks

You can override some settings and which checks adding an `.envoypush` config file to the root of your local repo.

Changing any of the default settings to **any non-empty value** will activate.

These are some default settings that might be useful to change in your environment:

```bash

SKIP_PUSH_MESSAGE=
EXIT_ON_ERROR=
FAIL_ON_MISSING=
PUSH_ON_FAILURE=
SKIP_CODE_FORMAT=
SKIP_FLAKE8=
SKIP_SHELLCHECK=
SKIP_PROTOS=

```

For example, the initial push message can be supressed with this command, run in the root of the Envoy repo:

```console

$ echo "SKIP_PUSH_MESSAGE=yes" >> .envoypush

```

If you wish push to exit immediately on error, rather than running all checks and erroring at the end:

```console

$ echo "EXIT_ON_ERROR=yes" >> .envoypush

```

For more advanced usage you can customize the `$CHECKS` array in the `.envoypush` file.

Specify which checks to run and for which files with matching regexes:

```bash

CHECKS=(
    "code_format:BUILD$|WORKSPACE$|\.bzl$|\.cc$|\.h$|\.java$|\.m$|\.md$|\.mm$|\.proto$|\.rst$"
    "glint:*"
    "shellcheck:*"
    "flake8:\.py$"
    "yapf:\.py$"
    "spelling:\.cc$|\.h$|\.proto$"
    "protos:\.proto$"
    "repositories:\.bzl$")

```

See the pre-push file for other settings.

### Missing check utilities

If a utility required by a check is missing **the check will be disabled**, and a warning will be printed to `stderr`.

This warning message should also provide some pointer to install the requirements

See above for further information about specific checks.

If you don't want to install the utility, you can skip the check to suppress the warning.

For example, to skip the clang tidy check:


```console

$ echo "SKIP_CODE_FORMAT=yes" >> .envoypush

```

If you wish to make missing utilities a failure you can set the `FAIL_ON_MISSING` var in `.envoypush`

```console

$ echo "FAIL_ON_MISSING=yes" >> .envoypush
$ git push
[check:code_format] WARNING: Missing $BUILDIFIER_PATH or $CLANG_FORMAT, skipping code_format/check_format.py
[check:code_format]     See https://github.com/envoyproxy/envoy/blob/main/bazel/README.md#running-clang-format-without-docker for further information
[check:code_format] ERROR: missing util
...
error: failed to push some refs to 'github.com:user/envoy'

```

### Debugging hook checks

Mostly the hooks should be quiet (ideally at least!), unless there is a problem.

If you wish to see what is being run set the `DEBUG` flag in `.envoypush`

```console

$ echo "DEBUG=yes" >> .envoypush
$ git push
[check:dco]
[check:code_format] support/hooks/README.md
[check:glint] support/hooks/README.md
[check:spelling] support/hooks/README.md
...

```
