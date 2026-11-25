import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

SRV = Path(__file__).resolve().parents[1] / "src" / "model_authority" / "model_authority.py"

REC = {"model_id": "churn-scorer", "uuid": "11111111-4111-8111-a111-111111111111", "version": "2.3.1",
       "cid": "sha256:" + "1" * 64,
       "integrity_wrapper": {"signature_type": "Sigstore-OIDC", "issuer": "https://github.com/login/oauth", "transparency_log": "https://rekor.sigstore.dev"},
       "provenance": {"training_data": "loyalty-events-2025", "pipeline": "churn-train v3"},
       "eval_evidence": {"benchmarks": [{"name": "tau2-Bench retail subset", "version": "1.2", "score": 0.71}]},
       "policy": {"license": "Apache-2.0", "risk_class": "medium", "allowed_use": "churn scoring", "approved_environments": ["dev", "stage", "prod"]}}


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    proc = subprocess.Popen([sys.executable, str(SRV), "--port", "8498", "--store", str(tmp_path_factory.mktemp("s") / "m.json")],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    yield "http://localhost:8498"
    proc.terminate()


def post(url, obj):
    req = urllib.request.Request(url, data=json.dumps(obj).encode(), headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req)


def test_register_resolve_deprecate(server):
    assert post(f"{server}/v1/models", REC).status == 201
    r = json.loads(post(f"{server}/v1/resolve", {"model_ref": "churn-scorer@2.3.1"}).read())
    assert r["cid"] == REC["cid"] and r["risk_class"] == "medium"
    assert post(f"{server}/v1/models/churn-scorer/2.3.1/deprecate", {}).status == 200
    import urllib.error
    with pytest.raises(urllib.error.HTTPError):
        post(f"{server}/v1/resolve", {"model_ref": "churn-scorer@2.3.1"})
