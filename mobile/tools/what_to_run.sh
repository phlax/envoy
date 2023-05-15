#!/bin/bash

set -euo pipefail

branch_name="$GITHUB_REF_NAME"


function success() {
    echo "android_build=true" >> "$GITHUB_OUTPUT"
    echo "android_build_all=true" >> "$GITHUB_OUTPUT"
    echo "android_tests=true" >> "$GITHUB_OUTPUT"
    echo "asan=true" >> "$GITHUB_OUTPUT"
    echo "cc_tests=true" >> "$GITHUB_OUTPUT"
    echo "compile_time_options=true" >> "$GITHUB_OUTPUT"
    echo "coverage=true" >> "$GITHUB_OUTPUT"
    echo "formatting=true" >> "$GITHUB_OUTPUT"
    echo "ios_build=true" >> "$GITHUB_OUTPUT"
    echo "ios_build_all=true" >> "$GITHUB_OUTPUT"
    echo "ios_tests=true" >> "$GITHUB_OUTPUT"
    echo "perf=true" >> "$GITHUB_OUTPUT"
    echo "release_validation=true" >> "$GITHUB_OUTPUT"
    echo "tsan=true" >> "$GITHUB_OUTPUT"
}

if [[ $branch_name == "main" ]]; then
    echo "android_build=true" >> "$GITHUB_OUTPUT"
    echo "android_tests=true" >> "$GITHUB_OUTPUT"
    echo "asan=true" >> "$GITHUB_OUTPUT"
    echo "cc_tests=true" >> "$GITHUB_OUTPUT"
    echo "compile_time_options=true" >> "$GITHUB_OUTPUT"
    echo "coverage=true" >> "$GITHUB_OUTPUT"
    echo "formatting=true" >> "$GITHUB_OUTPUT"
    echo "ios_build=true" >> "$GITHUB_OUTPUT"
    echo "ios_tests=true" >> "$GITHUB_OUTPUT"
    echo "perf=true" >> "$GITHUB_OUTPUT"
    echo "release_validation=true" >> "$GITHUB_OUTPUT"
    echo "tsan=true" >> "$GITHUB_OUTPUT"
    exit 0
fi

base_commit="$(git merge-base origin/main HEAD)"
changed_files="$(git diff "$base_commit" --name-only)"

if grep -q "^mobile/" <<< "$changed_files"; then
    success "mobile"
elif grep -q "^bazel/repository_locations\.bzl" <<< "$changed_files"; then
    success "bazel/repository_locations.bzl"
elif grep -q "^\.bazelrc" <<< "$changed_files"; then
    success ".bazelrc"
elif grep -q "^\.github/workflows/mobile-*" <<< "$changed_files"; then
    success "GitHub Workflows"
fi
