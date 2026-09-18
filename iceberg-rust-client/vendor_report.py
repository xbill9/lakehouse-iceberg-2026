#!/usr/bin/env python3
"""Render every stored Rust run and SigV4 demonstration into one text file.

    $ python3 vendor_report.py
    wrote evidence/rust-vendor-runs.txt

No network. Counts are computed here from the run files, never typed into the
paper, and nothing but catalog names, verdicts, error text already redacted at
write time, and config key NAMES appears in the output.
"""

import glob
import json
import os
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
EV = os.path.join(HERE, "evidence")
ORDER = ["OK", "IMPLICIT", "FAILED", "NOT-ISSUED", "NOT-EXPRESSIBLE"]


def main():
    lines = ["Rust client runs, iceberg-catalog-rest 0.10.1, --storage opendal",
             "One run per catalog. Rendered by vendor_report.py from rust-run-*.json.",
             ""]
    lines.append("  %-30s %-8s %4s %8s %6s %10s %15s" % (
        "catalog", "auth", "ok", "implicit", "failed", "not-issued", "not-expressible"))
    for path in sorted(glob.glob(os.path.join(EV, "rust-run-*.json"))):
        if path.endswith(".failed.json"):
            continue
        d = json.load(open(path))
        m = d["meta"]
        c = Counter(r["verdict"] for r in d["rows"])
        lines.append("  %-30s %-8s %4d %8d %6d %10d %15d   measured %s" % (
            m["catalog"] + (" +deleg" if m.get("access_delegation_header") else "")
            + (" [%s]" % m["tag"] if m.get("tag") else ""),
            m["auth_mode"], c["OK"], c["IMPLICIT"], c["FAILED"],
            c["NOT-ISSUED"], c["NOT-EXPRESSIBLE"], m["measured_utc"]))

    for path in sorted(glob.glob(os.path.join(EV, "rust-run-*-no-tls.json"))):
        d = json.load(open(path))
        err = next((r.get("error") for r in d["rows"] if r["verdict"] == "FAILED"), None)
        lines.append("")
        lines.append("  [no-tls] %s: binary built without a reqwest TLS feature, "
                     "as iceberg-catalog-rest 0.10.1 declares it" % d["meta"]["catalog"])
        lines.append("    first error: %s" % err)
    lines += ["", "Not run: databricks-unity and snowflake-horizon, whose entries in",
              "catalogs.yaml still hold placeholder values and carry enabled: false.",
              "SigV4 catalogs are not run in this mode; see the demonstration below."]
    lines += ["", "Storage: one read of the table's metadata file through the "
              "client's own FileIO,", "after load_table. Config key names only.", ""]
    for path in sorted(glob.glob(os.path.join(EV, "rust-run-*.json"))):
        if path.endswith(".failed.json"):
            continue
        m = json.load(open(path))["meta"]
        t = m.get("storage_touch")
        if not t:
            continue
        keys = m.get("storage_fileio_config_keys") or []
        vended = [k for k in keys if k.split(".")[0] in ("s3", "gcs", "adls")
                  and not k.startswith("header.")]
        if m.get("tag"):
            continue
        lines.append("  %s%s" % (m["catalog"], (
            "   with X-Iceberg-Access-Delegation: %s as a static header"
            % m["access_delegation_header"]) if m.get("access_delegation_header") else ""))
        lines.append("    fileio config keys: %s" % ", ".join(keys))
        lines.append("    storage credential keys among them: %s"
                     % (", ".join(vended) if vended else "none"))
        if t.get("ok"):
            det = t["detail"]
            lines.append("    read: ok, scheme %s, %d bytes, %d ms"
                         % (det["scheme"], det["bytes_read"], det["read_ms"]))
        else:
            lines.append("    read: FAILED after %d ms" % t["ms"])
            lines.append("    error: %s" % t["error"])
        lines.append("")

    lines += ["SigV4 demonstration: one signature for GET /v1/config, carried by",
              "the crate as static header.* properties on every request.", ""]
    for path in sorted(glob.glob(os.path.join(EV, "rust-sigv4-demo-*.json"))):
        d = json.load(open(path))
        m = d["meta"]
        # storage_read_metadata is a second load_table, so it is counted apart
        # from paper 1's probes rather than inflating them.
        rows = [r for r in d["rows"] if r.get("ok") is not None
                and r["probe"] != "storage_read_metadata"]
        st = next((r for r in d["rows"] if r["probe"] == "storage_read_metadata"), None)
        refused = sum(1 for r in rows if r.get("ok") is False
                      and "InvalidSignatureException" in (r.get("error") or ""))
        other = sum(1 for r in rows if r.get("ok") is True)
        lines.append("  %s   measured %s" % (m["catalog"], m["measured_utc"]))
        lines.append("    through the crate: %d of %d issued probes refused with "
                     "InvalidSignatureException, %d succeeded"
                     % (refused, len(rows), other))
        if st is not None:
            lines.append("    storage read: %s" % (
                "refused at load_table, InvalidSignatureException"
                if "InvalidSignatureException" in (st.get("error") or "")
                else ("ok" if st.get("ok") else "failed")))
        for k, v in (m.get("replay_outside_crate") or {}).items():
            lines.append("    replay, %s: %s" % (k, v))
        lines.append("")

    out = os.path.join(EV, "rust-vendor-runs.txt")
    with open(out, "w") as fh:
        fh.write("\n".join(lines).rstrip() + "\n")
    print("wrote %s" % os.path.relpath(out, HERE))


if __name__ == "__main__":
    main()
