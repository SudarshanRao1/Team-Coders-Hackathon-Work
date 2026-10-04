import os, tempfile
os.environ.update(AI_MODE="mock", DB_PATH=tempfile.mktemp(suffix=".db"), UPLOAD_DIR=tempfile.mkdtemp())
from fastapi.testclient import TestClient
import main, ai_service as ai
c = TestClient(main.app)
def mk(lang="te"): return c.post("/api/orders", json={"lang": lang}).json()["order_id"]
def msg(o, w, t): return c.post(f"/api/orders/{o}/message", json={"sender": w, "text": t}).json()
def ev(s): return [e["type"] for e in s["events"]]
S1 = "Two meals tomorrow. One must have no peanuts. Deliver after six."
S3 = "Make that three. The extra meal is for my grandmother; she needs soft food."

def test_extraction_and_flow():
    o = mk(); s = msg(o, "customer", S1)
    assert s["quantity"] == 2 and s["delivery"]["after"] == "18:00"
    assert s["allergies"][0]["applies_to"] == "Meal #1"
def test_quantity_allergy_special_and_diff():
    o = mk(); msg(o, "customer", S1); msg(o, "owner", "Confirmed."); s = msg(o, "customer", S3)
    assert s["quantity"] == 3 and "QUANTITY_CHANGED" in ev(s) and s["allergies"][0]["ingredient"] == "peanuts"
    assert s["special"][0]["meal"] == 3 and s["last_diff"]["before"]["meals"] == 2
    assert s["sheet_qty"] == 2 and any("Quantity changed" in a[1] for a in s["alerts"])
def test_address_conflict_blocks_dispatch_and_resolves():
    o = mk(); msg(o, "customer", S1); msg(o, "owner", "Confirmed.")
    s = msg(o, "delivery", "There are two addresses in this conversation. Which one is current?")
    assert s["open_conflicts"] and "ADDRESS_CONFLICT_DETECTED" in ev(s)
    c.post(f"/api/orders/{o}/ack")
    for _ in range(4): assert c.post(f"/api/orders/{o}/advance").status_code == 200
    assert c.post(f"/api/orders/{o}/advance").status_code == 409  # dispatch blocked
    s = c.post(f"/api/orders/{o}/resolve", json={"address": "42 Residency Road"}).json()
    assert not s["open_conflicts"] and s["delivery"]["address"] == "42 Residency Road"
    assert c.post(f"/api/orders/{o}/advance").json()["status"] == "OUT_FOR_DELIVERY"
def test_packaging_lock_needs_allergy_ack():
    o = mk(); msg(o, "customer", S1); msg(o, "owner", "Confirmed.")
    for _ in range(2): c.post(f"/api/orders/{o}/advance")
    assert c.post(f"/api/orders/{o}/advance").status_code == 409
def test_modification_after_packed_is_blocked_then_approved():
    o = mk(); msg(o, "customer", S1); msg(o, "owner", "Confirmed."); c.post(f"/api/orders/{o}/ack")
    for _ in range(4): c.post(f"/api/orders/{o}/advance")
    s = msg(o, "customer", "Make it four"); assert s["quantity"] == 2 and "MODIFICATION_BLOCKED" in ev(s)
    s = c.post(f"/api/orders/{o}/approve").json(); assert s["quantity"] == 4
def test_multilingual_telugu_input_and_reply():
    o = mk("en"); s = msg(o, "customer", "రేపు రెండు భోజనాలు కావాలి. ఒకదాంట్లో వేరుశెనగలు ఉండకూడదు.")
    assert s["quantity"] == 2 and s["allergies"][0]["ingredient"] == "peanuts" and s["customer"]["lang"] == "te"
    s = msg(o, "owner", "Confirmed."); assert "నిర్ధారించబడింది" in s["messages"][-1]["text"]
def test_invalid_llm_output_leaves_state_intact(monkeypatch):
    o = mk(); msg(o, "customer", S1)
    monkeypatch.setenv("AI_MODE", "live"); monkeypatch.setattr(ai, "_call", lambda *a, **k: "not json")
    s = msg(o, "customer", S3); assert s["quantity"] == 2 and "AI_OUTPUT_INVALID" in ev(s)
def test_live_valid_output_is_used(monkeypatch):
    o = mk(); monkeypatch.setenv("AI_MODE", "live")
    monkeypatch.setattr(ai, "_call", lambda *a, **k: '{"intent":"ORDER_UPDATE","language":"en","changes":{"quantity":5}}')
    assert msg(o, "customer", "x")["quantity"] == 5
def test_persistence_and_audit():
    o = mk(); msg(o, "customer", S1)
    s = main.load(o); assert s["quantity"] == 2 and ev(s)[:2] == ["ORDER_THREAD_OPENED", "ORDER_CREATED"]
