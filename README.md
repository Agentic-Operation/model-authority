# model-authority

Model Management Authority for Spec-444 §2.2 `model_bindings`. Record contract is canonical in
[agent-bootstrap-management/spec/annexes/model-authority-record.schema.json](https://github.com/Agentic-Operation/agent-bootstrap-management/blob/main/spec/annexes/model-authority-record.schema.json).

Endpoints: POST /v1/models (schema-validated), GET /v1/models/{id}[/versions/{v}],
POST /v1/resolve {"model_ref": "id@version"} → pinned id+version+CID+risk_class (CID equality with
bootstrap model_bindings enforced, cross-check C19), POST /v1/models/{id}/{v}/deprecate →
re-certification webhooks (agent re-validation + autonomy re-certification).

- Run: `python src/model_authority/model_authority.py --port 8090 --store models.json`
  (set `SPEC444_ANNEXES` to the bootstrap repo's `spec/annexes` for the schema, or rely on built-in structural checks)
- Tests: `pytest tests`
- License: Apache-2.0
