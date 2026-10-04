import os, tempfile
os.environ.update(AI_MODE="mock", DB_PATH=tempfile.mktemp(suffix=".db"), UPLOAD_DIR=tempfile.mkdtemp())
from fastapi.testclient import TestClient
import main, ai_service as ai

client = TestClient(main.app)

def create_order(lang="en", name="Priya"):
    return client.post("/api/orders", json={"name": name, "lang": lang}).json()["order_id"]

def send_msg(oid, sender, text):
    return client.post(f"/api/orders/{oid}/message", json={"sender": sender, "text": text}).json()

def test_real_world_multi_dish_order():
    oid = create_order("en", "Anand")
    res = send_msg(oid, "customer", "Hi, I need 4 meals tomorrow. One meal must have no dairy or milk. Deliver to Flat 302, Sunshine Apartments, Indiranagar after 7pm.")
    assert res["quantity"] == 4
    assert res["delivery"]["after"] == "19:00"
    assert "Sunshine Apartments" in res["delivery"]["address"]
    assert any(a["ingredient"] == "dairy" for a in res["allergies"])
    assert res["allergies"][0]["applies_to"] == "Meal #1"
    assert len(res["agent_traces"]) > 0

def test_hindi_multilingual_order():
    oid = create_order("hi", "Rahul")
    res = send_msg(oid, "customer", "नमस्ते, मुझे कल तीन थाली चाहिए। दादी के लिए एक भोजन नरम होना चाहिए।")
    assert res["quantity"] == 3
    assert res["customer"]["lang"] == "hi"
    assert any(s["requirement"] == "soft food" for s in res["special"])
    assert any(s["recipient"] == "grandmother" for s in res["special"])

def test_order_cancellation():
    oid = create_order("en", "Kiran")
    send_msg(oid, "customer", "Two meals tomorrow please.")
    res = send_msg(oid, "customer", "Please cancel my order.")
    assert res["status"] == "CANCELLED"
    events = [e["type"] for e in res["events"]]
    assert "ORDER_CANCELLED" in events

def test_customer_status_inquiry():
    oid = create_order("en", "Deepa")
    send_msg(oid, "customer", "Two meals tomorrow.")
    res = send_msg(oid, "customer", "What is the status of my order?")
    assert any("currently RECEIVED" in m["text"] for m in res["messages"] if m["who"].startswith("AI"))

def test_agents_metadata_endpoint():
    res = client.get("/api/agents").json()
    assert len(res) == 3
    agent_ids = [a["id"] for a in res]
    assert "customer_agent" in agent_ids
    assert "kitchen_agent" in agent_ids
    assert "delivery_agent" in agent_ids

def test_health_endpoint():
    res = client.get("/api/health").json()
    assert "ai_mode" in res
    assert "providers" in res
    assert "agents" in res

def test_cancellation_blocked_when_packed():
    oid = create_order("en", "Vijay")
    send_msg(oid, "customer", "Two meals tomorrow.")
    send_msg(oid, "owner", "Confirmed.")
    client.post(f"/api/orders/{oid}/ack")
    for _ in range(4):
        client.post(f"/api/orders/{oid}/advance")
    # Now in PACKED status
    res = send_msg(oid, "customer", "I want to cancel now.")
    assert res["status"] == "PACKED"
    events = [e["type"] for e in res["events"]]
    assert "CANCEL_BLOCKED" in events

def test_image_upload_mock_flow():
    # Mock mode cannot read photos: it must attach the image and ask for typed details, NOT invent a quantity.
    oid = create_order("en", "Sunil")
    import io; from PIL import Image
    buf = io.BytesIO(); Image.new("RGB", (8, 8), "white").save(buf, "PNG"); fake_png = buf.getvalue()
    res = client.post(f"/api/orders/{oid}/upload", data={"sender": "customer"}, files={"file": ("menu.png", fake_png, "image/png")}).json()
    assert res["quantity"] == 0
    events = [e["type"] for e in res["events"]]
    assert "IMAGE_NOT_READ" in events and "IMAGE_PARSED" not in events
    assert res["attachments"] and res["attachments"][0]["kind"] == "image"

def test_audio_upload_mock_flow():
    oid = create_order("en", "Kavya")
    fake_audio = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00"
    res = client.post(f"/api/orders/{oid}/upload", data={"sender": "customer"}, files={"file": ("voice.ogg", fake_audio, "audio/ogg")}).json()
    assert res["quantity"] == 3
    events = [e["type"] for e in res["events"]]
    assert "VOICE_TRANSCRIBED" in events

def test_quantity_reduction_and_waste_alert():
    oid = create_order("en", "Meera")
    send_msg(oid, "customer", "Three meals tomorrow.")
    send_msg(oid, "owner", "Confirmed.")
    client.post(f"/api/orders/{oid}/ack")  # kitchen sheet set to 3
    res = send_msg(oid, "customer", "Please reduce meals to 2.")
    assert res["quantity"] == 2
    events = [e["type"] for e in res["events"]]
    assert "QUANTITY_REDUCED" in events
    assert any("Quantity reduced" in a[1] or "Quantity changed" in a[1] for a in res["alerts"])

def test_quantity_deletion_to_zero():
    oid = create_order("en", "Arjun")
    send_msg(oid, "customer", "Two meals tomorrow.")
    res = send_msg(oid, "customer", "Please delete all meals.")
    assert res["quantity"] == 0
    events = [e["type"] for e in res["events"]]
    assert "ALL_MEALS_REMOVED" in events

def test_missing_address_warning_on_first_message():
    oid = create_order("en", "Rohit")
    res = send_msg(oid, "customer", "Two meals tomorrow. One must have no peanuts. Deliver after six.")
    assert "delivery address" in res["missing_details"]
    events = [e["type"] for e in res["events"]]
    assert "DETAILS_INCOMPLETE" in events
    assert any("Delivery Address Required" in m["text"] for m in res["messages"] if m["who"].startswith("AI"))

def test_missing_quantity_warning_on_first_message():
    oid = create_order("en", "Sana")
    res = send_msg(oid, "customer", "Deliver to 12 MG Road tomorrow please.")
    assert "meal quantity" in res["missing_details"]
    assert any("Meal Quantity Required" in m["text"] for m in res["messages"] if m["who"].startswith("AI"))

def test_multilingual_voice_notes_telugu():
    oid = create_order("te", "రమేష్")
    fake_audio = b"OggS\x00\x02\x00\x00\x00\x00\x00\x00\x00\x00"
    res = client.post(f"/api/orders/{oid}/upload", data={"sender": "customer", "lang": "te"}, files={"file": ("voice.ogg", fake_audio, "audio/ogg")}).json()
    assert res["quantity"] == 2
    assert res["customer"]["lang"] == "te"
    events = [e["type"] for e in res["events"]]
    assert "VOICE_TRANSCRIBED" in events

def test_direct_quantity_endpoint():
    oid = create_order("en", "Tara")
    send_msg(oid, "customer", "Two meals tomorrow.")
    res1 = client.post(f"/api/orders/{oid}/quantity", json={"action": "increase"}).json()
    assert res1["quantity"] == 3
    res2 = client.post(f"/api/orders/{oid}/quantity", json={"action": "decrease"}).json()
    assert res2["quantity"] == 2

def test_analytics_endpoint():
    res = client.get("/api/analytics").json()
    assert "total_orders" in res
    assert "active_orders" in res
    assert "total_meals" in res
    assert "language_distribution" in res
    assert res["total_orders"] > 0

def test_normalized_messages_and_events_endpoints():
    oid = create_order("en", "Vikram")
    send_msg(oid, "customer", "Two meals tomorrow to 12 MG Road.")
    msgs = client.get(f"/api/orders/{oid}/messages").json()
    assert len(msgs) >= 1
    evts = client.get(f"/api/orders/{oid}/events").json()
    assert len(evts) >= 1
    assert any(e["type"] == "ORDER_CREATED" for e in evts)

def test_system_reset_and_seed_endpoints():
    # Seed 3 enterprise demo orders
    seed_res = client.post("/api/seed").json()
    assert seed_res["status"] == "ok"
    assert len(seed_res["seeded_orders"]) == 3
    
    # Check that orders are present
    orders = client.get("/api/orders").json()
    assert len(orders) >= 3
    
    # Export system snapshot
    export_res = client.get("/api/export").json()
    assert export_res["system"] == "CulinaryOS Autonomous Control Tower"
    assert export_res["orders_count"] >= 3
    assert len(export_res["normalized_messages"]) > 0
    assert len(export_res["normalized_events"]) > 0
    
    # Reset system to blank slate
    reset_res = client.post("/api/reset").json()
    assert reset_res["status"] == "ok"
    orders_after_reset = client.get("/api/orders").json()
    assert len(orders_after_reset) == 0

def test_static_files_serving():
    html_res = client.get("/")
    assert html_res.status_code == 200
    assert "CulinaryOS" in html_res.text
    
    css_res = client.get("/static/css/styles.css")
    assert css_res.status_code == 200
    assert "CulinaryOS" in css_res.text

    api_js_res = client.get("/static/js/api.js")
    assert api_js_res.status_code == 200
    assert "API" in api_js_res.text

    voice_js_res = client.get("/static/js/voice.js")
    assert voice_js_res.status_code == 200
    assert "VoiceStudio" in voice_js_res.text

    app_js_res = client.get("/static/js/app.js")
    assert app_js_res.status_code == 200
    assert "App" in app_js_res.text

def test_sender_resilience_and_autocreate():
    # 1. Capitalized "Customer" should not fail with "bad sender"
    oid = create_order("en", "Ananya")
    res1 = client.post(f"/api/orders/{oid}/message", json={"sender": "Customer", "text": "Two meals tomorrow."})
    assert res1.status_code == 200
    assert res1.json()["quantity"] == 2

    # 2. Case variations and descriptive roles
    res2 = client.post(f"/api/orders/{oid}/message", json={"sender": "CUSTOMER (Voice)", "text": "Make it 3 meals."})
    assert res2.status_code == 200
    assert res2.json()["quantity"] == 3

    # 3. Message sent to non-existent ID auto-creates order seamlessly
    new_oid = "ORD-AUTO-999"
    res3 = client.post(f"/api/orders/{new_oid}/message", json={"sender": "customer", "text": "4 meals to 10 MG Road."})
    assert res3.status_code == 200
    assert res3.json()["order_id"] == new_oid
    assert res3.json()["quantity"] == 4


