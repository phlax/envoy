
PPC_SKIP_TARGETS = ["envoy.string_matcher.lua", "envoy.filters.http.lua", "envoy.router.cluster_specifier_plugin.lua"]

WINDOWS_SKIP_TARGETS = [
    "envoy.extensions.http.cache.file_system_http_cache",
    "envoy.extensions.http.cache_v2.file_system_http_cache",
    "envoy.filters.http.file_system_buffer",
    "envoy.filters.http.language",
    "envoy.filters.http.sxg",
    "envoy.tracers.dynamic_ot",
    "envoy.tracers.datadog",
    # Extensions that require CEL.
    "envoy.access_loggers.extension_filters.cel",
    "envoy.rate_limit_descriptors.expr",
    "envoy.filters.http.rate_limit_quota",
    "envoy.filters.http.ext_proc",
    "envoy.formatter.cel",
    "envoy.matching.inputs.cel_data_input",
    "envoy.matching.matchers.cel_matcher",
    # Wasm and RBAC extensions have a link dependency on CEL.
    "envoy.access_loggers.wasm",
    "envoy.bootstrap.wasm",
    "envoy.filters.http.wasm",
    "envoy.filters.network.wasm",
    "envoy.stat_sinks.wasm",
    # RBAC extensions have a link dependency on CEL.
    "envoy.filters.http.rbac",
    "envoy.filters.network.rbac",
    "envoy.rbac.matchers.upstream_ip_port",
]

NO_HTTP3_SKIP_TARGETS = [
    "envoy.quic.crypto_stream.server.quiche",
    "envoy.quic.deterministic_connection_id_generator",
    "envoy.quic.proof_source.filter_chain",
    "envoy.quic.server_preferred_address.fixed",
    "envoy.quic.server_preferred_address.datasource",
    "envoy.quic.connection_debug_visitor.basic",
    "envoy.quic.packet_writer.default",
]
