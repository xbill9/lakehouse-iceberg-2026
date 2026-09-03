#!/usr/bin/env python3
"""Run SQL against the Databricks SQL warehouse (statement execution API)."""
import os, sys, time, requests

HOST = "https://DATABRICKS_WORKSPACE.cloud.databricks.com"
WAREHOUSE = "DATABRICKS_WAREHOUSE_ID"
TOKEN = os.environ.get("DATABRICKS_TOKEN") or open(".secrets/databricks_token").read().strip()
HDR = {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}


def run(sql, wait=120):
    r = requests.post(HOST + "/api/2.0/sql/statements",
                      headers=HDR,
                      json={"statement": sql, "warehouse_id": WAREHOUSE,
                            "wait_timeout": "50s", "on_wait_timeout": "CONTINUE"},
                      timeout=120)
    b = r.json()
    sid = b.get("statement_id")
    deadline = time.time() + wait
    while b.get("status", {}).get("state") in ("PENDING", "RUNNING") and time.time() < deadline:
        time.sleep(3)
        b = requests.get(HOST + "/api/2.0/sql/statements/" + sid, headers=HDR, timeout=60).json()
    st = b.get("status", {})
    return st.get("state"), st.get("error", {}).get("message", ""), b


if __name__ == "__main__":
    state, err, b = run(sys.argv[1])
    print(state, err[:300] if err else "")
    d = (b.get("result") or {}).get("data_array")
    if d:
        for row in d[:20]:
            print("  ", row)
