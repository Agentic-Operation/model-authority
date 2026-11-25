#!/usr/bin/env python3
"""Model Management Authority — reference implementation of the record contract in
spec/annexes/model-authority-record.schema.json (Spec-444 §2.2).

Stdlib-only HTTP service. Endpoints (base /v1):
  POST   /models                 register a model record (schema-validated; 201 / 422)
  GET    /models/{model_id}      latest approved record
  GET    /models/{model_id}/versions/{version}
  POST   /models/{model_id}/{version}/deprecate   deprecate a version -> triggers re-certification callbacks
  POST   /resolve                {"model_ref": "churn-scorer@2.3.1"} -> pinned record (id+version+cid)
                                   used by Spec-444 scaffold/deploy to resolve model_bindings
  POST   /webhooks               register a re-certification callback URL (called on deprecate/re-register)
"""
import argparse
import json
import re
import subprocess
import sys
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlparse

import os
SCHEMA = Path(os.environ.get("SPEC444_ANNEXES", str(Path(__file__).resolve().parents[2] / "annexes"))) / "model-authority-record.schema.json"
CID = re.compile(r"^sha256:[a-f0-9]{64}$")


class Store:
    def __init__(self, path=None):
        self.models = {}   # model_id -> {version -> record}
        self.webhooks = []
        self.path = path
        if path and Path(path).exists():
            d = json.load(open(path))
            for m in d.get("models", []):
                self.models.setdefault(m["model_id"], {})[m["version"]] = m
            self.webhooks = d.get("webhooks", [])

    def put(self, rec):
        self.models.setdefault(rec["model_id"], {})[rec["version"]] = rec
        if self.path:
            json.dump({"models": [m for vs in self.models.values() for m in vs.values()],
                       "webhooks": self.webhooks}, open(self.path, "w"), indent=2)

    def latest_approved(self, mid):
        vs = {v: r for v, r in self.models.get(mid, {}).items() if r.get("status", "approved") == "approved"}
        return vs[max(vs)] if vs else None

    def notify(self, event, rec):
        for url in self.webhooks:
            try:
                req = urllib.request.Request(url, data=json.dumps({"event": event, "model": rec}).encode(),
                                             headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=3)
            except Exception:  # noqa: BLE001 - callbacks are best-effort
                pass


def validate_record(rec):
    errs = []
    try:
        import jsonschema
        jsonschema.validate(rec, json.load(open(SCHEMA)))
    except ImportError:
        for k in ("model_id", "uuid", "version", "cid", "integrity_wrapper", "provenance", "eval_evidence", "policy"):
            if k not in rec:
                errs.append(f"missing {k}")
        if not CID.match(rec.get("cid", "")):
            errs.append("bad cid")
    except Exception as e:  # noqa: BLE001
        errs.append(str(e))
    return errs


class Handler(BaseHTTPRequestHandler):
    store: Store = None

    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    def log_message(self, *a):
        pass

    def do_GET(self):
        p = urlparse(self.path).path.strip("/").split("/")
        if len(p) >= 3 and p[:2] == ["v1", "models"]:
            rec = self.store.latest_approved(p[2])
            if not rec:
                return self._send(404, {"error": "not found"})
            if len(p) == 5 and p[3] == "versions":
                rec = self.store.models[p[2]].get(p[4])
                return self._send(200, rec) if rec else self._send(404, {"error": "version not found"})
            return self._send(200, rec)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        p = urlparse(self.path).path.strip("/").split("/")
        if p == ["v1", "models"]:
            rec = self._body()
            errs = validate_record(rec)
            if errs:
                return self._send(422, {"violations": errs})
            rec.setdefault("status", "approved")
            self.store.put(rec)
            self.store.notify("model.registered", rec)
            return self._send(201, {"model_id": rec["model_id"], "version": rec["version"], "cid": rec["cid"]})
        if p == ["v1", "resolve"]:
            ref = self._body().get("model_ref", "")
            mid, _, ver = ref.partition("@")
            rec = self.store.models.get(mid, {}).get(ver) if ver else self.store.latest_approved(mid)
            if not rec or rec.get("status") != "approved":
                return self._send(404, {"error": f"no approved record for {ref!r}"})
            return self._send(200, {"model_id": rec["model_id"], "version": rec["version"], "cid": rec["cid"],
                                    "risk_class": rec["policy"]["risk_class"],
                                    "approved_environments": rec["policy"]["approved_environments"]})
        if len(p) == 5 and p[:2] == ["v1", "models"] and p[4] == "deprecate":
            rec = self.store.models.get(p[2], {}).get(p[3])
            if not rec:
                return self._send(404, {"error": "not found"})
            rec["status"] = "deprecated"
            self.store.put(rec)
            self.store.notify("model.deprecated", rec)   # triggers agent re-validation + autonomy re-cert (C19)
            return self._send(200, {"deprecated": f"{p[2]}@{p[3]}"})
        if p == ["v1", "webhooks"]:
            self.store.webhooks.append(self._body()["url"])
            if self.store.path:
                json.dump({"models": [m for vs in self.store.models.values() for m in vs.values()],
                           "webhooks": self.store.webhooks}, open(self.store.path, "w"), indent=2)
            return self._send(201, {"webhooks": self.store.webhooks})
        return self._send(404, {"error": "not found"})


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--store", default=None)
    a = ap.parse_args()
    Handler.store = Store(a.store)
    print(f"model authority listening on :{a.port}")
    HTTPServer(("0.0.0.0", a.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
