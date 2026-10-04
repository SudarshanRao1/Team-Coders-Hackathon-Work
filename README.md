# Autonomous Home Kitchen Order Control Tower
### Production-Grade Autonomous Multi-Agent Order Management System

A resilient, multi-agent AI system that maintains **One Continuously Updated Source of Truth ("AI Order Truth")** across customer conversations, kitchen production, packaging security, and fleet delivery dispatch.

---

## 🤖 The Three-Agent Architecture

Instead of a single monolithic extraction call or brittle keyword matchers, this system coordinates **three specialized autonomous agents**:

```
                         [ Customer Message / Voice / Image ]
                                         │
                                         ▼
                     ┌───────────────────────────────────────┐
                     │     1. Customer Interaction Agent     │
                     │  (Multilingual NLU, Speech, Ingestion)│
                     └───────────────────┬───────────────────┘
                                         │
                         [ Extracted Truth & Changes ]
                                         │
            ┌────────────────────────────┴────────────────────────────┐
            ▼                                                         ▼
┌───────────────────────────────┐         ┌───────────────────────────────────────┐
│ 2. Kitchen & Food Safety Agent│         │     3. Logistics & Dispatch Agent     │
│ • Critical Allergen Guard     │         │ • Address Ambiguity & Conflict Guard  │
│ • Stale Sheet Discrepancy     │◄───────►│ • Fleet Balancing (Helper A, B)       │
│ • Packaging Lock & Late Change│         │ • Real-time Routing, Distance & ETA   │
│ • Buffer Production Scheduling│         │ • Dispatch Lockout Gatekeeper         │
└───────────────────────────────┘         └───────────────────────────────────────┘
                                         │
                                         ▼
                        ┌─────────────────────────────────┐
                        │   Single Source of Order Truth  │
                        │       & Audit Event Store       │
                        └─────────────────────────────────┘
```

### 1. Customer Interaction Agent (`CustomerAgent`)
- **Role**: Frontline customer engagement, multilingual understanding, and conversational response generation.
- **Languages Supported**: Telugu (`te`), Hindi (`hi`), English (`en`), Tamil (`ta`), Kannada (`kn`), etc.
- **Multimodal Ingestion**: Order photos (handwritten / printed), menu snapshots and voice notes. **Photo reading needs `AI_MODE=live`** with a Gemini or Anthropic key; in mock mode the image is attached to the order but no details are invented.
- **Natural Language Parsing**: Extracts quantities (both digits and language number words), itemized dishes, allergens with scope (one meal vs all meals), special dietary needs with recipient tags, addresses, and delivery time preferences.

### 2. Kitchen Operations & Food Safety Agent (`KitchenAgent`)
- **Role**: Food safety enforcement, recipe truth maintenance, and production scheduling.
- **Critical Allergen Guard**: Flags food safety hazards (peanuts, nuts, dairy, gluten, shellfish, eggs, etc.) with high-priority warnings.
- **Packaging Lock**: Enforces that the kitchen helper must explicitly acknowledge allergy instructions before advancing to `PACKAGING`.
- **Stale Sheet Detection**: Compares physical kitchen printout quantity with live digital order truth, warning the cook if customer adjusted meals after confirmation.
- **Late Change Protection**: Prevents automatic customer changes once packed (`PACKED`), queueing them for chef/owner manual approval.
- **Production Buffer Scheduling**: Generates preparation, packaging, dispatch, and delivery window countdowns from configurable buffers.

### 3. Logistics & Dispatch Agent (`DeliveryAgent`)
- **Role**: Address validation, fleet assignment, routing, and dispatch gating.
- **Address Ambiguity Guard**: Detects multiple contradictory addresses and halts dispatch (`ADDRESS_CONFLICT_DETECTED`) until customer confirms.
- **Fleet Balancing**: Manages availability for delivery helpers (`Helper A`, `Helper B`), preventing double-assignment.
- **Route & Fare Estimation**: Calculates distance (km), transit ETA (mins), and dynamic delivery charges based on destination.
- **Dispatch Gatekeeper**: Blocks transition to `OUT_FOR_DELIVERY` until address is confirmed and all conflicts are resolved.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment (Optional)
The system runs in dual-mode:
- **Autonomous Local Engine (`AI_MODE=mock`)**: Works 100% offline with zero external dependencies using the built-in intelligent multi-agent parser.
- **Live Multimodal LLM (`AI_MODE=live`)**: Connects to Google Gemini (or Anthropic Claude) for deep semantic extraction, OCR image analysis, and audio voice transcription.

```env
# In .env:
AI_MODE=live
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

### 3. Start Application
```bash
uvicorn main:app --reload --port 8000
```
Open **http://localhost:8000** in your browser.

---

## 🧪 Testing & Verification

Run the full pytest suite (26 automated tests covering all original scenarios, real-world edge cases, multilingual orders, cancellations, uploads, quantity reduction, voice notes, order completeness validation, and normalized database queries):

```bash
pytest -v
```

pytest -v
```

### Test Coverage Highlights (66 tests passing):
- `test_extraction_and_flow`: Verifies order creation, allergen scope (`Meal #1`), and delivery timing.
- `test_quantity_allergy_special_and_diff`: Verifies quantity change, stale sheet detection, diff tracking, and alerts.
- `test_address_conflict_blocks_dispatch_and_resolves`: Verifies address conflict blocks dispatch until customer resolution.
- `test_packaging_lock_needs_allergy_ack`: Ensures 409 lock when advancing to packaging with unacknowledged allergy.
- `test_modification_after_packed_is_blocked_then_approved`: Tests post-pack modification lock and kitchen approval.
- `test_multilingual_telugu_input_and_reply`: Verifies native Telugu script intake and localized response.
- `test_real_world_multi_dish_order`: Tests real-world 4-meal order with dairy allergy, apartment address, and evening time.
- `test_hindi_multilingual_order`: Tests Hindi thali order with soft food for grandmother.
- `test_order_cancellation`: Tests customer-initiated cancellation and status lockdown.
- `test_customer_status_inquiry`: Tests status inquiries in real-time.
- `test_quantity_reduction_and_waste_alert`: Tests reducing meals with potential food waste warning when kitchen is already preparing.
- `test_quantity_deletion_to_zero`: Tests clearing/deleting all meals (`0 meals`).
- `test_missing_address_warning_on_first_message`: Proactively warns customer when address is missing on their first order message.
- `test_missing_quantity_warning_on_first_message`: Proactively warns customer when meal quantity is missing on their first order message.
- `test_multilingual_voice_notes_telugu`: Tests voice note audio uploads with Telugu transcript and extraction.
- `test_direct_quantity_endpoint`: Tests interactive `+`, `-`, and `clear` quantity controls.
- `test_analytics_endpoint`: Verifies live operations metrics (orders, meals, active allergens, food waste alerts).
- `test_normalized_messages_and_events_endpoints`: Verifies normalized relational SQLite tables for messages and event logs.
- `test_image_upload_mock_flow`: Mock mode attaches the image and asks for typed details (never invents a quantity).
- `test_image_orders.py`: Order-from-image flow (live path with a stubbed model) + extraction/pipeline regressions.
- `test_audio_upload_mock_flow`: Tests voice note audio transcription workflow.
- `test_agents_metadata_endpoint`: Verifies live status and capabilities for all 3 agents.
- `test_health_endpoint`: Verifies system health, AI engine status, and provider metadata.
- `test_system_reset_and_seed_endpoints`: Verifies 1-click clean slate system reset, enterprise demo seeding, and audit JSON export.
- `test_static_files_serving`: Verifies full separation of static assets (`/`, `/static/css/styles.css`, `/static/js/api.js`, `/static/js/voice.js`, `/static/js/app.js`).

---

## 📷 Create an Order from an Image
Click **📷 Order from Image** in the header (or the 📎 button in the chat bar to add a photo to an existing order).
`POST /api/orders/from-image` (multipart: `file`, optional `name`, `lang`) creates a new order, stores the photo (served from `/media/...`),
and - in live mode - extracts dishes + quantities, delivery address and instructions. The total is the sum of the dishes.
The response includes `image_read` / `image_note`. Always review what was extracted before confirming; handwriting can be misread.

## 💻 Commercial Control Center Architecture (UI & Server Separation)

The application is built with complete separation of concerns between backend services and a modular, clean frontend:

```
Team_Coders/
├── main.py                     # FastAPI REST API & Multi-Agent Orchestrator
├── ai_service.py               # Multilingual NLU, Multimodal OCR & Voice Processing
├── kitchen.db                  # SQLite database with WAL Mode (Orders, Messages, Events)
├── static/                     # Modular Frontend (Clean UI Separation)
│   ├── css/
│   │   └── styles.css          # Dark Glass Design System & Responsive Layouts
│   ├── js/
│   │   ├── api.js              # Centralized Network API client & Toast Alerts
│   │   ├── voice.js            # Multilingual Voice Studio (Recording, Speech-to-Text & TTS)
│   │   └── app.js              # State Controller, Truth Matrix, KDS & Scenarios
│   └── index.html              # HTML5 Single Page Application
├── agents/                     # 3 Autonomous Agent modules (Customer, Kitchen, Delivery)
└── uploads/                    # Secure media upload storage
```

### Multi-View Commercial Control Center:
1. **🛰️ Mission Control Tower**:
   - Live 3-Agent Hub displaying real-time agent status.
   - Interactive Ground Truth Matrix with direct quantity controls (`[-]`, `[+]`, `[🗑️]`).
   - Food Waste Prevention confirmation modal when reducing portions.
   - Proactive warnings on initial order placement if meal count or delivery address is missing.
   - Real-time customer chat stream with audio playback.
   - Lifecycle pipeline stepper and SQLite WAL immutable audit event timeline.
2. **👨‍🍳 Kitchen Display System (KDS)**:
   - Dedicated station view for kitchen cooks and chefs.
   - High-contrast allergen hazard cards with mandatory chef sign-off before packaging.
   - Item-level cook instructions and real-time status advancement.
3. **🛵 Fleet & Logistics Dispatch Radar**:
   - Real-time animated radar sweep tracking dispatched deliveries.
   - Automated address ambiguity conflict resolution.
4. **📊 Operations & Multilingual Intelligence**:
   - Key metrics: Active Orders, Total Meals, Allergens Safeguarded, Food Waste Triggers.
   - Breakdown of customer orders by language across Telugu, Hindi, English, Tamil, and Kannada.
   - 1-click JSON Audit Log download.
5. **🎙️ Multilingual Voice Studio**:
   - Real-time audio recording with animated waveform visualizer.
   - Native Web Speech API speech-to-text recognition in 5 languages.
   - Native Web SpeechSynthesis Text-to-Speech (TTS) audio playback.
   - Realistic voice note presets and fallback synthetic WAV audio generator.
6. **🧹 Clean Slate & Enterprise Seeding**:
   - The system starts on a fresh, clean slate from the beginning.
   - 1-click "Seed Demo" populates rich demonstration orders across Telugu, Hindi, and English.
   - 1-click "Reset System" cleans all orders, messages, and events back to zero.

Contributors:

 Hanuman 
 Jeevan 
 Risheaswer Reddy 

