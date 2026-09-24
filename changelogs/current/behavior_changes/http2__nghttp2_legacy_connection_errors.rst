Updated Envoy's legacy nghttp2 HTTP/2 codec behavior for nghttp2 >= 1.67.0. Invalid pseudo-headers,
content-length mismatches, and related HTTP messaging violations now follow upstream nghttp2 and
terminate the connection with ``GOAWAY(PROTOCOL_ERROR)`` instead of resetting only the affected
stream. As a result, ``override_stream_error_on_invalid_http_message`` is only honored by the
oghttp2 codec behind ``envoy.reloadable_features.http2_use_oghttp2``.
