from test_leads import payload


def test_invalid_http_input_returns_safe_422_not_500(client):
    response = client.post("/api/crm/leads", json=payload(email=123))

    assert response.status_code == 422
    body = response.json()
    assert "detail" in body
    assert "AttributeError" not in str(body)


def test_punctuation_only_phone_returns_safe_422(client):
    response = client.post("/api/crm/leads", json=payload(email=None, phone="+++++++"))
    assert response.status_code == 422


def test_crm_contract_replay_and_conflict_responses(client):
    request = payload()
    created = client.post("/api/crm/leads", json=request)
    assert created.status_code == 201
    assert created.json()["intake_state"] == "created"

    replayed = client.post("/api/crm/leads", json=request)
    assert replayed.status_code == 200
    assert replayed.json()["intake_state"] == "replayed"
    assert replayed.json()["crm_lead_id"] == created.json()["crm_lead_id"]

    changed = {
        **request,
        "original_message": "Different message",
        "normalized_message": "Different message",
    }
    conflict = client.post("/api/crm/leads", json=changed)
    assert conflict.status_code == 409
    assert "different lead data" in conflict.json()["detail"]
