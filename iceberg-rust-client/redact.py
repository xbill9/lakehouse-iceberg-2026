"""Replace anything account-shaped with a placeholder, before it reaches disk.

The evidence files in this directory are committed. A client's error text is
not written by us and is not bounded: `requests` puts the whole URL in an
HTTPError, the Rust crate puts the request in some of its messages, and a
vendor's URL carries the account, the project or the workspace.

So the rule this repository already applies to `loadTable` responses applies to
error strings too. `scrub` maps the values a run knows about onto placeholders;
`verify` refuses to write a document that still contains one of them, for the
reason check-no-identifiers.sh exists: an anonymiser that cannot fail reads
exactly like one that passed.
"""

import json
import os
from urllib.parse import quote, urlsplit


def values_for(cat, extra_env=()):
    """(literal, placeholder) pairs for one catalog's configuration.

    Longest first, so that a namespace that is a substring of a URL does not
    blank out half the URL before the URL itself is matched.
    """
    pairs = []
    url = cat.get("base_url") or ""
    if url:
        pairs.append((url.rstrip("/"), "<uri>"))
        host = urlsplit(url).netloc
        if host:
            pairs.append((host, "<host>"))
    for key, placeholder in (("warehouse", "<warehouse>"),
                             ("namespace", "<namespace>"),
                             ("table", "<table>")):
        if cat.get(key):
            pairs.append((str(cat[key]), placeholder))
    # A composite warehouse is split up in storage paths: OneLake's
    # "<workspace>/<lakehouse>" comes back as abfss://<workspace>@.../<lakehouse>/,
    # which matches neither the whole value nor its encoding. Each long
    # component is an identifier on its own.
    # ARN structure words and regions are not identifiers, and blanking them
    # makes verify() refuse a document for naming the service it probed.
    generic = {"arn", "aws", "s3tables", "glue", "bucket", "gs", "abfss",
               "https", "http"}
    for part in str(cat.get("warehouse") or "").replace(":", "/").split("/"):
        if len(part) >= 8 and part not in generic and not part.startswith(
                ("us-", "eu-", "ap-", "ca-", "sa-", "me-", "af-")):
            pairs.append((part, "<warehouse-part>"))
    # Header values carry account identifiers too: BigLake's
    # x-goog-user-project is the project id itself.
    for value in (cat.get("headers") or {}).values():
        if value:
            pairs.append((str(value), "<header>"))
    for name in extra_env:
        secret = os.environ.get(name, "")
        if secret:
            pairs.append((secret, "<secret>"))
    # Every value also travels percent-encoded, because clients put it in a
    # query string: `?warehouse=gs%3A%2F%2F<project>-...`. Matching only the
    # literal let the encoded form through on 2026-09-18 -- a GCP project id
    # and two OneLake GUIDs reached disk while verify() reported nothing.
    encoded = []
    for literal, placeholder in pairs:
        for form in (quote(literal, safe=""), quote(literal)):
            if form != literal:
                encoded.append((form, placeholder))
    pairs.extend(encoded)
    return sorted(set(pairs), key=lambda kv: -len(kv[0]))


def scrub(text, pairs):
    if not text:
        return text
    for literal, placeholder in pairs:
        text = text.replace(literal, placeholder)
    return text


def secret_env_names(cat):
    """The env vars this catalog's auth reads, whatever the auth type."""
    spec = cat.get("auth") or {}
    return [spec[k] for k in ("client_secret_env", "client_id_env", "env_var")
            if spec.get(k)]


def verify(document, pairs):
    """Raise if any literal survived into the document about to be written."""
    text = json.dumps(document)
    survived = [literal for literal, _ in pairs
                # A placeholder for an empty or one-character value would match
                # everything; those are configuration errors, not identifiers.
                if len(literal) > 3 and literal in text]
    if survived:
        raise RuntimeError(
            "refusing to write evidence: %d configured value(s) survived "
            "redaction (%s)" % (len(survived),
                                ", ".join(repr(s[:12] + "...") for s in survived)))


def _selftest():
    """Plant a value and watch it fail. A check that cannot fail reads exactly
    like a check that passes, which is how an identifier reached 33 committed
    files once already.
    """
    cat = {"base_url": "https://acct-1234.example-cloud.com/polaris/api/catalog",
           "warehouse": "MY_DB", "namespace": "probe_ns", "table": "probe_table"}
    pairs = values_for(cat)
    doc = {"error": "404 for url: %s/v1/MY_DB/namespaces/probe_ns/tables/probe_table"
                    % cat["base_url"]}
    try:
        verify(doc, pairs)
    except RuntimeError:
        pass
    else:
        raise SystemExit("selftest FAILED: verify() passed a planted identifier")

    doc["error"] = scrub(doc["error"], pairs)
    verify(doc, pairs)

    # The encoded form, which is how the warehouse actually leaked.
    cat["warehouse"] = "gs://acct-1234-bucket/a b"
    cat["headers"] = {"x-goog-user-project": "acct-1234"}
    pairs = values_for(cat)
    leak = {"error": "error sending request for url (%s/v1/config?warehouse=%s)"
                     % (cat["base_url"], quote(cat["warehouse"], safe=""))}
    try:
        verify(leak, pairs)
    except RuntimeError:
        pass
    else:
        raise SystemExit("selftest FAILED: verify() passed a percent-encoded identifier")
    leak["error"] = scrub(leak["error"], pairs)
    verify(leak, pairs)
    if "acct-1234" in leak["error"]:
        raise SystemExit("selftest FAILED: encoded identifier survived scrub")
    for literal, _ in pairs:
        if literal in doc["error"]:
            raise SystemExit("selftest FAILED: %r survived scrub" % literal)
    print("selftest ok: planted identifier caught, then scrubbed to\n  %s"
          % doc["error"])


if __name__ == "__main__":
    _selftest()
