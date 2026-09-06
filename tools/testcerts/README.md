# Test certificate generator

`//tools/testcerts:gen` produces the certificate fixtures used by Envoy's
tests. It replaces the `certs.sh` scripts that used to shell out to the OpenSSL
CLI (and, for the expired integration certificate, to
`docker run ... faketime`).

It links BoringSSL directly rather than going through Envoy's `//bazel:crypto`
label flag, so the fixtures it emits do not depend on which TLS provider Envoy
itself is built against.

Three directories are generated from it:

| Directory | Spec |
| --- | --- |
| `test/common/tls/test_data` | [`certs.spec`](../../test/common/tls/test_data/certs.spec) |
| `test/common/tls/ocsp/test_data` | [`certs.spec`](../../test/common/tls/ocsp/test_data/certs.spec) |
| `test/config/integration/certs` | [`certs.spec`](../../test/config/integration/certs/certs.spec) |

```console
$ bazel build //test/common/tls/test_data:certs
$ ls bazel-bin/test/common/tls/test_data/
```

## Year stamping

Certificates are valid from Jan 1 of the year the build runs in, so they never
age out. The year comes from `STABLE_CERT_EPOCH_YEAR`, written by
`bazel/get_workspace_status` into `bazel-out/stable-status.txt` and picked up by
the `stamp = 1` genrule in `certs.bzl`.

Three validity modes are available:

| Mode | notBefore | notAfter |
| --- | --- | --- |
| `current` (default) | Jan 1 of the stamped year | +2 years |
| `expired` | Jan 1 2020 | Jan 1 2021 |
| `long` | Jan 1 of the stamped year | +18250 days |

Serial numbers are derived from a hash of the fixture name (or pinned in the
spec), never randomly, so CRL and OCSP entries stay consistent and repeated
builds are byte-identical for RSA fixtures.

## Spec format

An INI-like file. Each stanza is `[<kind> <name>]` followed by `key = value`
lines. Keys may repeat where noted. Blank lines and `#` comments are ignored.

### `[cert <name>]`

| Key | Meaning |
| --- | --- |
| `key` | private key file, relative to `--in-dir` (required) |
| `key_password` | password for an encrypted key |
| `cfg` | OpenSSL config supplying the subject and extensions (required) |
| `section` | config section holding the v3 extensions (default `v3_ca`) |
| `subject_section` | config section holding the subject (default `req_distinguished_name`) |
| `issuer` | name of the issuing fixture, or `self` (default `self`) |
| `validity` | `current`, `expired` or `long` (default `current`) |
| `serial` | pinned serial in hex; derived from the name if absent |
| `out` | output file name (default `<name>_cert.pem`); `none` suppresses it |
| `info_header` | emit a `*_cert_info.h` header with this name |
| `hash_header` | emit a `*_cert_hash.h` header with this name |

If the extension section is missing from the config, the certificate is emitted
as X.509 v1, matching what `openssl ca` used to do.

### `[concat <output>]`

`parts` is a comma-separated list of fixture names and/or previously written
output files, concatenated in order.

### `[crl <output>]`

`issuer` names the signing CA; `revoke` is a comma-separated list of fixtures
whose serials are revoked.

### `[p12 <output>]`

`cert` names the fixture whose certificate and key are bundled. `chain` adds
extra certificates. `password` or `password_file` set the passphrase, and
`encrypt = none` disables key/certificate encryption and MAC iteration.

### `[ocsp <output>]`

RFC 6960 responses, encoded by hand because BoringSSL has no OCSP module.
`cert`, `issuer` and `status` may repeat (once per SingleResponse).
`responder` names the signing fixture, `responder_id` is `name` or `key`, and
`next_update_days` adds a nextUpdate field. `info_header` emits the thisUpdate
and nextUpdate timestamps as constants.

### `[trust_bundle <output>]`

`domain` may repeat; each entry is `<trust domain>:<cert>[+<cert>...]:<sequence
number>` and produces a SPIFFE trust bundle entry.
