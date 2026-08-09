#!/usr/bin/env python3
"""Update deps.yaml with version and urls derived from MODULE.bazel and repository_locations.bzl.

This tool reads:
  - MODULE.bazel: bazel_dep entries (name, version, repo_name)
  - repository_locations.bzl: REPOSITORY_LOCATIONS_SPEC (non-registry deps, e.g. quiche)
  - MODULE.bazel.lock: source.json URLs for each resolved module version
  - Fetches source.json from registries to obtain archive download URLs

It then updates deps.yaml with:
  - version: resolved version string
  - urls: list of archive download URLs (expanded from templates where applicable)

For any dep whose version cannot be resolved, version is set to "MISSING".
For any MODULE.bazel dep that has no deps.yaml entry, a skeleton entry is added
with all required metadata fields set to "MISSING" or ["MISSING"] as appropriate.

Usage:
  python3 tools/dependency/update_deps_yaml.py \\
    --module MODULE.bazel \\
    --lock MODULE.bazel.lock \\
    --repo-locations bazel/repository_locations.bzl \\
    bazel/deps.yaml
"""

import argparse
import json
import logging
import re
import sys
import urllib.request
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

# Required string fields that get "MISSING" value in new entries
MISSING_STR = "MISSING"
# Required list fields that get ["MISSING"] value in new entries
MISSING_LIST = ["MISSING"]

# Fields that are lists in deps.yaml
LIST_FIELDS = {"use_category", "extensions", "urls"}

# Template placeholders used in url patterns in REPOSITORY_LOCATIONS_SPEC
_VERSION_PLACEHOLDER = re.compile(r"\{version\}")


def expand_url_template(url_template: str, version: str) -> str:
    """Expand {version} placeholder in a URL template."""
    return url_template.replace("{version}", version)


def parse_module_bazel(module_path: Path) -> dict:
    """Parse MODULE.bazel and return a mapping of module_name -> {version, repo_name}.

    Handles commented-out bazel_dep lines (starting with #).
    repo_name (if present) is the local alias used in the build graph.
    """
    content = module_path.read_text()
    result = {}

    for match in re.finditer(r"bazel_dep\s*\([^)]+\)", content, re.DOTALL):
        block = match.group(0)
        # Skip commented-out entries
        # Check if the line containing 'bazel_dep' has a '#' before it
        start = match.start()
        line_start = content.rfind("\n", 0, start) + 1
        prefix = content[line_start:start].strip()
        if prefix.startswith("#"):
            continue

        name_m = re.search(r'name\s*=\s*"([^"]+)"', block)
        ver_m = re.search(r'version\s*=\s*"([^"]+)"', block)
        repo_m = re.search(r'repo_name\s*=\s*"([^"]+)"', block)

        if name_m and ver_m:
            name = name_m.group(1)
            result[name] = {
                "version": ver_m.group(1),
                "repo_name": repo_m.group(1) if repo_m else None,
            }

    return result


def strip_comments(content: str) -> str:
    """Strip Python/Starlark line comments (#...) from content."""
    lines = []
    for line in content.splitlines():
        # Remove inline comments, but preserve # inside strings
        in_str = False
        str_char = None
        result_chars = []
        i = 0
        while i < len(line):
            ch = line[i]
            if in_str:
                result_chars.append(ch)
                if ch == str_char:
                    in_str = False
            elif ch in ('"', "'"):
                in_str = True
                str_char = ch
                result_chars.append(ch)
            elif ch == "#":
                break  # rest of line is comment
            else:
                result_chars.append(ch)
            i += 1
        lines.append("".join(result_chars))
    return "\n".join(lines)


def parse_repository_locations_bzl(bzl_path: Path) -> dict:
    """Parse repository_locations.bzl and extract REPOSITORY_LOCATIONS_SPEC.

    Returns mapping of dep_name -> {version, urls} with {version} expanded.
    """
    if not bzl_path.exists():
        return {}

    content = strip_comments(bzl_path.read_text())

    # Find REPOSITORY_LOCATIONS_SPEC = dict(...)
    spec_match = re.search(r"REPOSITORY_LOCATIONS_SPEC\s*=\s*dict\s*\(", content)
    if not spec_match:
        return {}

    # Extract the full dict(...) including nested parens
    start = spec_match.end() - 1  # position of opening (
    depth = 0
    i = start
    while i < len(content):
        if content[i] == "(":
            depth += 1
        elif content[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1

    dict_str = "dict" + content[start:i + 1]

    # ast.literal_eval won't work on Starlark; use regex to extract each dep entry
    result = {}

    # Find top-level dep name = dict(...) entries within the spec
    # We scan for `name = dict(...)` at the top level of the outer dict
    # by tracking parenthesis depth inside dict_str
    inner = content[start + 1:i]  # content between outer ( and )

    # Find each `dep_name = dict(` and capture its contents
    dep_pattern = re.compile(r"\b([A-Za-z_]\w*)\s*=\s*dict\s*\(")
    j = 0
    while j < len(inner):
        dm = dep_pattern.search(inner, j)
        if not dm:
            break
        dep_name = dm.group(1)
        # Skip Starlark keywords that look like assignments
        if dep_name in ("dict", "list", "True", "False", "None"):
            j = dm.end()
            continue
        # Find the matching ) for this dict(
        d_start = dm.end() - 1  # position of opening (
        d_depth = 0
        k = d_start
        while k < len(inner):
            if inner[k] == "(":
                d_depth += 1
            elif inner[k] == ")":
                d_depth -= 1
                if d_depth == 0:
                    break
            k += 1

        dep_content = inner[d_start + 1:k]

        # Extract version and urls from dep_content
        version_m = re.search(r'version\s*=\s*"([^"]+)"', dep_content)
        urls_m = re.findall(r'"(https?://[^"]+)"', dep_content)

        if version_m:
            version = version_m.group(1)
            expanded_urls = [expand_url_template(u, version) for u in urls_m]
            result[dep_name] = {
                "version": version,
                "urls": expanded_urls,
            }

        j = k + 1

    return result


def extract_source_json_urls_from_lock(lock_path: Path) -> dict:
    """Extract {module_name: {version: source_json_url}} from MODULE.bazel.lock.

    The registryFileHashes keys include URLs like:
      https://bcr.bazel.build/modules/abseil-cpp/20260107.1/source.json
    These tell us which source.json to fetch for each module@version.
    """
    if not lock_path.exists():
        return {}

    with lock_path.open() as f:
        lock = json.load(f)

    result = {}  # {module_name: {version: source_json_url}}
    for url in lock.get("registryFileHashes", {}).keys():
        if not url.endswith("/source.json"):
            continue
        # URL format: {registry}/modules/{name}/{version}/source.json
        parts = url.split("/modules/")
        if len(parts) != 2:
            continue
        name_ver = parts[1].rstrip("/source.json")
        # Split on last occurrence to handle names with / in version (unlikely but safe)
        idx = name_ver.rfind("/")
        if idx < 0:
            continue
        module_name = name_ver[:idx]
        version = name_ver[idx + 1:]
        if module_name not in result:
            result[module_name] = {}
        result[module_name][version] = url

    return result


def fetch_source_url(source_json_url: str) -> tuple:
    """Fetch a source.json URL and return (archive_urls, effective_version_or_none).

    effective_version_or_none is the git SHA extracted from the URL if the archive
    is a hash-based (non-tagged) release, or None to use the MODULE.bazel version.
    """
    try:
        with urllib.request.urlopen(source_json_url, timeout=10) as resp:
            data = json.loads(resp.read())
        url = data.get("url")
        if url:
            urls = [url]
        else:
            urls = data.get("urls", [])

        # Extract git SHA from archive URL if present.
        # Archive URLs look like: .../archive/<sha>.tar.gz
        # where <sha> is a 40-char hex string.
        effective_version = None
        for archive_url in urls:
            sha_match = re.search(r"/archive/([0-9a-f]{40})(?:\.tar\.gz|\.zip)$", archive_url)
            if sha_match:
                effective_version = sha_match.group(1)
                break

        return urls, effective_version
    except Exception as exc:
        logger.warning("Failed to fetch %s: %s", source_json_url, exc)
        return [], None


def build_module_version_info(
        module_deps: dict,
        repo_locations: dict,
        source_json_map: dict,
) -> dict:
    """Build a mapping: dep_name -> {version, urls} from all sources.

    Priority:
    1. repository_locations.bzl (has explicit urls)
    2. MODULE.bazel + lockfile source.json (fetches urls from registry)
    """
    result = {}

    # First, populate from MODULE.bazel
    for mod_name, info in module_deps.items():
        version = info["version"]
        # Find source.json URL from lockfile
        source_json_url = None
        name_versions = source_json_map.get(mod_name, {})
        if version in name_versions:
            source_json_url = name_versions[version]
        else:
            # Try stripping .envoy suffix for registry lookup
            base_version = re.sub(r"\.envoy$", "", version)
            if base_version in name_versions:
                source_json_url = name_versions[mod_name].get(base_version)

        urls = []
        effective_version = version
        if source_json_url:
            urls, sha = fetch_source_url(source_json_url)
            # For hash-based (non-tagged) archives, use the git SHA as the version
            # so it matches the URL and satisfies generate_external_deps_rst.py assertions.
            if sha:
                effective_version = sha

        result[mod_name] = {"version": effective_version, "urls": urls}

        # Also record under repo_name alias if present
        repo_name = info.get("repo_name")
        if repo_name:
            result[repo_name] = {"version": effective_version, "urls": urls}

    # Override/supplement with repository_locations.bzl (which has explicit urls)
    for dep_name, info in repo_locations.items():
        result[dep_name] = info

    return result


def normalize_key(key: str) -> str:
    """Normalize a dep key for fuzzy matching (replace - and . with _)."""
    return key.replace("-", "_").replace(".", "_")


def find_version_info(yaml_key: str, version_info: dict) -> dict:
    """Find version info for a deps.yaml key in the version_info map.

    Tries: exact match, then normalized match.
    Returns {version, urls} or None.
    """
    if yaml_key in version_info:
        return version_info[yaml_key]

    norm_yaml = normalize_key(yaml_key)
    for vk, vi in version_info.items():
        if normalize_key(vk) == norm_yaml:
            return vi

    return None


def update_deps_yaml(
        deps_yaml_path: Path,
        module_deps: dict,
        repo_locations: dict,
        source_json_map: dict,
        add_missing_module_deps: bool = True,
) -> None:
    """Update deps.yaml in-place with version and urls from MODULE.bazel and repo_locations."""

    # Read existing deps.yaml
    content = deps_yaml_path.read_text()
    deps = yaml.safe_load(content) or {}

    # Build complete version info map
    version_info = build_module_version_info(module_deps, repo_locations, source_json_map)

    # Update existing entries
    for yaml_key in list(deps.keys()):
        info = find_version_info(yaml_key, version_info)
        if info:
            deps[yaml_key]["version"] = info["version"]
            deps[yaml_key]["urls"] = info["urls"]
        else:
            deps[yaml_key]["version"] = MISSING_STR
            deps[yaml_key]["urls"] = []
            logger.warning("No version found for deps.yaml key: %s", yaml_key)

    # Add new entries for MODULE.bazel deps not in deps.yaml
    if add_missing_module_deps:
        for mod_name, info in module_deps.items():
            # Check if this module is already covered (directly or via alias)
            found = find_version_info(mod_name, {k: {} for k in deps.keys()}) is not None
            if not found:
                # Also check repo_name
                repo_name = info.get("repo_name")
                if repo_name and repo_name in deps:
                    continue
                deps[mod_name] = {
                    "project_name": MISSING_STR,
                    "project_desc": MISSING_STR,
                    "project_url": MISSING_STR,
                    "release_date": MISSING_STR,
                    "use_category": MISSING_LIST,
                    "license": MISSING_STR,
                    "license_url": MISSING_STR,
                    "version": info["version"],
                    "urls": version_info.get(mod_name, {}).get("urls", []),
                }
                logger.info("Added new entry for: %s", mod_name)

    # Write updated deps.yaml preserving order
    deps_yaml_path.write_text(
        yaml.dump(deps, default_flow_style=False, allow_unicode=True, sort_keys=False))
    logger.info("Updated %s", deps_yaml_path)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("deps_yaml", type=Path, help="Path to deps.yaml to update")
    parser.add_argument(
        "--module",
        type=Path,
        required=True,
        help="Path to MODULE.bazel",
    )
    parser.add_argument(
        "--lock",
        type=Path,
        required=True,
        help="Path to MODULE.bazel.lock",
    )
    parser.add_argument(
        "--repo-locations",
        type=Path,
        default=None,
        help="Path to repository_locations.bzl (optional, for non-registry deps)",
    )
    parser.add_argument(
        "--no-add-missing",
        action="store_true",
        help="Do not add new entries for MODULE.bazel deps missing from deps.yaml",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(message)s",
    )

    # Parse inputs
    logger.info("Parsing MODULE.bazel: %s", args.module)
    module_deps = parse_module_bazel(args.module)
    logger.info("Found %d bazel_dep entries", len(module_deps))

    repo_locations = {}
    if args.repo_locations:
        logger.info("Parsing repository_locations.bzl: %s", args.repo_locations)
        repo_locations = parse_repository_locations_bzl(args.repo_locations)
        logger.info("Found %d REPOSITORY_LOCATIONS_SPEC entries", len(repo_locations))

    logger.info("Parsing MODULE.bazel.lock: %s", args.lock)
    source_json_map = extract_source_json_urls_from_lock(args.lock)
    logger.info("Found source.json URLs for %d modules", len(source_json_map))

    # Update deps.yaml
    update_deps_yaml(
        args.deps_yaml,
        module_deps,
        repo_locations,
        source_json_map,
        add_missing_module_deps=not args.no_add_missing,
    )


if __name__ == "__main__":
    main()
