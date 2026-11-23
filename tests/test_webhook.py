import pytest
from fastapi.testclient import TestClient

from auto_ocr import webhook

GROUP = "120363431318894759@g.us"


def event(message_id="ABC123", group=GROUP, kind="imageMessage", name="messages.upsert"):
    return {
        "event": name,
        "data": {
            "key": {"remoteJid": group, "id": message_id},
            "messageType": kind,
            "messageTimestamp": 1795242263,
            "message": {"base64": "aGk="},
        },
    }


@pytest.fixture
def post(monkeypatch):
    handled = []
    monkeypatch.setenv("WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("WHATSAPP_GROUP_ID", GROUP)
    monkeypatch.setattr(webhook, "handle", lambda data: handled.append(data["key"]["id"]))
    monkeypatch.setattr(webhook, "seen", set())
    monkeypatch.setattr(webhook.log, "handlers", [])  # keep test events out of the real log file
    client = TestClient(webhook.app)

    def send(body, secret="s3cret"):
        reply = client.post("/whatsapp", json=body, headers={"x-webhook-secret": secret})
        return reply.status_code, reply.json().get("status"), handled

    return send


def test_only_a_photo_from_our_group_is_read_and_only_once(post):
    assert post(event(), secret="wrong")[0] == 401
    assert post(event(group="999@g.us"))[1] == "ignored"
    assert post(event(kind="conversation"))[1] == "ignored"
    assert post(event(name="messages.update"))[1] == "ignored"
    assert post({"junk": 1})[1] == "ignored"
    assert post(event())[1] == "accepted"
    assert post(event()) == (200, "duplicate", ["ABC123"])
