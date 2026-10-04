"""Kitchen & Food Safety Operations Agent.
Responsible for:
1. Maintaining authoritative food preparation truth.
2. Food safety & Allergen Guard (protocol auditing, packaging lock on unacknowledged allergens).
3. Kitchen sheet synchronization (detecting stale physical sheets vs digital order truth).
4. Packaging lock & late modification approvals (preventing waste after packaging).
5. Dynamic production scheduling (prep start, packaging start, dispatch buffers).
6. Responding to kitchen crew queries with real-time preparation status.
"""
import datetime as dt

class KitchenAgent:
    """Autonomous agent managing food safety, preparation truth, and packaging integrity."""

    def __init__(self, buffers: dict = None):
        self.name = "Kitchen Operations & Food Safety Agent"
        self.role = "Kitchen Production, Food Safety Guard & Buffer Scheduling"
        self.avatar = "👨‍🍳"
        self.buffers = buffers or {"prep": 90, "pack": 30, "dispatch": 15}

    def evaluate_food_safety(self, state: dict) -> list[tuple[str, str]]:
        """Audits allergens and returns safety alerts with severity levels."""
        alerts = []
        for a in state.get("allergies", []):
            ing = a["ingredient"].upper()
            scope = a.get("applies_to", "All meals")
            if not a.get("confirmed"):
                alerts.append(("crit", f"🚨 CRITICAL FOOD SAFETY — NO {ing} ({scope}) requires confirmation by owner"))
            if not a.get("acked"):
                alerts.append(("crit", f"🚨 Allergy instruction (no {a['ingredient']}) not acknowledged by kitchen staff"))
        return alerts

    def check_sheet_synchronization(self, sheet_qty: int | None, current_qty: int) -> tuple[bool, str | None]:
        """Detects if kitchen is cooking based on an outdated physical sheet."""
        if sheet_qty is not None and sheet_qty != current_qty:
            return True, f"⚠️ Quantity changed after kitchen confirmation (sheet: {sheet_qty}, now: {current_qty})"
        return False, None

    def check_packaging_lock(self, status: str, has_pending: bool, unacknowledged_allergies: bool) -> tuple[bool, str | None]:
        """Enforces packaging lock conditions."""
        if status in ("PACKED", "OUT_FOR_DELIVERY", "DELIVERED"):
            return False, "Order already packed or dispatched: late customer modification requires kitchen approval"
        if unacknowledged_allergies:
            return False, "Packaging locked: allergy instruction must be acknowledged by kitchen helper first"
        if has_pending:
            return False, "Packaging locked: resolve pending modification first"
        return True, None

    def calculate_schedule(self, delivery_after: str | None, base_date: dt.datetime = None):
        """Calculates dynamic buffer schedule for prep, packaging, and dispatch."""
        if not delivery_after:
            return None, None
            
        now_dt = base_date or dt.datetime.now()
        # Parse delivery hour:minute
        try:
            parts = delivery_after.split(":")
            h, m = int(parts[0]), int(parts[1])
        except Exception:
            return None, None

        # Schedule for tomorrow if current time is past, or same day
        target = (now_dt + dt.timedelta(days=1)).replace(hour=h, minute=m, second=0, microsecond=0)
        
        fmt = lambda minutes_before: (target - dt.timedelta(minutes=minutes_before)).strftime("%I:%M %p")
        schedule_dict = {
            "Preparation starts": fmt(self.buffers["prep"]),
            "Packaging starts": fmt(self.buffers["pack"]),
            "Dispatch": fmt(self.buffers["dispatch"]),
            "Delivery window opens": target.strftime("%I:%M %p"),
            "_note": "AI-generated from kitchen buffer rules"
        }
        return schedule_dict, target

    def answer_kitchen_query(self, state: dict) -> str:
        """Generates exact, safe answer to kitchen crew questions."""
        sheet_qty = state.get("sheet_qty")
        current_qty = state.get("quantity", 0)
        is_stale = sheet_qty is not None and sheet_qty != current_qty
        stale_prefix = f"STALE SHEET: sheet says {sheet_qty}, truth is {current_qty}. " if is_stale else ""
        
        al_list = []
        for a in state.get("allergies", []):
            conf_str = "confirmed by owner" if a.get("confirmed") else "NEEDS CONFIRMATION"
            ack_str = "acknowledged" if a.get("acked") else "not yet acknowledged by kitchen"
            al_list.append(f"NO {a['ingredient'].upper()} → {a['applies_to']} [{conf_str}, {ack_str}]")
        al_summary = "; ".join(al_list) or "none"
        
        sp_list = [f"{x['requirement']}" + (f" for {x['recipient']}" if x.get("recipient") else "") + (f" (Meal #{x['meal']})" if x.get("meal") else "") for x in state.get("special", [])]
        sp_summary = "; ".join(sp_list) or "none"
        
        open_confs = [c for c in state.get("conflicts", []) if not c.get("resolved")]
        addr_status = "CONFLICT" if open_confs else (state.get("delivery", {}).get("address") or "None")

        return f"{stale_prefix}Current: {current_qty} meals. Allergy: {al_summary}. Special: {sp_summary}. Address: {addr_status}."
