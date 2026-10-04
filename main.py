import os, json, sqlite3, uuid, base64, re, datetime as dt, pathlib
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Body
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
import ai_service as ai

DB = os.getenv("DB_PATH", "kitchen.db")
UP = pathlib.Path(os.getenv("UPLOAD_DIR", "uploads")); UP.mkdir(parents=True, exist_ok=True)
FLOW = ["RECEIVED", "CONFIRMED", "PREPARING", "READY_FOR_PACKAGING", "PACKAGING", "PACKED", "OUT_FOR_DELIVERY", "DELIVERED"]
LOCK = ("PACKED", "OUT_FOR_DELIVERY", "DELIVERED")
BUF = {"prep": 90, "pack": 30, "dispatch": 15}  # minutes before delivery; configurable
KIND = {"CONFIRMED": "confirmed", "PREPARING": "preparing", "PACKAGING": "packaging", "PACKED": "packed",
        "OUT_FOR_DELIVERY": "out", "DELIVERED": "delivered"}
app = FastAPI(title="Home Kitchen Autonomous Order Management Tower")
STATIC_DIR = pathlib.Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/media", StaticFiles(directory=UP), name="media")   # uploaded order images / voice notes (uuid filenames)

def now(): return dt.datetime.now()

def _c():
    c = sqlite3.connect(DB, check_same_thread=False)
    try:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")
    except Exception:
        pass
    c.execute("create table if not exists orders(id text primary key, state text)")
    c.execute("create table if not exists messages(id text primary key, order_id text, ts text, who text, text text)")
    c.execute("create table if not exists events(id text primary key, order_id text, ts text, event_type text, detail text)")
    return c

def norm(s):
    """Fill defaults so legacy / seeded / partially-written states never crash the API."""
    s.setdefault("customer", {})
    s["customer"].setdefault("name", "Customer")
    s["customer"].setdefault("phone", "+91 98765 43210")
    s["customer"].setdefault("lang", "en")
    s["customer"].setdefault("known_addresses", ["12 MG Road", "42 Residency Road"])
    s.setdefault("status", "RECEIVED")
    s.setdefault("quantity", 0)
    s.setdefault("quantity_history", [])
    s.setdefault("items", [])
    s.setdefault("special", [])
    s.setdefault("conflicts", [])
    s.setdefault("pending_approvals", [])
    s.setdefault("messages", [])
    s.setdefault("events", [])
    s.setdefault("agent_traces", [])
    s.setdefault("agent_history", [])
    s.setdefault("attachments", [])
    s.setdefault("sheet_qty", None)
    s.setdefault("delivery_assignment", None)
    s.setdefault("last_diff", None)
    s.setdefault("conf", 0)
    s.setdefault("missing_details", [])
    d = s.setdefault("delivery", {})
    d.setdefault("address", None)
    d.setdefault("after", None)
    d.setdefault("address_confirmed", bool(d.get("address")))
    s.setdefault("allergies", [])
    for a in s["allergies"]:
        a["acked"] = bool(a.get("acked") or a.get("acknowledged_by_kitchen"))
        a.setdefault("confirmed", True)
        a.setdefault("applies_to", "All meals")
    return s

def load(oid):
    c = _c()
    r = c.execute("select state from orders where id=?", (oid,)).fetchone()
    c.close()
    if not r: raise HTTPException(404, "order not found")
    return norm(json.loads(r[0]))

def save(s):
    c = _c()
    oid = s["order_id"]
    c.execute("insert or replace into orders values(?,?)", (oid, json.dumps(s, ensure_ascii=False)))
    # Rebuild the normalized audit tables from the authoritative state (no hash-based dedupe,
    # so identical messages/events are kept and restarts never create duplicates).
    c.execute("delete from messages where order_id=?", (oid,))
    c.execute("delete from events where order_id=?", (oid,))
    for i, m in enumerate(s.get("messages", [])):
        c.execute("insert into messages values(?,?,?,?,?)",
                  (f"{oid}_m{i}", oid, m.get("ts"), m.get("who"), m.get("text")))
    for i, e in enumerate(s.get("events", [])):
        c.execute("insert into events values(?,?,?,?,?)",
                  (f"{oid}_e{i}", oid, e.get("ts"), e.get("type"), e.get("detail")))
    c.commit()
    c.close()

def all_orders():
    c = _c()
    rows = c.execute("select state from orders order by rowid").fetchall()
    c.close()
    return [norm(json.loads(r[0])) for r in rows]

def ev(s, t, d=""):
    s["events"].append({"ts": now().strftime("%H:%M:%S"), "type": t, "detail": d})

def say(s, who, text, image=None):
    m = {"ts": now().strftime("%H:%M"), "who": who, "text": text}
    if image: m["image"] = image
    s["messages"].append(m)

def notify(s, kind):
    say(s, "AI → customer", ai.generate_customer_response(kind, s, s["customer"]["lang"]))

def snap(s):
    return {
        "meals": s["quantity"],
        "allergies": [f'{a["ingredient"]} ({a["applies_to"]})' for a in s["allergies"]],
        "special": [f'{x["requirement"]}' + (f' for {x["recipient"]}' if x["recipient"] else "") + (f' (Meal #{x["meal"]})' if x["meal"] else "") for x in s["special"]],
        "address": s["delivery"]["address"],
        "after": s["delivery"]["after"]
    }

def open_conflicts(s):
    return [c for c in s["conflicts"] if not c["resolved"]]

def open_address_conflict(s, options):
    if any(c["field"] == "delivery_address" and not c["resolved"] for c in s["conflicts"]): return
    s["conflicts"].append({"id": uuid.uuid4().hex[:6], "field": "delivery_address", "options": options, "severity": "HIGH", "resolved": False})
    ev(s, "ADDRESS_CONFLICT_DETECTED", " vs ".join(options))
    notify(s, "address_q")

def apply(s, ex, force=False):
    ch = ex.get("changes", {})
    has_changes = (ch.get("quantity") is not None) or bool(ch.get("allergies")) or bool(ch.get("special")) or bool(ch.get("address")) or bool(ch.get("addresses")) or bool(ch.get("after")) or bool(ch.get("items"))
    if not has_changes:
        return False
    if s["status"] in LOCK and not force:
        s["pending_approvals"].append(ex)
        need = "manual kitchen approval required" if s["status"] == "PACKED" else "delivery/operator intervention required"
        ev(s, "MODIFICATION_BLOCKED", f'status {s["status"]}: {need}')
        notify(s, "blocked")
        return True

    before = snap(s)
    old = s["quantity"]
    q = ch.get("quantity")
    if q is None and ch.get("items"):
        q = sum(i["quantity"] for i in ch["items"])
    if q is not None and q != old:
        if old == 0:
            ev(s, "ORDER_CREATED", f"{q} meals")
        elif q < old:
            ev(s, "QUANTITY_REDUCED", f"{old} → {q} meals")
            ev(s, "QUANTITY_CHANGED", f"{old} → {q}")
            if q == 0:
                ev(s, "ALL_MEALS_REMOVED", "Order quantity reduced to 0")
        else:
            ev(s, "QUANTITY_CHANGED", f"{old} → {q}")
        s["quantity"] = q
        s.setdefault("quantity_history", []).append({
            "old": old, "new": q, "diff": q - old, "at": now().strftime("%H:%M:%S")
        })

    if ch.get("items"):
        s["items"] = ch["items"]
        s["dish"] = ", ".join(f'{i["quantity"]}× {i["name"]}' for i in ch["items"])

    for a in ch.get("allergies", []):
        ing = a["ingredient"].lower()
        if not any(x["ingredient"] == ing for x in s["allergies"]):
            s["allergies"].append({
                "ingredient": ing,
                "applies_to": "Meal #1" if a.get("scope") == "one_meal" else "All meals",
                "acked": False,
                "confirmed": False
            })
            ev(s, "ALLERGY_ADDED", f"no {ing} — {s['allergies'][-1]['applies_to']}")

    for x in ch.get("special", []):
        if not x.get("requirement"):
            continue
        meal = s["quantity"] if (q and q > old and old > 0) else None
        if any(e["requirement"] == x["requirement"] and e.get("recipient") == x.get("recipient") and e.get("meal") == meal
               for e in s["special"]):
            continue   # same instruction repeated -> do not duplicate it on the kitchen sheet
        s["special"].append({
            "recipient": x.get("recipient"),
            "requirement": x["requirement"],
            "meal": meal
        })
        ev(s, "SPECIAL_REQUIREMENT_ADDED", f'{x.get("recipient") or "customer"} → {x["requirement"]}' + (f" (Meal #{meal})" if meal else ""))

    if ch.get("after") and ch["after"] != s["delivery"]["after"]:
        ev(s, "DELIVERY_TIME_CHANGED", f'{s["delivery"]["after"]} → {ch["after"]}')
        s["delivery"]["after"] = ch["after"]

    multi = ch.get("addresses")
    if multi and len(multi) >= 2:
        open_address_conflict(s, multi[:2])

    a = ch.get("address")
    if a:
        cur = s["delivery"]["address"]
        if cur and cur.lower() != a.lower():
            open_address_conflict(s, [cur, a])
        elif not cur:
            s["delivery"].update(address=a, address_confirmed=True)
            ev(s, "DELIVERY_ADDRESS_SET", a)

    s["conf"] = ex.get("confidence", 0)
    after = snap(s)
    if before != after:
        s["last_diff"] = {
            "before": before,
            "after": after,
            "source": "customer's latest message",
            "at": now().strftime("%H:%M:%S")
        }
    return True

def process(s, sender, text, image=None, audio=None, display=None):
    say(s, sender, display or text)
    ex = ai.extract_order_information(text, sender, snap(s) | {"status": s["status"]}, now(), image, audio)
    
    # Store agent traces for UI transparency
    if ex.get("agent_traces"):
        s["agent_traces"] = ex["agent_traces"]
        s.setdefault("agent_history", []).extend(ex["agent_traces"])
        s["agent_history"] = s["agent_history"][-30:]

    if ex["intent"] == "AI_ERROR":
        ev(s, "AI_OUTPUT_INVALID", "order state left unchanged")
        return

    if sender == "customer" and ex["language"] != "en":
        s["customer"]["lang"] = ex["language"]

    i = ex["intent"]
    if sender == "customer" and s["status"] == "CANCELLED" and i != "STATUS_QUERY":
        ev(s, "MODIFICATION_REJECTED", "order already cancelled")
        say(s, "AI → customer", "This order has been cancelled. Please start a new order to make changes.")
        return
    if i == "CANCELLATION" and sender == "customer":
        if s["status"] in LOCK:
            ev(s, "CANCEL_BLOCKED", s["status"])
            say(s, "AI → customer", "Cancellation blocked: your order is already being packed or is out for delivery. Please contact the kitchen directly.")
        else:
            s["status"] = "CANCELLED"
            ev(s, "ORDER_CANCELLED")
            say(s, "AI → customer", "Your order has been cancelled successfully.")
    elif i == "CONFIRMATION" and sender == "owner" and s["status"] == "RECEIVED" and s["quantity"] > 0:
        s["status"] = "CONFIRMED"
        s["sheet_qty"] = s["quantity"]
        for a in s["allergies"]: a["confirmed"] = True
        ev(s, "ORDER_CONFIRMED", "by owner")
        notify(s, "confirmed")
    elif i == "ADDRESS_QUERY" and sender == "delivery":
        cands = [] if s["delivery"]["address_confirmed"] else list(dict.fromkeys(s["customer"]["known_addresses"]))
        if len(cands) >= 2:
            open_address_conflict(s, cands[:2])
        oc = open_conflicts(s)
        say(s, "AI → delivery", ("Address conflict: " + " vs ".join(oc[0]["options"]) + ". Dispatch is BLOCKED until the customer confirms.") if oc
            else f'Current address: {s["delivery"]["address"]} (confirmed).')
    elif i == "STATUS_QUERY" and sender == "kitchen":
        stale = s["sheet_qty"] is not None and s["sheet_qty"] != s["quantity"]
        al = "; ".join(f'NO {a["ingredient"].upper()} → {a["applies_to"]} [{"confirmed by owner" if a["confirmed"] else "NEEDS CONFIRMATION"}, {"acknowledged" if a["acked"] else "not yet acknowledged by kitchen"}]' for a in s["allergies"]) or "none"
        sp = "; ".join(snap(s)["special"]) or "none"
        say(s, "AI → kitchen", f'{"STALE SHEET: sheet says " + str(s["sheet_qty"]) + ", truth is " + str(s["quantity"]) + ". " if stale else ""}'
            f'Current: {s["quantity"]} meals. Allergy: {al}. Special: {sp}. Address: {"CONFLICT" if open_conflicts(s) else s["delivery"]["address"]}.')
    elif i == "STATUS_QUERY" and sender == "customer":
        say(s, "AI → customer", f"Your order ({s['order_id']}) is currently {s['status']}. Total meals: {s['quantity']}. Delivery window: {s['delivery']['after'] or 'Standard'}.")
    elif i == "ADDRESS_CONFIRMATION" and sender == "customer" and open_conflicts(s):
        a = ex["changes"].get("address") or ""
        for c in open_conflicts(s):
            m = [o for o in c["options"] if o.lower() == a.lower()]
            if m: resolve(s, m[0])
    elif sender == "customer" and i == "ORDER_UPDATE":
        old_q = s["quantity"]
        if apply(s, ex) and not open_conflicts(s) and s["status"] not in LOCK:
            new_q = s["quantity"]
            if new_q < old_q and old_q > 0:
                notify(s, "reduced")
            else:
                notify(s, "received" if s["status"] == "RECEIVED" else "confirmed")

    if sender == "customer":
        completeness(s)

def completeness(s):
    """Flag missing quantity / address and warn the customer (shared by chat, voice and image orders)."""
    if s["status"] not in ("CANCELLED", "DELIVERED"):
        missing = []
        if s["quantity"] == 0:
            missing.append("meal quantity")
        if not s["delivery"].get("address"):
            missing.append("delivery address")
        s["missing_details"] = missing

        if missing and not open_conflicts(s):
            ev(s, "DETAILS_INCOMPLETE", "Missing: " + ", ".join(missing))
            lang = s["customer"]["lang"]
            if "meal quantity" in missing and "delivery address" in missing:
                warn_msg = {
                    "te": "⚠️ ఆర్డర్ హెచ్చరిక: దయచేసి మీ భోజనాల సంఖ్య మరియు డెలివరీ చిరునామాను తెలియజేయండి.",
                    "hi": "⚠️ ऑर्डर चेतावनी: कृपया भोजन की संख्या और डिलीवरी का पता अवश्य बताएं।",
                    "ta": "⚠️ ஆர்டர் எச்சரிக்கை: சாப்பாட்டின் எண்ணிக்கை மற்றும் டெலிவரி முகவரியை தெரிவிக்கவும்.",
                    "kn": "⚠️ ಆದೇಶ ಎಚ್ಚರಿಕೆ: ದಯವಿಟ್ಟು ಊಟದ ಪ್ರಮಾಣ ಮತ್ತು ಡೆಲಿವರಿ ವಿಳಾಸವನ್ನು ತಿಳಿಸಿ.",
                    "en": "⚠️ Order Warning: Please specify both your meal quantity and delivery address so we can schedule and prepare your order."
                }.get(lang, "⚠️ Order Warning: Please specify both your meal quantity and delivery address.")
            elif "delivery address" in missing:
                warn_msg = {
                    "te": f"⚠️ డెలివరీ చిరునామా అవసరం: మీరు {s['quantity']} భోజనాలు ఎంచుకున్నారు. దయచేసి మీ డెలివరీ చిరునామాను (ఇంటి నం, వీధి) పంపండి.",
                    "hi": f"⚠️ डिलीवरी का पता आवश्यक है: आपने {s['quantity']} भोजन चुना है। कृपया अपना डिलीवरी का पता (मकान नं., सड़क) बताएं।",
                    "ta": f"⚠️ முகவரி தேவை: நீங்கள் {s['quantity']} சாப்பாடு தேர்ந்தெடுத்துள்ளீர்கள். தயவுசெய்து உங்கள் டெலிவரி முகவரியை அனுப்பவும்.",
                    "kn": f"⚠️ ವಿಳಾಸ ಅಗತ್ಯವಿದೆ: ನೀವು {s['quantity']} ಊಟ ಆಯ್ಕೆ ಮಾಡಿದ್ದೀರಿ. ದಯವಿಟ್ಟು ನಿಮ್ಮ ಡೆಲಿವರಿ ವಿಳಾಸವನ್ನು ಕಳುಹಿಸಿ.",
                    "en": f"⚠️ Delivery Address Required: You ordered {s['quantity']} meal(s), but no delivery address was specified. Please provide your delivery address (street, area, or house number)."
                }.get(lang, f"⚠️ Delivery Address Required: Please provide your delivery address for your {s['quantity']} meal(s).")
            elif "meal quantity" in missing:
                warn_msg = {
                    "te": "⚠️ భోజనాల సంఖ్య అవసరం: దయచేసి మీకు ఎన్ని భోజనాలు కావాలో లేదా ఏయే వంటకాలు కావాలో తెలియజేయండి.",
                    "hi": "⚠️ भोजन की संख्या आवश्यक है: कृपया बताएं कि आपको कितने भोजन या कौन-से व्यंजन चाहिए।",
                    "ta": "⚠️ சாப்பாட்டின் எண்ணிக்கை தேவை: எத்தனை சாப்பாடு வேண்டும் என்று குறிப்பிடவும்.",
                    "kn": "⚠️ ಊಟದ ಪ್ರಮಾಣ ಅಗತ್ಯವಿದೆ: ದಯವಿಟ್ಟು ಎಷ್ಟು ಊಟ ಬೇಕು ಎಂದು ತಿಳಿಸಿ.",
                    "en": "⚠️ Meal Quantity Required: Please specify how many meals or which dishes you would like to order."
                }.get(lang, "⚠️ Meal Quantity Required: Please specify how many meals you would like to order.")
            say(s, "AI → customer", warn_msg)

def resolve(s, address):
    for c in open_conflicts(s):
        if address in c["options"]:
            c["resolved"] = True
            c["chosen"] = address
    s["delivery"].update(address=address, address_confirmed=True)
    if "delivery address" in s.get("missing_details", []):
        s["missing_details"].remove("delivery address")
    ev(s, "ADDRESS_CONFIRMED", address)

def schedule(s):
    t = s["delivery"]["after"]
    if not t: return None
    try:
        parts = t.split(":")
        hr, mn = int(parts[0]), int(parts[1])
    except Exception:
        return None
    d = (now() + dt.timedelta(days=1)).replace(hour=hr, minute=mn, second=0, microsecond=0)
    f = lambda m: (d - dt.timedelta(minutes=m)).strftime("%I:%M %p")
    return {
        "Preparation starts": f(BUF["prep"]),
        "Packaging starts": f(BUF["pack"]),
        "Dispatch": f(BUF["dispatch"]),
        "Delivery window opens": d.strftime("%I:%M %p"),
        "_note": "AI-generated from configured buffers"
    }, d

def alerts(s):
    A = []; st = s.get("status", "RECEIVED"); sc = schedule(s)
    sheet_qty = s.get("sheet_qty")
    qty = s.get("quantity", 0)
    if sheet_qty is not None and sheet_qty != qty:
        if qty < sheet_qty:
            A.append(("warn", f'⚠️ Quantity changed after kitchen confirmation (sheet: {sheet_qty}, now: {qty}) — Quantity reduced (potential portion waste!)'))
        else:
            A.append(("warn", f'⚠️ Quantity changed after kitchen confirmation (sheet: {sheet_qty}, now: {qty})'))
    for a in s.get("allergies", []):
        if not a.get("acked") and not a.get("acknowledged_by_kitchen"):
            A.append(("crit", f'🚨 Allergy instruction (no {a.get("ingredient")}) not acknowledged by kitchen'))
        if not a.get("confirmed", True):
            A.append(("crit", f'🚨 Allergy (no {a.get("ingredient")}) requires confirmation by owner'))
    if open_conflicts(s): A.append(("warn", "⚠️ Delivery address conflict — dispatch blocked"))
    if s.get("pending_approvals"): A.append(("crit", "🔴 Customer requested modification after packaging — kitchen approval needed"))
    if sc and st in FLOW[:5] and now() >= sc[1] - dt.timedelta(minutes=BUF["pack"]): A.append(("warn", "⏰ Packaging deadline approaching"))
    deliv = s.get("delivery", {})
    if st == "PACKED" and not open_conflicts(s) and deliv.get("address_confirmed") and not s.get("pending_approvals"):
        A.append(("ok", "🟢 Order ready for dispatch"))
    # Incomplete details alerts
    if s.get("missing_details"):
        if "delivery address" in s["missing_details"]:
            A.append(("warn", "⚠️ Incomplete order: Customer has not provided a delivery address"))
        if "meal quantity" in s["missing_details"]:
            A.append(("warn", "⚠️ Incomplete order: Meal quantity has not been specified"))
    return A

def view(s):
    v = dict(s)
    v["alerts"] = alerts(s)
    sc = schedule(s)
    v["schedule"] = sc[0] if sc else None
    busy = {o.get("delivery_assignment") for o in all_orders() if o.get("status") == "OUT_FOR_DELIVERY" and o.get("delivery_assignment")}
    v["helpers"] = [{"name": h, "state": "Out for delivery" if h in busy else "Available"} for h in ("Helper A", "Helper B")]
    a = s["delivery"]["address"] or ""
    km = sum(map(ord, a)) % 9 + 2 if a else 0
    v["delivery_est"] = {
        "km": km,
        "charge": 30 + 8 * km if km else None,
        "eta_min": 10 + 4 * km if km else None,
        "note": "Demo estimate from the address text - not a real routing calculation"
    }
    v["flow"] = FLOW
    v["ai_mode"] = ai.mode()
    v["open_conflicts"] = open_conflicts(s)
    v["agents"] = ai.get_agents()
    v["agent_traces"] = s.get("agent_traces", [])
    v["agent_history"] = s.get("agent_history", [])[-15:]
    v["items"] = s.get("items", [])
    v["missing_details"] = s.get("missing_details", [])
    v["quantity_history"] = s.get("quantity_history", [])
    return v

class Msg(BaseModel): sender: str; text: str
class New(BaseModel): name: str = "Ravi"; lang: str = "te"
class Addr(BaseModel): address: str
class Settings(BaseModel): mode: str
class QtyChange(BaseModel):
    action: str  # "increase" | "decrease" | "set" | "clear"
    quantity: int | None = None

@app.get("/api/health")
def health():
    gemini_key = bool(os.getenv("GEMINI_API_KEY"))
    anthropic_key = bool(os.getenv("ANTHROPIC_API_KEY"))
    live_key_present = gemini_key or anthropic_key
    return {
        "ai_mode": ai.mode(),
        "live_key_present": live_key_present,
        "live_ready": live_key_present,
        "providers": {
            "gemini": gemini_key,
            "anthropic": anthropic_key
        },
        "agents": ai.get_agents()
    }

@app.get("/api/agents")
def get_agents():
    return ai.get_agents()

@app.get("/api/orders")
def orders():
    return [{
        "order_id": o["order_id"],
        "name": o["customer"]["name"],
        "lang": o["customer"]["lang"],
        "status": o["status"],
        "quantity": o["quantity"],
        "alerts": len(alerts(o)),
        "address": o["delivery"]["address"] or "Not set",
        "has_allergy": len(o["allergies"]) > 0,
        "missing_details": o.get("missing_details", []),
        # richer fields used by the dashboard (order list, KDS, radar)
        "customer": o["customer"],
        "delivery": o["delivery"],
        "allergies": o["allergies"],
        "special": o["special"],
        "dish": o.get("dish"),
        "pending_approvals": len(o["pending_approvals"]),
        "open_conflicts": len(open_conflicts(o)),
        "delivery_assignment": o.get("delivery_assignment"),
    } for o in all_orders()]

def next_order_id():
    nums = []
    for o in all_orders():
        m = re.search(r"(\d+)$", o["order_id"])
        if m: nums.append(int(m.group(1)))
    return f"ORD-{max([1000] + nums) + 1}"

def new_state(oid, name="Customer", lang="en", origin="Order thread created"):
    t = now().strftime("%H:%M:%S")
    s = {
        "order_id": oid,
        "customer": {"name": (name or "Customer")[:40], "phone": "+91 98765 43210",
                     "lang": (lang or "en")[:3], "known_addresses": ["12 MG Road", "42 Residency Road"]},
        "quantity": 0, "quantity_history": [],
        "missing_details": ["meal quantity", "delivery address"],
        "items": [], "allergies": [], "special": [],
        "delivery": {"address": None, "address_confirmed": False, "after": None},
        "status": "RECEIVED", "sheet_qty": None, "conflicts": [], "pending_approvals": [],
        "delivery_assignment": None, "last_diff": None, "conf": 0,
        "messages": [], "events": [], "attachments": [],
        "agent_traces": [
            {"agent": "Customer Interaction Agent", "avatar": "🤖", "action": "Order Thread Initialized",
             "thought": f"{origin} for {(name or 'Customer')} (preferred language: {lang}). Ready to ingest requests.", "ts": t},
            {"agent": "Kitchen Operations & Food Safety Agent", "avatar": "👨‍🍳", "action": "Station Standby",
             "thought": "Kitchen safety monitors active. Awaiting recipe specifications and allergen declarations.", "ts": t},
            {"agent": "Logistics & Dispatch Agent", "avatar": "🛵", "action": "Fleet Ready",
             "thought": "Dispatch radar online. Helper A and Helper B available for allocation.", "ts": t},
        ],
        "agent_history": [],
    }
    ev(s, "ORDER_THREAD_OPENED")
    return s

@app.post("/api/orders")
def create(n: New):
    s = new_state(next_order_id(), n.name, n.lang)
    save(s)
    return view(s)

@app.get("/api/orders/{oid}")
def get(oid: str):
    return view(load(oid))

@app.post("/api/orders/{oid}/message")
def message(oid: str, m: Msg):
    raw_sender = (m.sender or "customer").strip().lower()
    if "kitchen" in raw_sender or "chef" in raw_sender or "cook" in raw_sender:
        effective_sender = "kitchen"
    elif "delivery" in raw_sender or "rider" in raw_sender or "driver" in raw_sender:
        effective_sender = "delivery"
    elif "owner" in raw_sender or "manager" in raw_sender:
        effective_sender = "owner"
    else:
        effective_sender = "customer"

    if not m.text.strip():
        raise HTTPException(400, "message text is empty")
    try:
        s = load(oid)
    except HTTPException:
        s = new_state(oid, "Customer", "en")   # by design: a thread is auto-created for an unknown id
    process(s, effective_sender, m.text.strip()[:2000])
    save(s)
    return view(s)

@app.post("/api/orders/{oid}/quantity")
def change_quantity(oid: str, q_data: QtyChange):
    s = load(oid)
    if s["status"] in ("CANCELLED", "DELIVERED"):
        raise HTTPException(409, f"Order is {s['status']}; quantity cannot be changed")
    old = s["quantity"]
    if q_data.action == "decrease":
        new_q = max(0, old - 1)
    elif q_data.action == "increase":
        new_q = old + 1
    elif q_data.action == "clear":
        new_q = 0
    elif q_data.action == "set" and q_data.quantity is not None:
        new_q = max(0, q_data.quantity)
    else:
        raise HTTPException(400, "invalid quantity action")
    
    ex = {
        "intent": "ORDER_UPDATE",
        "language": s["customer"]["lang"],
        "confidence": 1.0,
        "requires_confirmation": False,
        "changes": {"quantity": new_q},
        "agent_traces": [{
            "agent": "Customer Interaction Agent",
            "avatar": "🤖",
            "action": f"Quantity Direct {q_data.action.capitalize()}",
            "thought": f"Adjusted meal quantity from {old} to {new_q}.",
            "ts": now().strftime("%H:%M:%S")
        }]
    }
    say(s, "customer", f"Please {q_data.action} order quantity: {old} → {new_q} meals.")
    apply(s, ex)

    # Missing details update
    missing = []
    if s["quantity"] == 0:
        missing.append("meal quantity")
    if not s["delivery"].get("address"):
        missing.append("delivery address")
    s["missing_details"] = missing

    if new_q < old and old > 0 and s["status"] not in LOCK:
        notify(s, "reduced")

    save(s)
    return view(s)

@app.post("/api/orders/{oid}/resolve")
def resolve_ep(oid: str, a: Addr):
    s = load(oid)
    if not any(a.address in c["options"] for c in open_conflicts(s)):
        raise HTTPException(400, "not an open option")
    resolve(s, a.address)
    say(s, "customer", f"Use {a.address}")
    save(s)
    return view(s)

@app.post("/api/orders/{oid}/ack")
def ack(oid: str):
    s = load(oid)
    for a in s["allergies"]:
        a["acked"] = True
    s["sheet_qty"] = s["quantity"]
    ev(s, "KITCHEN_ACKNOWLEDGED", "allergies + current quantity")
    save(s)
    return view(s)

@app.post("/api/orders/{oid}/approve")
def approve(oid: str):
    s = load(oid)
    if not s["pending_approvals"]:
        raise HTTPException(409, "nothing pending")
    ex = s["pending_approvals"].pop(0)
    apply(s, ex, force=True)
    ev(s, "MODIFICATION_APPROVED", "manual kitchen approval")
    save(s)
    return view(s)

@app.post("/api/orders/{oid}/cancel")
def cancel_ep(oid: str):
    s = load(oid)
    if s["status"] in LOCK:
        raise HTTPException(409, "Order cannot be cancelled in current status")
    s["status"] = "CANCELLED"
    ev(s, "ORDER_CANCELLED", "User requested direct cancellation")
    say(s, "AI → customer", "Your order has been cancelled.")
    save(s)
    return view(s)

class Advance(BaseModel):
    status: str | None = None

@app.post("/api/orders/{oid}/advance")
def advance(oid: str, body: Advance | None = Body(default=None)):
    s = load(oid)
    st = s["status"]
    if st not in FLOW or st == FLOW[-1]:
        raise HTTPException(409, "cannot advance")
    nxt = FLOW[FLOW.index(st) + 1]
    if body and body.status and body.status != nxt:
        raise HTTPException(409, f"Order is {st}; next step is {nxt}, not {body.status}. Refresh and try again.")
    if s["quantity"] == 0:
        raise HTTPException(409, "Order has 0 meals - add meals first (or cancel the order)")
    if nxt == "PACKAGING" and any(not a["acked"] for a in s["allergies"]):
        raise HTTPException(409, "Packaging locked: allergy instruction must be acknowledged")
    if nxt == "PACKED" and s["pending_approvals"]:
        raise HTTPException(409, "Resolve pending modification first")
    if nxt == "OUT_FOR_DELIVERY":
        if open_conflicts(s) or not s["delivery"]["address_confirmed"]:
            raise HTTPException(409, "Dispatch blocked: delivery address not confirmed")
        busy = {o.get("delivery_assignment") for o in all_orders() if o.get("status") == "OUT_FOR_DELIVERY"}
        free = [h for h in ("Helper A", "Helper B") if h not in busy]
        if not free:
            raise HTTPException(409, "No delivery helper available")
        s["delivery_assignment"] = free[0]
        ev(s, "DELIVERY_ASSIGNED", free[0])
    if nxt == "CONFIRMED":
        s["sheet_qty"] = s["quantity"]
        for a in s["allergies"]: a["confirmed"] = True
        ev(s, "ORDER_CONFIRMED", "by owner")
    s["status"] = nxt
    ev(s, nxt)
    if nxt in KIND:
        notify(s, KIND[nxt])
    save(s)
    return view(s)

MAX_UPLOAD = 5_000_000

def role_of(raw):
    r = (raw or "customer").strip().lower()
    if "kitchen" in r or "chef" in r or "cook" in r: return "kitchen"
    if "delivery" in r or "rider" in r or "driver" in r: return "delivery"
    if "owner" in r or "manager" in r: return "owner"
    return "customer"

def check_image(data):
    """Verify the bytes really are a PNG/JPEG/WEBP (never trust the client's content-type)."""
    import io
    from PIL import Image
    try:
        im = Image.open(io.BytesIO(data)); fmt = im.format; im.verify()
    except Exception:
        raise HTTPException(400, "That file is not a readable image.")
    kinds = {"PNG": ("image/png", "png"), "JPEG": ("image/jpeg", "jpg"), "WEBP": ("image/webp", "webp")}
    if fmt not in kinds:
        raise HTTPException(415, "Unsupported image format - please use PNG, JPEG or WEBP.")
    return kinds[fmt]

def store_media(data, ext):
    fname = f"{uuid.uuid4().hex}.{ext}"
    (UP / fname).write_bytes(data)
    return fname

def ingest_image(s, sender, data, ct, fname, notes=None):
    """Turn an order photo into order details. Returns (read_ok, note). Never fabricates details:
    if no live model can read the photo, the image is attached and the customer is asked to type the order."""
    s["attachments"].append({"file": fname, "kind": "image", "by": sender, "ts": now().strftime("%H:%M:%S")})
    say(s, sender, "📷 Order image uploaded" + (f" — {notes}" if notes else ""), image=f"/media/{fname}")
    if s["status"] == "CANCELLED":
        ev(s, "MODIFICATION_REJECTED", "order already cancelled")
        say(s, "AI → customer", "This order has been cancelled. Please start a new order to make changes.")
        return False, "order is cancelled"
    ev(s, "IMAGE_RECEIVED", fname)

    ex = ai.extract_from_image((ct, base64.b64encode(data).decode()), sender, snap(s) | {"status": s["status"]}, now(), notes or "")
    why = None
    if ex is None:
        why = ("mock mode cannot read photos - switch to live AI mode" if ai.mode() != "live"
               else "the AI provider was unreachable (check API key / model / network)")
    elif ex.get("intent") == "AI_ERROR":
        why = "the model's answer could not be validated"
    else:
        ch = ex["changes"]
        if not (ch.get("quantity") is not None or ch.get("items") or ch.get("address") or ch.get("allergies")
                or ch.get("special") or ch.get("after")):
            why = "no order details were found in the image"
    if why:
        ev(s, "IMAGE_NOT_READ", why)
        say(s, "AI → customer", f"I received your image but could not read an order from it ({why}). "
                                "Please type the dishes, quantity and delivery address in the chat.")
        completeness(s)
        return False, why

    ex["intent"] = "ORDER_UPDATE"          # an order photo is always an order, whatever label the model chose
    if ex.get("language") not in (None, "en") and not (s["customer"].get("lang") or "").strip() == ex["language"]:
        s["customer"]["lang"] = ex["language"]
    ch = ex["changes"]
    lines = len(ch.get("items") or [])
    trace = {"agent": "Customer Interaction Agent", "avatar": "🤖", "action": "Image Order Extraction",
             "thought": f"Read the order image: {lines} dish line(s), "
                        f"{'address found' if ch.get('address') else 'no address found'}, confidence {ex.get('confidence', 0):.2f}.",
             "ts": now().strftime("%H:%M:%S")}
    s["agent_traces"] = [trace] + list(ex.get("agent_traces") or [])
    s["agent_history"] = (s.get("agent_history", []) + s["agent_traces"])[-30:]
    apply(s, ex)

    parts = [f'{i["quantity"]}× {i["name"]}' for i in (ch.get("items") or [])] or (
        [f'{ch["quantity"]} meal(s)'] if ch.get("quantity") is not None else [])
    summary = "; ".join(parts) or "details"
    ev(s, "IMAGE_PARSED", summary + (f" → {ch['address']}" if ch.get("address") else ""))
    msg = f"Read from your image: {summary}."
    if ch.get("address"): msg += f" Deliver to: {ch['address']}."
    if ch.get("special"): msg += " Notes: " + "; ".join(
        (f'{x["requirement"]}' + (f' ({x["recipient"]})' if x.get("recipient") else "")) for x in ch["special"] if x.get("requirement")) + "."
    if ch.get("allergies"): msg += " Allergies: " + ", ".join(a["ingredient"] for a in ch["allergies"]) + "."
    if ex.get("confidence", 1) < 0.7 or ex.get("requires_confirmation"):
        ev(s, "IMAGE_LOW_CONFIDENCE", f'confidence {ex.get("confidence")}')
        msg += " ⚠️ Handwriting was hard to read - please double-check before confirming."
    else:
        msg += " Please review before the kitchen confirms."
    say(s, "AI → customer", msg)
    completeness(s)
    return True, summary

@app.post("/api/orders/from-image")
async def create_from_image(file: UploadFile = File(...), name: str = Form(None), lang: str = Form(None), notes: str = Form(None)):
    """Create a NEW order from a photo of a handwritten / printed order."""
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file too large (5MB max)")
    ct, ext = check_image(data)                       # validate before creating anything
    s = new_state(next_order_id(), (name or "Customer").strip() or "Customer", (lang or "en").strip() or "en",
                  origin="Order created from an image upload")
    ok, note = ingest_image(s, "customer", data, ct, store_media(data, ext), (notes or "").strip() or None)
    save(s)
    out = view(s)
    out["image_read"], out["image_note"] = ok, note
    return out

@app.post("/api/orders/{oid}/upload")
async def upload(oid: str, sender: str = Form("customer"), file: UploadFile = File(...), lang: str = Form(None),
                 notes: str = Form(None), use_sample: bool = Form(True)):
    data = await file.read(MAX_UPLOAD + 1)
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "file too large (5MB max)")
    ct = (file.content_type or "").split(";")[0].strip().lower()
    if not (ct.startswith("image/") or ct.startswith("audio/")):
        raise HTTPException(415, "unsupported type")
    try:
        s = load(oid)
    except HTTPException:
        s = new_state(oid, "Customer", lang or "en", origin="Order thread created via media upload")
    who = role_of(sender)
    effective_lang = lang or s["customer"]["lang"] or "en"

    if ct.startswith("image/"):
        ct, ext = check_image(data)
        ingest_image(s, who, data, ct, store_media(data, ext), (notes or "").strip() or None)
    else:
        ext = re.sub(r"[^a-z0-9]", "", ct.split("/")[1])[:5] or "bin"
        fname = store_media(data, ext)
        s["attachments"].append({"file": fname, "kind": "audio", "by": who, "ts": now().strftime("%H:%M:%S")})
        transcript, tag = (notes or "").strip(), f"🎙️ [Voice Note ({effective_lang.upper()})"
        sample = False
        if not transcript and ai.mode() != "live":
            if not use_sample:
                raise HTTPException(422, "Mock mode cannot transcribe audio. Type what was said and send again, or switch to live mode.")
            sample_transcripts = {
                "te": "నమస్కారం, రేపు రెండు భోజనాలు కావాలి, ఒకదాంట్లో వేరుశెనగలు ఉండకూడదు. 42 రెసిడెన్సీ రోడ్డుకి పంపండి.",
                "hi": "कल तीन थाली चाहिए, 12 मालवीय नगर पर डिलीवर कर दीजिए।",
                "ta": "நாளை இரண்டு சாப்பாடு வேண்டும், 15 காந்தி ரோடு முகவரிக்கு அனுப்பவும்.",
                "kn": "ನಾಳೆ ಮೂರು ಊಟ ಬೇಕು, 10 ಎಂಜಿ ರಸ್ತೆಗೆ ಡೆಲಿವರಿ ಮಾಡಿ.",
                "en": "Three meals tomorrow, mild spice for grandma, deliver to 42 Residency Road."
            }
            transcript, sample = sample_transcripts.get(effective_lang, sample_transcripts["en"]), True
        if transcript:
            ev(s, "VOICE_TRANSCRIBED", f"{effective_lang.upper()}{' (demo sample)' if sample else ''}: {transcript[:40]}...")
            process(s, who, transcript, display=f'{tag}{" — demo sample transcript" if sample else ""}]: "{transcript}"')
        else:   # live mode, no typed transcript: let the multimodal model listen to the audio itself
            ev(s, "VOICE_RECEIVED", effective_lang.upper())
            process(s, who, f"[voice message in {effective_lang}: transcribe and extract order details]",
                    audio=(ct, data), display=f"{tag}]")

    save(s)
    return view(s)

@app.post("/api/settings")
def update_settings(cfg: Settings):
    if cfg.mode not in ("mock", "live"):
        raise HTTPException(400, "invalid mode")
    if cfg.mode == "live" and not (os.getenv("GEMINI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")):
        raise HTTPException(400, "Live mode requires GEMINI_API_KEY or ANTHROPIC_API_KEY in .env")
    os.environ["AI_MODE"] = cfg.mode
    return {"status": "ok", "mode": cfg.mode}

@app.get("/api/orders/{oid}/messages")
def get_order_messages(oid: str):
    c = _c()
    rows = c.execute("select ts, who, text from messages where order_id=? order by rowid", (oid,)).fetchall()
    c.close()
    return [{"ts": r[0], "who": r[1], "text": r[2]} for r in rows]

@app.get("/api/orders/{oid}/events")
def get_order_events(oid: str):
    c = _c()
    rows = c.execute("select ts, event_type, detail from events where order_id=? order by rowid", (oid,)).fetchall()
    c.close()
    return [{"ts": r[0], "type": r[1], "detail": r[2]} for r in rows]

@app.get("/api/analytics")
def get_analytics():
    all_ord = all_orders()
    total = len(all_ord)
    active = sum(1 for o in all_ord if o.get("status") not in ("CANCELLED", "DELIVERED"))
    delivered = sum(1 for o in all_ord if o.get("status") == "DELIVERED")
    cancelled = sum(1 for o in all_ord if o.get("status") == "CANCELLED")
    total_meals = sum(o.get("quantity", 0) for o in all_ord)
    allergens_count = sum(len(o.get("allergies", [])) for o in all_ord)
    waste_alerts = sum(1 for o in all_ord if any("Quantity changed" in a[1] for a in alerts(o)))
    langs = {}
    for o in all_ord:
        l = o.get("customer", {}).get("lang", "en")
        langs[l] = langs.get(l, 0) + 1
    return {
        "total_orders": total,
        "active_orders": active,
        "delivered_orders": delivered,
        "cancelled_orders": cancelled,
        "total_meals": total_meals,
        "active_allergens_tracked": allergens_count,
        "waste_prevention_triggers": waste_alerts,
        "language_distribution": langs
    }

@app.post("/api/reset")
def reset_all_data():
    c = _c()
    c.execute("delete from orders")
    c.execute("delete from messages")
    c.execute("delete from events")
    c.commit()
    c.close()
    return {"status": "ok", "message": "All orders and history have been cleared."}

def _seed_order(oid, name, phone, lang, dish, qty, allergies, special, address, after, status,
                messages, events, qty_history=None, sheet_qty=None, assignment=None):
    s = new_state(oid, name, lang, origin="Demo order seeded")
    s["customer"]["phone"] = phone
    s["dish"] = dish
    s["quantity"] = qty
    s["quantity_history"] = qty_history or []
    s["allergies"] = [{"ingredient": i, "applies_to": scope, "acked": ack, "confirmed": True}
                      for (i, scope, ack) in allergies]
    s["special"] = special
    s["delivery"] = {"address": address, "address_confirmed": True, "after": after}
    s["status"] = status
    s["sheet_qty"] = sheet_qty if sheet_qty is not None else (qty if status != "RECEIVED" else None)
    s["delivery_assignment"] = assignment
    s["missing_details"] = []
    s["messages"] = messages
    s["events"] = [{"ts": ts, "type": t, "detail": d} for (ts, t, d) in events]
    return s

@app.post("/api/seed")
def seed_demo_data():
    c = _c()
    c.execute("delete from orders")
    c.execute("delete from messages")
    c.execute("delete from events")
    c.commit()
    c.close()

    order1 = _seed_order(
        "ORD-901", "Ananya Rao", "+91 98480 12345", "te", "Royal Andhra Meal & Pulao Combo", 2,
        [("peanuts", "Meal #1", True)],
        [{"recipient": "grandmother", "requirement": "soft food", "meal": 1}],
        "42 Residency Road, Banjara Hills", "13:00", "PREPARING",
        [
            {"ts": "11:00", "who": "customer", "text": "నమస్కారం, రేపు 3 భోజనాలు కావాలి, ఒకదాంట్లో వేరుశెనగలు అస్సలు ఉండకూడదు. 42 రెసిడెన్సీ రోడ్డుకి పంపండి."},
            {"ts": "11:00", "who": "AI → customer", "text": "మీ ఆర్డర్ అందింది. 3 భోజనాలు."},
            {"ts": "11:15", "who": "customer", "text": "దయచేసి ఒక భోజనం తగ్గించండి, మొత్తం 2 చాలు."},
            {"ts": "11:15", "who": "AI → customer", "text": "మీ ఆర్డర్ నవీకరించబడింది: భోజనాల సంఖ్య 2కు తగ్గించబడింది."},
        ],
        [
            ("11:00:05", "ORDER_CREATED", "3 meals"),
            ("11:00:06", "ALLERGY_ADDED", "no peanuts — Meal #1"),
            ("11:05:00", "ORDER_CONFIRMED", "by owner"),
            ("11:15:10", "QUANTITY_REDUCED", "3 → 2 meals"),
            ("11:20:00", "KITCHEN_ACKNOWLEDGED", "allergies + current quantity"),
            ("11:25:00", "PREPARING", ""),
        ],
        qty_history=[{"old": 3, "new": 2, "diff": -1, "at": "11:15:10"}], sheet_qty=3)

    order2 = _seed_order(
        "ORD-902", "Vikram Sharma", "+91 98111 54321", "hi", "Punjabi Dal Makhani & Paneer Tikka Box", 4,
        [], [{"recipient": "kids", "requirement": "mild / low spice", "meal": None}],
        "14 Malviya Nagar", "12:30", "CONFIRMED",
        [
            {"ts": "11:40", "who": "customer", "text": "नमस्ते, कल दोपहर 4 थाली चाहिए, 12:30 के बाद 14 मालवीय नगर पर डिलीवर करवा दें। बच्चों के लिए मिर्च कम रखिएगा।"},
            {"ts": "11:40", "who": "AI → customer", "text": "आपका ऑर्डर पक्का हो गया। 4 भोजन तैयार करेंगे।"},
        ],
        [
            ("11:40:02", "ORDER_CREATED", "4 meals"),
            ("11:40:03", "SPECIAL_REQUIREMENT_ADDED", "kids → mild / low spice"),
            ("11:42:00", "ORDER_CONFIRMED", "by owner"),
        ])

    order3 = _seed_order(
        "ORD-903", "Arjun Menon", "+91 99000 88776", "en", "Kerala Sadhya Executive Box", 2,
        [("mustard", "All meals", True)], [],
        "TechPark Phase 2, Tower B, Whitefield", "12:00", "OUT_FOR_DELIVERY",
        [
            {"ts": "09:30", "who": "customer", "text": "Hi, 2 executive Sadhya meals please. Mustard allergy across all meals. Deliver to Indiranagar home or Whitefield tech park?"},
            {"ts": "09:31", "who": "AI → customer", "text": "Two delivery addresses appear in the conversation. Which one should we use?"},
            {"ts": "09:33", "who": "customer", "text": "Please deliver to TechPark Phase 2 Whitefield after 12:00."},
            {"ts": "09:33", "who": "AI → customer", "text": "Address confirmed for Whitefield! Meal prep scheduled."},
        ],
        [
            ("09:30:10", "ORDER_CREATED", "2 meals"),
            ("09:30:11", "ALLERGY_ADDED", "no mustard — All meals"),
            ("09:31:00", "ADDRESS_CONFLICT_DETECTED", "Indiranagar vs Whitefield"),
            ("09:33:05", "ADDRESS_CONFIRMED", "TechPark Phase 2, Tower B, Whitefield"),
            ("09:40:00", "KITCHEN_ACKNOWLEDGED", "allergies + current quantity"),
            ("11:45:00", "DELIVERY_ASSIGNED", "Helper A"),
            ("11:45:01", "OUT_FOR_DELIVERY", ""),
        ], assignment="Helper A")

    for o in (order1, order2, order3):
        save(o)
    return {"status": "ok", "message": "Successfully seeded 3 demonstration orders across Telugu, Hindi, and English.",
            "seeded_orders": ["ORD-901", "ORD-902", "ORD-903"]}

@app.get("/api/export")
def export_system_data():
    all_ord = all_orders()
    c = _c()
    messages = c.execute("select order_id, ts, who, text from messages").fetchall()
    events = c.execute("select order_id, ts, event_type, detail from events").fetchall()
    c.close()
    return {
        "exported_at": now().isoformat(),
        "system": "CulinaryOS Autonomous Control Tower",
        "version": "2.4.0",
        "orders_count": len(all_ord),
        "orders": all_ord,
        "normalized_messages": [{"order_id": m[0], "ts": m[1], "who": m[2], "text": m[3]} for m in messages],
        "normalized_events": [{"order_id": e[0], "ts": e[1], "type": e[2], "detail": e[3]} for e in events]
    }

@app.get("/")
def index():
    return FileResponse(pathlib.Path(__file__).parent / "static" / "index.html")
