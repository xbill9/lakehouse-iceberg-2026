# What a Rust client can reach: iceberg-rust against seven catalogs

Supports the **Rust client paper**. Paper 1 measured what seven Iceberg REST
catalogs *serve*. This measures what a *client implementation* can reach across
the same seven, with `pyiceberg` as the control.

Standalone, and deliberately not part of `iceberg-mcp-hosts/`. That paper
measures MCP tool surfaces, and the fact that one server under test happens to be
written in Rust is incidental to it. Rust is the subject here.

## What varies, and what does not

| shared, one implementation | different, on purpose |
|---|---|
| the seven catalogs, already configured | the client library |
| the fixture table, already seeded | |
| the operation set, taken from paper 1's probes | |
| the evidence and anonymisation discipline | |

    control     pyiceberg 0.12.0        Python, and what paper 1 measured with
    subject     iceberg-catalog-rest    Rust, Apache, 0.10.1 (2026-08-01)

Using paper 1's own probe list means the two papers are comparable rather than
merely adjacent: a cell that a catalog served for Python and refuses for Rust is
a client difference, because the server side is already measured.

## The finding that is already visible in the source

`evidence/rust-client-auth-surface.txt` records it, read from the published crate
rather than from documentation: the crate has **no AWS SigV4**. It supports a
bearer `token`, OAuth2 `credential` + `oauth2-server-uri` + `scope`, and static
`header.<name>` values, and its dependency list contains no AWS SDK or signing
crate.

Paper 1 measured Glue and S3 Tables as SigV4-signed. A SigV4 signature is
computed per request, so a static header cannot carry one. As shipped, two of the
seven are out of reach.

That is a reading of the source, not a result. **The paper has to demonstrate the
failure against a live endpoint**, in the same way paper 1 refused to report a
verdict it had not seen on the wire. Until then it is a hypothesis with a grep
behind it.

## What this is not

Not "Rust is missing features". The REST specification does not require SigV4;
the crate implements what the spec describes, and the two AWS catalogs layer an
AWS-specific signing requirement on top of it. The interesting sentence is about
what a portable client can assume, not about who is at fault.

## Status

Scaffolding. Auth surface read from the crate. Nothing run against a catalog yet.
