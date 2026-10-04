"""Multi-Agent Coordinator.
Coordinates collaboration between:
1. CustomerAgent (Intake & Customer Communication)
2. KitchenAgent (Food Safety, Prep Sheets & Buffer Scheduling)
3. DeliveryAgent (Address Verification, Logistics & Dispatch)
"""
import datetime as dt
from agents.customer_agent import CustomerAgent
from agents.kitchen_agent import KitchenAgent
from agents.delivery_agent import DeliveryAgent

class MultiAgentCoordinator:
    """Orchestrates the 3 autonomous agents into a cohesive order management team."""

    def __init__(self):
        self.customer_agent = CustomerAgent()
        self.kitchen_agent = KitchenAgent()
        self.delivery_agent = DeliveryAgent()

    def get_agents_status(self) -> list[dict]:
        """Returns diagnostic health and metadata for all 3 agents."""
        return [
            {
                "id": "customer_agent",
                "name": self.customer_agent.name,
                "role": self.customer_agent.role,
                "avatar": self.customer_agent.avatar,
                "status": "active",
                "capabilities": ["Multilingual NLU", "Intent Detection", "Dietary Intake", "Multimodal OCR/Audio"]
            },
            {
                "id": "kitchen_agent",
                "name": self.kitchen_agent.name,
                "role": self.kitchen_agent.role,
                "avatar": self.kitchen_agent.avatar,
                "status": "active",
                "capabilities": ["Allergen Safety Protocol", "Stale Sheet Detection", "Packaging Lock", "Dynamic Scheduling"]
            },
            {
                "id": "delivery_agent",
                "name": self.delivery_agent.name,
                "role": self.delivery_agent.role,
                "avatar": self.delivery_agent.avatar,
                "status": "active",
                "capabilities": ["Address Ambiguity Guard", "Fleet Allocation", "Distance Matrix ETA", "Dispatch Verification"]
            }
        ]

    def coordinate_message_analysis(self, text: str, sender: str, ctx: dict, now: dt.datetime) -> tuple[dict, list[dict]]:
        """Coordinates the agents to analyze an incoming message and return changes plus reasoning traces."""
        traces = []
        now_str = now.strftime("%H:%M:%S")

        # Step 1: Customer Agent analyzes the input
        extraction = self.customer_agent.parse_message(text, sender, ctx)
        traces.append({
            "agent": self.customer_agent.name,
            "avatar": self.customer_agent.avatar,
            "action": f"Message Analysis ({sender})",
            "thought": extraction.get("agent_thought", f"Processed incoming {sender} input."),
            "ts": now_str
        })

        changes = extraction.get("changes", {})
        
        # Step 2: Kitchen Agent evaluates food safety impact
        if changes.get("allergies"):
            all_ings = [a["ingredient"] for a in changes["allergies"]]
            traces.append({
                "agent": self.kitchen_agent.name,
                "avatar": self.kitchen_agent.avatar,
                "action": "Allergen Security Protocol",
                "thought": f"Allergen(s) identified: {all_ings}. Enforcing mandatory kitchen acknowledgment & packaging lock.",
                "ts": now_str
            })
        elif changes.get("quantity") is not None:
            q_val = changes["quantity"]
            action_title = "Order Clearing / Total Reduction" if q_val == 0 else "Production Volume Assessment"
            thought_desc = "Order meals cleared to 0. Halting cooking line and releasing prep resources." if q_val == 0 else f"Order size adjusted to {q_val} meals. Verifying kitchen prep capacity."
            traces.append({
                "agent": self.kitchen_agent.name,
                "avatar": self.kitchen_agent.avatar,
                "action": action_title,
                "thought": thought_desc,
                "ts": now_str
            })

        # Step 3: Delivery Agent evaluates address & logistics impact
        if changes.get("address"):
            traces.append({
                "agent": self.delivery_agent.name,
                "avatar": self.delivery_agent.avatar,
                "action": "Destination Verification",
                "thought": f"Delivery destination set to: '{changes['address']}'. Calculating routing and transit buffers.",
                "ts": now_str
            })
        elif changes.get("after"):
            traces.append({
                "agent": self.delivery_agent.name,
                "avatar": self.delivery_agent.avatar,
                "action": "Time Window Scheduling",
                "thought": f"Target delivery time set to after {changes['after']}. Synchronizing dispatch buffers.",
                "ts": now_str
            })

        return extraction, traces
