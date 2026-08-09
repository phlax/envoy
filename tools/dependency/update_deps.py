#!/usr/bin/env python3
"""Update deps.yaml version and urls from the bzlmod module graph.

This tool reads a MODULE.bazel (and its MODULE.bazel.lock) plus the
corresponding repository_locations.bzl, then updates the deps.yaml file
in place, adding/refreshing the ``version`` and ``urls`` fields for each
direct dependency.

Existing human-authored metadata (project_name, project_desc, project_url,
release_date, use_category, extensions, cpe, license, license_url) is
preserved unchanged.  Only ``version`` and ``urls`` are written by this tool.

If a dep appears in MODULE.bazel but has no entry in deps.yaml a stub is
created with every required field set to the sentinel value ``MISSING`` so
that a human can grep for gaps.

Usage examples::

    # Update root module deps
    python tools/dependency/update_deps.py

    # Update api module deps
    python tools/dependency/update_deps.py \\
        --module api/MODULE.bazel \\
        --deps    api/bazel/deps.yaml

    # Via Bazel
    bazel run //tools/dependency:update_deps
    bazel run //tools/dependency:update_deps -- --module api/MODULE.bazel --deps api/bazel/deps.yaml
"""

import argparse
import json
import os
import pathlib
import re
import sys
import urllib.request
import urllib.error

import yaml

# ---------------------------------------------------------------------------
# Sentinel used for unknown / unresolvable metadata fields
# ---------------------------------------------------------------------------
MISSING = "MISSING"

# Required scalar fields every deps.yaml entry must carry
SCALAR_FIELDS = [
    "project_name",
    "project_desc",
    "project_url",
    "release_date",
    "cpe",
    "license",
    "license_url",
]

# Required list fields every deps.yaml entry must carry
LIST_FIELDS = ["use_category"]

# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

_BAZEL_DEP_BLOCK_RE = re.compile(r'bazel_dep\s*\(([^)]+)\)', re.DOTALL)
_ATTR_RE = re.compile(r'(\w+)\s*=\s*"([^"]*)"')


def parse_module_bazel(path: pathlib.Path) -> dict:
    """Return {module_name: version_str} for every bazel_dep in MODULE.bazel.

    If a bazel_dep has no version attribute the value will be ``""``."""
    text = path.read_text()
    deps = {}
    for block_m in _BAZEL_DEP_BLOCK_RE.finditer(text):
        block = block_m.group(1)
        attrs = dict(_ATTR_RE.findall(block))
        name = attrs.get("name", "")
        if not name:
            continue
        version = attrs.get("version", "")
        deps[name] = version
    return deps


def parse_lockfile(path: pathlib.Path) -> dict:
    """Return {module_name: source_json_url} from MODULE.bazel.lock.

    Scans ``registryFileHashes`` for keys of the form
    ``…/modules/{name}/{version}/source.json`` and returns the URL keyed by
    module name.  When multiple registry entries exist for the same module
    (e.g. BCR and toolshed both provide it) the first one found is used.
    """
    data = json.loads(path.read_text())
    registry_hashes = data.get("registryFileHashes", {})
    result: dict = {}
    for url in registry_hashes:
        m = re.search(r'/modules/([^/]+)/([^/]+)/source\.json$', url)
        if m:
            name = m.group(1)
            if name not in result:
                result[name] = url
    # Also pick up non-module repos from extension generated specs (e.g. quiche)
    ext_specs: dict = {}
    for _ext_key, ext_val in data.get("moduleExtensions", {}).items():
        for platform_val in ext_val.values():
            for repo_name, repo_spec in platform_val.get("generatedRepoSpecs", {}).items():
                attrs = repo_spec.get("attributes", {})
                urls = attrs.get("urls", [])
                version = attrs.get("version", "")
                ext_specs[repo_name] = {"urls": urls, "version": version}
    return result, ext_specs


def fetch_source_json_url(source_json_url: str) -> str | None:
    """Fetch a registry source.json and return the upstream archive ``url``."""
    try:
        with urllib.request.urlopen(source_json_url, timeout=10) as resp:
            data = json.loads(resp.read())
        return data.get("url") or None
    except (urllib.error.URLError, json.JSONDecodeError, OSError):
        return None


# ---------------------------------------------------------------------------
# repository_locations.bzl parser
# ---------------------------------------------------------------------------

def parse_repository_locations(path: pathlib.Path) -> dict:
    """Parse REPOSITORY_LOCATIONS_SPEC from a .bzl file.

    Returns {repo_name: {version, urls, …}} dict.  Falls back gracefully if
    the file is absent or cannot be parsed.
    """
    if not path.exists():
        return {}
    text = path.read_text()
    # Extract the REPOSITORY_LOCATIONS_SPEC dict using a regex-based approach
    # that handles the Starlark dict()-of-dict() style.
    m = re.search(r'REPOSITORY_LOCATIONS_SPEC\s*=\s*dict\((.*)\)', text, re.DOTALL)
    if not m:
        return {}
    inner = m.group(1).strip()
    # Convert top-level Starlark keyword args to Python dict entries:
    # "key = dict(...)" → '"key": dict(...)'
    # We handle this by finding top-level key=dict( pairs
    result = {}
    # Find each top-level entry: identifier = dict(...)
    entry_re = re.compile(r'(\w+)\s*=\s*dict\(', re.DOTALL)
    # Build a simple Starlark->Python conversion by replacing
    # identifier = dict( with "identifier": dict(
    py_inner = entry_re.sub(r'"\1": dict(', inner)
    # Remove trailing commas before closing braces/parens (Python doesn't allow them in older ver)
    py_inner = re.sub(r',\s*\)', ')', py_inner)
    try:
        parsed = eval(f'{{{py_inner}}}', {"__builtins__": {}}, {"dict": dict})  # noqa: S307
    except Exception:
        return {}
    # Expand url templates
    for name, spec in parsed.items():
        version = spec.get("version", "")
        raw_urls = spec.get("urls", [])
        urls = [u.replace("{version}", version) for u in raw_urls]
        result[name] = {"version": version, "urls": urls}
    return result


# ---------------------------------------------------------------------------
# deps.yaml updater
# ---------------------------------------------------------------------------

def _load_yaml(path: pathlib.Path) -> dict:
    """Load a YAML file.  Returns an ordered dict (Python 3.7+ dict preserves order)."""
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text()) or {}


def _format_value(value) -> str:
    """Format a scalar value for inline YAML output.  All strings are double-quoted."""
    if isinstance(value, str):
        escaped = value.replace('\\', '\\\\').replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if value is None:
        return 'null'
    return str(value)


def _format_entry(data: dict) -> str:
    """Format a complete deps.yaml entry block (without the top-level key)."""
    lines = []
    for key, val in data.items():
        if isinstance(val, list):
            lines.append(f'  {key}:')
            for item in val:
                lines.append(f'  - {_format_value(item)}')
        else:
            lines.append(f'  {key}: {_format_value(val)}')
    return '\n'.join(lines) + '\n'


def _append_fields(block: str, fields: dict) -> str:
    """Append version/urls fields to an existing YAML entry block.

    The block is the full text of one deps.yaml entry (key + indented body).
    Fields are appended before any trailing blank line.
    """
    # Remove trailing newlines to cleanly append
    block = block.rstrip('\n')
    for key, val in fields.items():
        if isinstance(val, list):
            block += f'\n  {key}:'
            for item in val:
                block += f'\n  - {_format_value(item)}'
        else:
            block += f'\n  {key}: {_format_value(val)}'
    return block + '\n'


def _update_field(block: str, key: str, new_val) -> str:
    """Replace an existing field value in a YAML entry block."""
    if isinstance(new_val, list):
        # Replace multi-line list field
        # Find "  key:\n  - ...\n  - ..." pattern
        pattern = re.compile(
            r'^( {2}' + re.escape(key) + r':(?:\n {2}-[^\n]*)*)', re.MULTILINE)
        new_lines = f'  {key}:'
        for item in new_val:
            new_lines += f'\n  - {_format_value(item)}'
        if pattern.search(block):
            return pattern.sub(new_lines, block, count=1)
        # Field not present → append
        return _append_fields(block, {key: new_val})
    else:
        # Replace scalar field
        pattern = re.compile(r'^( {2}' + re.escape(key) + r':)( .+)?$', re.MULTILINE)
        replacement = f'  {key}: {_format_value(new_val)}'
        if pattern.search(block):
            return pattern.sub(replacement, block, count=1)
        return _append_fields(block, {key: new_val})


def _split_yaml_entries(text: str) -> list:
    """Split a YAML file into a list of (key, block_text) pairs.

    Each top-level key starts at column 0.  Comment-only lines are attached
    to the following entry.
    """
    entries = []
    current_key = None
    current_lines = []
    for line in text.splitlines(keepends=True):
        if line and line[0].isalpha() or (line and line[0] == '_'):
            # Top-level key line
            if current_key is not None:
                entries.append((current_key, ''.join(current_lines)))
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_.+-]*):', line)
            if m:
                current_key = m.group(1)
                current_lines = [line]
            else:
                # Not a key, continuation
                if current_key is not None:
                    current_lines.append(line)
        else:
            current_lines.append(line)
    if current_key is not None:
        entries.append((current_key, ''.join(current_lines)))
    return entries


def _write_yaml_surgical(
    deps_path: pathlib.Path,
    existing_data: dict,
    updates: dict,  # {key: {field: value}} — fields to add/update
    new_entries: dict,  # {key: full_entry_dict} — new entries to append
) -> None:
    """Update deps_path surgically: only touch changed entries."""
    if deps_path.exists():
        original = deps_path.read_text()
    else:
        original = ''

    # Split into keyed blocks
    entries = _split_yaml_entries(original)
    entry_map = {k: i for i, (k, _) in enumerate(entries)}

    # Apply updates to existing blocks
    blocks = [block for _, block in entries]
    for key, fields in updates.items():
        idx = entry_map.get(key)
        if idx is None:
            continue
        block = blocks[idx]
        for field, value in fields.items():
            # Check if field already exists with the right value
            existing_val = existing_data.get(key, {}).get(field)
            if existing_val == value:
                continue
            block = _update_field(block, field, value)
        blocks[idx] = block

    # Rebuild file
    result = ''.join(blocks)
    # Ensure trailing newline
    if result and not result.endswith('\n'):
        result += '\n'

    # Append new entries
    for name, entry_dict in new_entries.items():
        result += f'{name}:\n'
        result += _format_entry(entry_dict)

    deps_path.write_text(result)


def _stub_entry(version: str, urls: list) -> dict:
    """Return a stub deps.yaml entry with MISSING sentinels."""
    entry = {}
    for field in SCALAR_FIELDS:
        entry[field] = MISSING
    for field in LIST_FIELDS:
        entry[field] = [MISSING]
    if version:
        entry["version"] = version
    else:
        entry["version"] = MISSING
    if urls:
        entry["urls"] = urls
    return entry


def _normalize_name(name: str) -> str:
    """Normalize a dep name for key matching: replace -/. with _."""
    return re.sub(r'[-.]', '_', name)


def _find_entry_key(deps_data: dict, module_name: str) -> str | None:
    """Find the key in deps_data that best matches module_name.

    Tries exact match first, then underscore-normalised match (to handle
    entries that pre-date the module-name alignment, e.g. ``abseil_cpp``
    for module ``abseil-cpp``).
    """
    if module_name in deps_data:
        return module_name
    norm = _normalize_name(module_name)
    if norm in deps_data:
        return norm
    return None


def update_deps_yaml(
    deps_path: pathlib.Path,
    module_deps: dict,
    source_json_map: dict,
    ext_repo_specs: dict,
    repo_locations: dict,
    *,
    fetch_urls: bool = True,
    verbose: bool = True,
) -> None:
    """Update deps_path in-place with version/urls from the module graph."""
    deps_data = _load_yaml(deps_path)

    # Build the combined set of deps to process:
    #   1. bazel_dep entries from MODULE.bazel (module_deps)
    #   2. repo_locations entries (non-module / extension deps, e.g. quiche)
    # De-duplicate: if a repo_locations dep normalises to the same name as a
    # module dep, the module dep takes precedence (it is the bzlmod source of
    # truth); the repo_locations entry is skipped.
    module_norms = {_normalize_name(n): n for n in module_deps}
    filtered_repo_locations = {
        n: v
        for n, v in repo_locations.items()
        if _normalize_name(n) not in module_norms
    }
    all_names = set(module_deps) | set(filtered_repo_locations)

    # Collect changes: updates to existing entries and completely new entries
    field_updates: dict = {}   # {existing_key: {field: value}}
    new_entries: dict = {}     # {name: full_entry_dict}
    changed = False

    for name in sorted(all_names):
        version = ""
        urls: list = []

        if name in filtered_repo_locations:
            spec = filtered_repo_locations[name]
            version = spec.get("version", "")
            urls = spec.get("urls", [])
        elif name in module_deps:
            version = module_deps[name]
            if fetch_urls and name in source_json_map:
                src_url = fetch_source_json_url(source_json_map[name])
                if src_url:
                    urls = [src_url]
                elif verbose:
                    print(f"  [warn] could not fetch source.json for {name}", file=sys.stderr)
        elif name in ext_repo_specs:
            spec = ext_repo_specs[name]
            version = spec.get("version", "")
            urls = spec.get("urls", [])

        existing_key = _find_entry_key(deps_data, name)
        if existing_key is None:
            if verbose:
                print(f"  [new]  {name} (version={version or MISSING})")
            new_entries[name] = _stub_entry(version, urls)
            changed = True
        else:
            entry = deps_data[existing_key]
            old_version = entry.get("version")
            old_urls = entry.get("urls")
            entry_updates = {}
            if old_version != (version or MISSING):
                if verbose:
                    print(f"  [upd]  {name} version: {old_version!r} → {version!r}")
                entry_updates["version"] = version if version else MISSING
                changed = True
            if urls and old_urls != urls:
                if verbose:
                    print(f"  [upd]  {name} urls updated")
                entry_updates["urls"] = urls
                changed = True
            if entry_updates:
                field_updates[existing_key] = entry_updates

    if changed:
        _write_yaml_surgical(deps_path, deps_data, field_updates, new_entries)
        if verbose:
            print(f"Wrote {deps_path}")
    else:
        if verbose:
            print(f"No changes to {deps_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--module",
        default="MODULE.bazel",
        help="Path to MODULE.bazel (default: MODULE.bazel in cwd)",
    )
    parser.add_argument(
        "--deps",
        default=None,
        help=(
            "Path to deps.yaml to update "
            "(default: <module_dir>/../bazel/deps.yaml for nested modules, "
            "or bazel/deps.yaml for the root module)"
        ),
    )
    parser.add_argument(
        "--lockfile",
        default=None,
        help="Path to MODULE.bazel.lock (default: <module>.lock next to MODULE.bazel)",
    )
    parser.add_argument(
        "--repository-locations",
        default=None,
        help=(
            "Path to repository_locations.bzl (default: "
            "<module_dir>/../bazel/repository_locations.bzl or "
            "<module_dir>/bazel/repository_locations.bzl)"
        ),
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        default=False,
        help="Skip fetching source.json URLs from registries (urls will not be updated)",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False,
        help="Suppress informational output",
    )
    return parser


def resolve_paths(args) -> tuple:
    """Return (module_path, deps_path, lockfile_path, repo_locations_path)."""
    module_path = pathlib.Path(args.module).resolve()
    module_dir = module_path.parent

    # Deps yaml: try to detect whether this is a nested module (api/) or root
    if args.deps:
        deps_path = pathlib.Path(args.deps).resolve()
    else:
        # Heuristic: if the parent dir is named 'api' or similar, look for
        # <parent>/bazel/deps.yaml, otherwise bazel/deps.yaml relative to cwd.
        candidate = module_dir / "bazel" / "deps.yaml"
        if candidate.exists() or (module_dir / "bazel").is_dir():
            deps_path = candidate
        else:
            # root module: bazel/deps.yaml relative to MODULE.bazel location
            deps_path = module_dir / "bazel" / "deps.yaml"

    # Lockfile
    if args.lockfile:
        lockfile_path = pathlib.Path(args.lockfile).resolve()
    else:
        lockfile_path = module_path.with_suffix(".bazel.lock")

    # repository_locations.bzl
    if args.repository_locations:
        repo_loc_path = pathlib.Path(args.repository_locations).resolve()
    else:
        # Try <module_dir>/bazel/repository_locations.bzl (nested api/ module)
        candidate1 = module_dir / "bazel" / "repository_locations.bzl"
        # Try <module_dir>/../bazel/repository_locations.bzl (root)
        candidate2 = module_dir.parent / "bazel" / "repository_locations.bzl"
        if candidate1.exists():
            repo_loc_path = candidate1
        elif candidate2.exists():
            repo_loc_path = candidate2
        else:
            repo_loc_path = candidate1  # will be absent, gracefully handled

    return module_path, deps_path, lockfile_path, repo_loc_path


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    verbose = not args.quiet

    module_path, deps_path, lockfile_path, repo_loc_path = resolve_paths(args)

    if verbose:
        print(f"Module:               {module_path}")
        print(f"Lockfile:             {lockfile_path}")
        print(f"Repository locations: {repo_loc_path}")
        print(f"deps.yaml:            {deps_path}")

    if not module_path.exists():
        print(f"ERROR: MODULE.bazel not found: {module_path}", file=sys.stderr)
        return 1

    if not lockfile_path.exists():
        print(f"WARNING: lockfile not found: {lockfile_path}", file=sys.stderr)
        source_json_map = {}
        ext_repo_specs = {}
    else:
        source_json_map, ext_repo_specs = parse_lockfile(lockfile_path)

    module_deps = parse_module_bazel(module_path)
    repo_locations = parse_repository_locations(repo_loc_path)

    if verbose:
        print(f"\nFound {len(module_deps)} bazel_dep entries in MODULE.bazel")
        print(f"Found {len(repo_locations)} entries in repository_locations.bzl")
        print()

    update_deps_yaml(
        deps_path,
        module_deps,
        source_json_map,
        ext_repo_specs,
        repo_locations,
        fetch_urls=not args.no_fetch,
        verbose=verbose,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
