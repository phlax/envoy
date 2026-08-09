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
    bazel run //tools/dependency:update_deps

    # Update api module deps
    bazel run //tools/dependency:update_deps -- --module api/MODULE.bazel --deps api/bazel/deps.yaml
"""

import argparse
import ast
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

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

_WHITESPACE = " \t\r\n"


def _skip_ignored(text: str, index: int) -> int:
    while index < len(text):
        if text[index] in _WHITESPACE:
            index += 1
            continue
        if text[index] == "#":
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        break
    return index


def _consume_string(text: str, index: int) -> int:
    quote = text[index]
    index += 1
    while index < len(text):
        if text[index] == "\\":
            index += 2
            continue
        if text[index] == quote:
            return index + 1
        index += 1
    raise ValueError("unterminated string literal")


def _find_matching_paren(text: str, open_index: int) -> int:
    depth = 0
    index = open_index
    while index < len(text):
        char = text[index]
        if char in "\"'":
            index = _consume_string(text, index)
            continue
        if char == "#":
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise ValueError("unmatched '('")


def _iter_call_bodies(text: str, call_name: str):
    index = 0
    while index < len(text):
        char = text[index]
        if char in "\"'":
            index = _consume_string(text, index)
            continue
        if char == "#":
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        if char.isalpha() or char == "_":
            start = index
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                index += 1
            ident = text[start:index]
            if ident != call_name:
                continue
            index = _skip_ignored(text, index)
            if index >= len(text) or text[index] != "(":
                continue
            end = _find_matching_paren(text, index)
            yield text[index + 1:end]
            index = end + 1
            continue
        index += 1


def _split_top_level_items(text: str) -> list[str]:
    items = []
    start = 0
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in "\"'":
            index = _consume_string(text, index)
            continue
        if char == "#":
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "," and depth == 0:
            item = text[start:index].strip()
            if item:
                items.append(item)
            start = index + 1
        index += 1
    tail = text[start:].strip()
    if tail:
        items.append(tail)
    return items


def _split_assignment(text: str) -> tuple[str, str] | tuple[None, None]:
    depth = 0
    index = 0
    while index < len(text):
        char = text[index]
        if char in "\"'":
            index = _consume_string(text, index)
            continue
        if char == "#":
            while index < len(text) and text[index] != "\n":
                index += 1
            continue
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
        elif char == "=" and depth == 0:
            return text[:index].strip(), text[index + 1:].strip()
        index += 1
    return None, None


def _parse_starlark_value(text: str, index: int):
    index = _skip_ignored(text, index)
    if index >= len(text):
        raise ValueError("expected value")
    char = text[index]
    if text.startswith("dict", index) and index + 4 < len(text) and text[index + 4] == "(":
        index += 5
        result = {}
        while True:
            index = _skip_ignored(text, index)
            if index >= len(text):
                raise ValueError("unterminated dict()")
            if text[index] == ")":
                return result, index + 1
            key_start = index
            if not (text[index].isalpha() or text[index] == "_"):
                raise ValueError("expected dict() key")
            index += 1
            while index < len(text) and (text[index].isalnum() or text[index] == "_"):
                index += 1
            key = text[key_start:index]
            index = _skip_ignored(text, index)
            if index >= len(text) or text[index] != "=":
                raise ValueError("expected '=' in dict()")
            value, index = _parse_starlark_value(text, index + 1)
            result[key] = value
            index = _skip_ignored(text, index)
            if index < len(text) and text[index] == ",":
                index += 1
                continue
            if index < len(text) and text[index] == ")":
                return result, index + 1
            raise ValueError("expected ',' or ')' in dict()")
    if char == "[":
        index += 1
        result = []
        while True:
            index = _skip_ignored(text, index)
            if index >= len(text):
                raise ValueError("unterminated list")
            if text[index] == "]":
                return result, index + 1
            value, index = _parse_starlark_value(text, index)
            result.append(value)
            index = _skip_ignored(text, index)
            if index < len(text) and text[index] == ",":
                index += 1
                continue
            if index < len(text) and text[index] == "]":
                return result, index + 1
            raise ValueError("expected ',' or ']' in list")
    if char in "\"'":
        end = _consume_string(text, index)
        return ast.literal_eval(text[index:end]), end
    if char.isdigit() or char == "-":
        end = index + 1
        while end < len(text) and text[end] not in _WHITESPACE + ",)]}":
            end += 1
        return ast.literal_eval(text[index:end]), end
    if char.isalpha() or char == "_":
        start = index
        index += 1
        while index < len(text) and (text[index].isalnum() or text[index] == "_"):
            index += 1
        ident = text[start:index]
        if ident == "True":
            return True, index
        if ident == "False":
            return False, index
        if ident == "None":
            return None, index
        return ident, index
    raise ValueError(f"unsupported Starlark value starting with {char!r}")


def parse_module_bazel(path: pathlib.Path) -> dict:
    """Return {module_name: version_str} for every bazel_dep in MODULE.bazel.

    If a bazel_dep has no version attribute the value will be ``""``."""
    text = path.read_text()
    deps = {}
    for block in _iter_call_bodies(text, "bazel_dep"):
        attrs = {}
        for item in _split_top_level_items(block):
            key, value_text = _split_assignment(item)
            if key is None:
                continue
            value, _ = _parse_starlark_value(value_text, 0)
            attrs[key] = value
        name = attrs.get("name", "")
        if not name:
            continue
        version = attrs.get("version", "")
        deps[name] = version
    return deps


def parse_lockfile(path: pathlib.Path) -> dict:
    """Return ({module_name: source_json_url}, extension_repo_specs) from lockfile.

    Registry module entries in current lockfiles expose ``source.json`` locations
    but not the final upstream archive URL, so network-free callers can only
    use this map for optional follow-up fetching. Non-module extension repos
    still expose their resolved ``urls`` and ``version`` inline.
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
    m = re.search(r"\bREPOSITORY_LOCATIONS_SPEC\b\s*=", text)
    if not m:
        return {}
    try:
        parsed, _ = _parse_starlark_value(text, m.end())
    except (SyntaxError, ValueError):
        print(f"WARNING: failed to parse {path}", file=sys.stderr)
        return {}
    for name, spec in parsed.items():
        version = spec.get("version", "")
        raw_urls = spec.get("urls", [])
        urls = [u.replace("{version}", version) for u in raw_urls if isinstance(u, str)]
        parsed[name] = {"version": version, "urls": urls}
    return parsed


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
    fetch_urls: bool = False,
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
    ext_fallback_norms = {_normalize_name(n) for n in filtered_repo_locations}
    ext_fallback_norms.update(_normalize_name(n) for n in deps_data)
    filtered_ext_repo_specs = {
        n: v
        for n, v in ext_repo_specs.items()
        if _normalize_name(n) not in module_norms and _normalize_name(n) in ext_fallback_norms
    }
    all_names = set(module_deps) | set(filtered_repo_locations) | set(filtered_ext_repo_specs)

    # Collect changes: updates to existing entries and completely new entries
    field_updates: dict = {}   # {existing_key: {field: value}}
    new_entries: dict = {}     # {name: full_entry_dict}
    changed = False

    for name in sorted(all_names):
        version = ""
        urls: list = []

        if name in module_deps:
            version = module_deps[name]
            if fetch_urls and name in source_json_map:
                src_url = fetch_source_json_url(source_json_map[name])
                if src_url:
                    urls = [src_url]
                elif verbose:
                    print(
                        f"  [warn] could not resolve source.json for {name}",
                        file=sys.stderr,
                    )
            elif not fetch_urls and name in source_json_map and verbose:
                print(
                    f"  [warn] {name} urls not updated offline; "
                    "re-run with --fetch-registry to resolve source.json",
                    file=sys.stderr,
                )
        elif name in filtered_repo_locations:
            spec = filtered_repo_locations[name]
            version = spec.get("version", "")
            urls = spec.get("urls", [])
        elif name in filtered_ext_repo_specs:
            spec = filtered_ext_repo_specs[name]
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
        help="Path to MODULE.bazel relative to the workspace root",
    )
    parser.add_argument(
        "--deps",
        default=None,
        help=(
            "Path to deps.yaml to update "
            "(default: bazel/deps.yaml for the root module, or api/bazel/deps.yaml "
            "for api/MODULE.bazel)"
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
            "Path to repository_locations.bzl relative to the workspace root "
            "(default: bazel/repository_locations.bzl or "
            "api/bazel/repository_locations.bzl)"
        ),
    )
    parser.add_argument(
        "--fetch-registry",
        action="store_true",
        default=False,
        help=(
            "Resolve module urls by fetching source.json from registries recorded in "
            "the lockfile. This is non-hermetic and disabled by default."
        ),
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        default=False,
        help="Suppress informational output",
    )
    return parser


def _resolve_workspace_path(workspace_root: pathlib.Path, path: str | None) -> pathlib.Path | None:
    if path is None:
        return None
    candidate = pathlib.Path(path)
    if candidate.is_absolute():
        return candidate
    return workspace_root / candidate


def resolve_paths(args, workspace_root: pathlib.Path) -> tuple:
    """Return (module_path, deps_path, lockfile_path, repo_locations_path)."""
    module_path = _resolve_workspace_path(workspace_root, args.module)
    module_dir = module_path.parent

    if args.deps:
        deps_path = _resolve_workspace_path(workspace_root, args.deps)
    elif module_dir == workspace_root / "api":
        deps_path = workspace_root / "api" / "bazel" / "deps.yaml"
    else:
        deps_path = workspace_root / "bazel" / "deps.yaml"

    if args.lockfile:
        lockfile_path = _resolve_workspace_path(workspace_root, args.lockfile)
    else:
        lockfile_path = module_path.with_suffix(".bazel.lock")

    if args.repository_locations:
        repo_loc_path = _resolve_workspace_path(workspace_root, args.repository_locations)
    elif module_dir == workspace_root / "api":
        repo_loc_path = workspace_root / "api" / "bazel" / "repository_locations.bzl"
    else:
        repo_loc_path = workspace_root / "bazel" / "repository_locations.bzl"

    return module_path, deps_path, lockfile_path, repo_loc_path


def main(argv=None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    verbose = not args.quiet
    workspace_directory = os.environ.get("BUILD_WORKSPACE_DIRECTORY")
    if not workspace_directory:
        print(
            "ERROR: BUILD_WORKSPACE_DIRECTORY is not set. "
            "Run this tool via `bazel run //tools/dependency:update_deps` so it can "
            "update files in the real workspace.",
            file=sys.stderr,
        )
        return 1
    workspace_root = pathlib.Path(workspace_directory).resolve()

    module_path, deps_path, lockfile_path, repo_loc_path = resolve_paths(args, workspace_root)

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
        fetch_urls=args.fetch_registry,
        verbose=verbose,
    )

    return 0


if __name__ == "__main__":
    sys.exit(main())
