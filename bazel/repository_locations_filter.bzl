# jq filter used to derive `bzlmod_all_repository_locations` from the bzlmod
# module graph (`@envoy_mod_graph//:deps.json`) plus the `deps.yaml` metadata.
#
# Shared between the production `bzlmod_all_repository_locations` target and
# the `all_repository_locations_test` fixture target in `bazel/BUILD`, so both
# always exercise identical filter logic.
#
# The filter expects its input to be a 3-element array: `[modules, metadata1,
# metadata2]`, where `modules` maps a bzlmod module name to its resolved
# module info (e.g. `version`, `module_url`, `urls`), and `metadata1` /
# `metadata2` are merged (with `metadata2` taking precedence) to produce the
# dependency metadata (e.g. `version`, `license_url`, etc) keyed by dependency
# name.
#
# For each dependency, the corresponding module is resolved by trying, in
# order: an exact name match, stripping a `com_google_` prefix, and mapping
# underscores to dashes. If none of these match a known module, the
# dependency's metadata is kept verbatim (no `module_url` is added).
BZLMOD_ALL_REPOSITORY_LOCATIONS_FILTER = """
.
| .[0] as $modules
| .[1] as $metadata1
| .[2] as $metadata2
| ($metadata1 * $metadata2) as $metadata
| def module_source($dep):
    if $modules[$dep] then
      ($modules[$dep] + {module_name: $dep})
    elif ($dep | startswith("com_google_")) and $modules[$dep | sub("^com_google_"; "")] then
      (($dep | sub("^com_google_"; "")) as $module_name | $modules[$module_name] + {module_name: $module_name})
    else
      ($dep | gsub("_"; "-")) as $module_name
      | if $modules[$module_name] then
          ($modules[$module_name] + {module_name: $module_name})
        else null end
    end;
  def dependency_source($dep):
    module_source($dep);
  $metadata
  | keys
  | reduce .[] as $k ({};
      (dependency_source($k)) as $source
      | . + {($k): (
          (($source // {}) + ($metadata[$k] // {}))
          | .version as $ver
          | if .license_url and $ver then
              .license_url |= (
                gsub("{version}"; $ver)
                | gsub("{dash_version}"; ($ver | gsub("[.]"; "-")))
                | gsub("{underscore_version}"; ($ver | gsub("[.]"; "_")))
              )
            else . end
        )}
    )
"""
