"""AI service layer with Three Autonomous Agents architecture.
1. CustomerAgent (NLU, Intent, Multilingual Localization)
2. KitchenAgent (Food Safety, Allergen Guard, Sheet Sync)
3. DeliveryAgent (Address Verification, Routing, Fleet Dispatch)
4. MultiAgentCoordinator (Orchestration & Trace Logging)
Supports:
- Live LLM execution via Google Gemini (gemini-2.5-flash / gemini-3.8-flash) or Anthropic Claude
- Autonomous local heuristic multi-agent engine for offline / test mock modes
- Vision (food photos, menu receipts) & Audio (voice note ordering)
"""
import os, re, json, base64, httpx, datetime as dt
from dotenv import load_dotenv

load_dotenv()

from agents.customer_agent import CustomerAgent
from agents.kitchen_agent import KitchenAgent
from agents.delivery_agent import DeliveryAgent
from agents.coordinator import MultiAgentCoordinator

coordinator = MultiAgentCoordinator()

LANGS = {"te": (0xC00, 0xC7F), "hi": (0x900, 0x97F), "ta": (0xB80, 0xBFF), "kn": (0xC80, 0xCFF)}
NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "రెండు": 2, "మూడు": 3, "నాలుగు": 4,
       "दो": 2, "तीन": 3, "चार": 4}
HOURS = {"six": 18, "seven": 19, "eight": 20, "five": 17, "four": 16, "noon": 12}

SYSTEM = """You are the Order Intelligence extractor for a home kitchen managed by three collaborative agents (Customer Agent, Kitchen Agent, Delivery Agent). Given the CURRENT order state JSON, the sender role and a new message (any language), return ONLY JSON:
{"intent": one of ORDER_UPDATE|CONFIRMATION|CANCELLATION|ADDRESS_QUERY|STATUS_QUERY|ADDRESS_CONFIRMATION|INFORMATION,
 "language": ISO code of the message, "confidence": 0-1, "requires_confirmation": bool,
 "changes": {"quantity": int|null, "allergies": [{"ingredient": str, "scope": "one_meal"|"all"}],
   "special": [{"recipient": str|null, "requirement": str}], "items": [{"name": str, "quantity": int}],
   "address": str|null, "after": "HH:MM"|null}}
Rules: never invent missing details; never silently resolve conflicting addresses; never remove an allergy unless the
customer explicitly says so; keep fields null/empty when the message does not change them; the latest explicit customer
modification is the intended state; ambiguity => lower confidence and requires_confirmation=true. "quantity" is the TOTAL number of meals/dishes ordered
(the sum of the item quantities when dishes are listed). Only list an allergy when the sender says an ingredient must be avoided
or names an allergy - a dish name such as "egg fried rice" is NOT an allergy. If the input is an IMAGE (handwritten or printed
order, receipt, menu), read every line: list each dish in "items" with its quantity, copy the delivery address exactly as written,
and put free-text instructions (e.g. "less sugar in the apple pie") in "special" with the dish as "recipient". Use intent ORDER_UPDATE
for an image that contains an order. If handwriting is unclear, keep your best reading but lower "confidence" and set requires_confirmation=true. No prose."""

def mode():
    """Return the configured AI mode.

    Live mode is explicit when AI_MODE=live. If AI_MODE is omitted,
    automatically use live when a provider key is configured; otherwise
    stay in the safe offline mock mode.
    """
    configured = os.getenv("AI_MODE", "").strip().lower()
    if configured in {"mock", "live"}:
        return configured
    return "live" if (os.getenv("GEMINI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")) else "mock"

def detect_lang(t):
    return coordinator.customer_agent.detect_language(t)

def validate(d):
    assert isinstance(d, dict) and isinstance(d.get("changes"), dict)
    assert d.get("intent") in {"ORDER_UPDATE", "CONFIRMATION", "CANCELLATION", "ADDRESS_QUERY", "STATUS_QUERY",
                               "ADDRESS_CONFIRMATION", "INFORMATION"}
    c = d["changes"]
    assert c.get("quantity") is None or isinstance(c["quantity"], int)
    assert isinstance(c.get("allergies", []), list) and isinstance(c.get("special", []), list)
    items = []
    for it in c.get("items") or []:
        try:
            name, qty = str(it.get("name", "")).strip(), int(it.get("quantity"))
        except Exception:
            continue
        if name and qty > 0:
            items.append({"name": name, "quantity": qty})
    if items:
        c["items"] = items
        if c.get("quantity") is None or c["quantity"] != sum(i["quantity"] for i in items):
            c["quantity"] = sum(i["quantity"] for i in items)   # total always equals the listed dishes
    else:
        c.pop("items", None)
    if c.get("address") is not None and not str(c["address"]).strip():
        c["address"] = None
    d.setdefault("language", "en")
    d.setdefault("confidence", 0.9 if d.get("intent") != "INFORMATION" else 0.5)
    d.setdefault("requires_confirmation", False)
    for k in ("allergies", "special"):
        c.setdefault(k, [])
    return d

def _call(system, user, image=None, audio=None):
    """Executes live LLM call with support for Anthropic Claude and Google Gemini."""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    gemini_key = os.getenv("GEMINI_API_KEY")

    if anthropic_key:
        try:
            content = [{"type": "text", "text": user}]
            if image:
                content.insert(0, {"type": "image", "source": {"type": "base64", "media_type": image[0], "data": image[1]}})
            r = httpx.post("https://api.anthropic.com/v1/messages", timeout=40,
                           headers={"x-api-key": anthropic_key, "anthropic-version": "2023-06-01"},
                           json={"model": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"), "max_tokens": 800,
                                 "system": system, "messages": [{"role": "user", "content": content}]})
            r.raise_for_status()
            return "".join(b.get("text", "") for b in r.json()["content"])
        except Exception as e:
            if not gemini_key:
                raise e

    if gemini_key:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=gemini_key)
        model_name = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        
        contents = []
        if image:
            contents.append(types.Part.from_bytes(data=base64.b64decode(image[1]), mime_type=image[0]))
        if audio:
            contents.append(types.Part.from_bytes(data=audio[1], mime_type=audio[0]))
        contents.append(f"SYSTEM INSTRUCTIONS:\n{system}\n\nUSER INPUT:\n{user}")

        response = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )
        return response.text or ""

    raise RuntimeError("No LLM API key configured (neither ANTHROPIC_API_KEY nor GEMINI_API_KEY)")

def _live_extract(text, sender, ctx, now, image, audio=None):
    user = f"NOW: {now.isoformat()}\nSENDER: {sender}\nSTATE: {json.dumps(ctx, ensure_ascii=False)}\nMESSAGE: {text}"
    transport_failed = False
    for attempt in range(2):
        try:
            out = _call(SYSTEM + ("" if attempt == 0 else "\nReturn ONLY one valid JSON object, nothing else."), user, image, audio)
        except Exception as e:
            # Provider unreachable / bad key / unknown model: not a model-output problem.
            transport_failed = True
            print(f"[ai_service] live provider call failed: {type(e).__name__}: {str(e)[:200]}")
            break
        try:
            match = re.search(r"\{.*\}", out, re.S)
            if not match:
                continue
            return validate(json.loads(match.group()))
        except Exception:
            continue
    return {"intent": "AI_ERROR", "language": "en", "confidence": 0, "requires_confirmation": True,
            "changes": {}, "_transport_failed": transport_failed}

def _mock_extract(text, sender, ctx, now=None):
    now_dt = now or dt.datetime.now()
    extracted, traces = coordinator.coordinate_message_analysis(text, sender, ctx, now_dt)
    result = validate(extracted)
    result["agent_traces"] = traces
    return result

def extract_order_information(text, sender, ctx, now, image=None, audio=None):
    if mode() == "live":
        res = _live_extract(text, sender, ctx, now, image, audio)
        if not res.pop("_transport_failed", False):
            return res
        # Live provider is unavailable -> degrade gracefully to the built-in local engine
        # instead of leaving the whole app dead.
        fallback = _mock_extract(text, sender, ctx, now)
        fallback.setdefault("agent_traces", []).insert(0, {
            "agent": "Customer Interaction Agent", "avatar": "🤖",
            "action": "AI Provider Unavailable",
            "thought": "Live LLM call failed (check API key / model name / network). Used the built-in local engine instead.",
            "ts": now.strftime("%H:%M:%S")})
        return fallback
    return _mock_extract(text, sender, ctx, now)

def extract_from_image(image, sender, ctx, now, hint=""):
    """Read an order from a photo. Returns the extraction dict, or None when no live model could read it
    (mock mode / provider outage). Never invents order details."""
    if mode() != "live":
        return None
    text = "[IMAGE ORDER] Read the attached image and extract the order." + (f" Sender note: {hint}" if hint else "")
    res = _live_extract(text, sender, ctx, now, image)
    if res.pop("_transport_failed", False):
        return None
    return res

def generate_customer_response(kind, s, lang):
    fallback = coordinator.customer_agent.generate_response(kind, s, lang)
    if mode() == "live" and lang not in ("te", "hi", "en", "ta", "kn"):
        try:
            return _call(f"Translate the message to the language with ISO code {lang}. Output only the translation.",
                         coordinator.customer_agent.generate_response(kind, s, "en")).strip()
        except Exception:
            pass
    return fallback

def get_agents():
    return coordinator.get_agents_status()
