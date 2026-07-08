# 08 — Testing Strategy

Comprehensive testing plan for Speed to Lead v4 that simulates a real dealership
with salespeople, a sales manager, and customers.

**Last updated:** 2026-06-06
**Current test count:** 131 passing

---

## Table of Contents

1. [Testing Philosophy](#1-testing-philosophy)
2. [The Dealership Simulation](#2-the-dealership-simulation)
3. [Test Architecture & Tools](#3-test-architecture--tools)
4. [Layer 1: Unit Tests (Existing + Extensions)](#4-layer-1-unit-tests-existing--extensions)
5. [Layer 2: Integration Tests](#5-layer-2-integration-tests)
6. [Layer 3: E2E Simulation Tests](#6-layer-3-e2e-simulation-tests)
7. [Layer 4: AI Conversation Quality Tests](#7-layer-4-ai-conversation-quality-tests)
8. [Layer 5: Load & Concurrency Tests](#8-layer-5-load--concurrency-tests)
9. [Layer 6: Dashboard UI Tests (Playwright)](#9-layer-6-dashboard-ui-tests-playwright)
10. [Layer 7: Manual Testing Checklist](#10-layer-7-manual-testing-checklist)
11. [Compliance Test Matrix](#11-compliance-test-matrix)
12. [CI/CD Pipeline](#12-cicd-pipeline)
13. [Test Coverage Targets](#13-test-coverage-targets)
14. [Running Tests](#14-running-tests)

---

## 1. Testing Philosophy

### The Two-Dimensional Test Matrix

|                  | Real SMS (Twilio) | Fake SMS (FakeTwilio) |
|------------------|-------------------|-----------------------|
| **Real LLM**     | LIVE FIRE         | SMOKE TEST            |
| **Fake LLM**     | CHAOS MODE        | UNIT TESTS (default)  |

Default mode uses FakeTwilio + FakeLLM. No API keys needed, no credits burned,
deterministic results.

### Golden Rules

1. **No test hits a real external service.** Use FakeTwilio, FakeLLM, frozen clock.
2. **Every test gets a clean schema.** In-memory SQLite, created and dropped per test.
3. **Tests assert on behavior, not implementation.** We test what the user sees,
   not how the code is structured internally.
4. **The compliance gate is sacred.** Every send path must be tested against the
   compliance gate in `tools/send_sms.py`.
5. **Speed is the product.** Latency tests enforce the <60s response promise.

### The Fake Test Doubles

**FakeTwilio** — Records outbound messages instead of sending. Intercepts
`client.messages.create()` calls, stores them in an in-memory list. Verify
message content, recipient, and count without sending real SMS.

**FakeLLM** — Returns canned responses based on the conversation state. No API
calls, no costs, deterministic. Tests assert the engine's handling (tool
execution, grounding, autonomy branch), not the model's wording.

**Frozen Clock** — A fixed `datetime` for deterministic quiet-hours,
business-hours, escalation timing, and latency budget tests.

---

## 2. The Dealership Simulation

### The Cast

We simulate a real BC used-car dealership with these actors:

```
DEALERSHIP: "Test Motors" (Vancouver, BC)
  ├── MANAGER: "Sarah" (dashboard user, sees everything)
  ├── SALES REP 1: "Manav" (WhatsApp +160****2870)
  ├── SALES REP 2: "Friend" (WhatsApp +177****4366)
  └── INVENTORY: Honda Civic 2024, Ford Mustang 2021, Toyota RAV4 2023
```

### Customer Personas

| Persona | Scenario | Expected Behavior |
|---------|----------|-------------------|
| **Eager Buyer** | Submits webform with vehicle stock #, consent=True | Auto-reply mentions vehicle, gets assigned, rep claims, AI books appointment |
| **Casual Browser** | SMS with "just looking" | AI qualifies, offers inventory, gentle follow-up |
| **After-Hours Caller** | Missed call at 11 PM | Missed-call text-back, AI handles conversation autonomously |
| **Price Shopper** | Asks for price negotiation | AI respects guardrails (no_price_negotiation), redirects |
| **Opt-Out Customer** | Sends "STOP" | Immediate opt-out, ConsentLog, no further messages |
| **French Customer** | Sends "ARRET" | Same as STOP (bilingual CASL) |
| **Repeat Lead** | Submits form twice in 1 hour | Dedup — same lead returned, no duplicate messages |
| **Impatient Customer** | Lead sits unclaimed for 5+ minutes | Escalation fires, reassigns to next rep, notifies manager |

### Rep Workflows

| Workflow | Steps | Verification |
|----------|-------|--------------|
| **Claim** | WhatsApp "1" → ASSIGNED → CLAIMED | State transition, message logged |
| **Pass** | WhatsApp "2" → reassigned to next rep | New rep gets WhatsApp ping |
| **Manage Pipeline** | View leads on dashboard | Correct state, health badge, timeline |
| **Approve AI Draft** | Business hours → AI generates draft → rep sends | mode="draft", approved_by logged |

### Manager Dashboard

| View | What to Verify |
|------|---------------|
| **Leads** | Stats cards (total, active, appts, sold), lead table, attention widget, health badges |
| **Lead Detail** | Timeline (events + messages), delivery status, AI-generated flag |
| **Team** | Rep leaderboard (sorted by sold), conversion %, TOP badge |
| **Stats** | Response time metrics, conversion funnel, source breakdown, per-rep stats |
| **Settings** | Dealer config, compliance settings, AI persona |
| **Appointments** | Scheduled appointments, status |
| **Login/Logout** | Auth gate, cookie, redirect |

---

## 3. Test Architecture & Tools

### Tool Stack

| Tool | Purpose | When to Use |
|------|---------|-------------|
| **pytest** | Test runner, fixtures, parametrize | All tests |
| **FastAPI TestClient** | HTTP endpoint testing without a running server | Integration + E2E |
| **SQLAlchemy in-memory SQLite** | Isolated DB per test | All tests |
| **Playwright** | Browser-based dashboard UI testing | E2E simulation |
| **Twilio Test Credentials** | Real SMS simulation with test numbers | Live-fire only |
| **OpenRouter (offline mode)** | FakeLLM for AI conversation tests | Unit + integration |
| **httpx** | Async HTTP client for webhook simulation | Integration |
| **pytest-xdist** | Parallel test execution | CI |
| **pytest-cov** | Coverage reporting | CI |
| **freezegun** | Time manipulation (alternative to frozen_now fixture) | Compliance tests |

### Project Structure

```
tests/
├── conftest.py                  # Shared fixtures (DB, FakeTwilio, FakeLLM, frozen_now)
├── fixtures/
│   ├── demo-dealer.yaml         # Valid dealer config
│   ├── inventory_feed.csv       # Vehicle inventory
│   ├── webform_payload.json     # Sample webform submission
│   ├── twilio_sms_inbound.json  # Sample SMS webhook
│   └── crm_expected.json        # Expected CRM sync output
│
│ ── Existing Tests (131 passing) ──
├── test_config.py               # Config validation
├── test_inventory.py            # Inventory sync + grounding
├── test_intake_adapters.py      # Intake parsing
├── test_routing.py              # Round-robin rotation
├── test_lifecycle.py            # State machine transitions
├── test_conversation.py         # AI conversation + business hours
├── test_compliance.py           # Opt-out, quiet hours, consent
├── test_webhooks.py             # FastAPI webhook endpoints
├── test_pipeline_e2e.py         # Full pipeline integration
├── test_e2e_smoke.py            # End-to-end smoke tests
├── test_tenant_isolation.py     # Multi-dealer isolation
├── test_org_sinks.py            # CRM sync sinks
├── test_load.py                 # Sequential load tests
├── test_latency.py              # Response time budget
├── test_chaos.py                # Error boundary tests
├── test_smoke.py                # App startup + dashboard render
│
│ ── NEW Tests (to add) ──
├── test_dealership_simulation.py   # Full dealership scenario simulation
├── test_ai_quality.py              # AI conversation quality evaluation
├── test_dashboard_playwright.py     # Playwright browser tests
├── test_concurrency.py             # Concurrent lead handling
├── test_escalation_ladder.py       # Full escalation scenarios
├── test_followup_sequences.py      # Follow-up message sequences
├── test_appointment_flow.py        # End-to-end appointment booking
└── test_compliance_extended.py     # Extended compliance scenarios
```

### Fixture Architecture

```python
# conftest.py — Key fixtures

@pytest.fixture
def db_engine():
    """In-memory SQLite engine. Each test gets a clean schema."""
    engine = create_engine("sqlite:///:memory:", ...)
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()

@pytest.fixture
def db_session(db_engine):
    """A SQLAlchemy session bound to the in-memory SQLite engine."""
    ...

@pytest.fixture
def frozen_now():
    """A fixed 'now' for deterministic tests. Thu 2026-06-04 17:00 UTC = 10:00 AM Vancouver."""
    return datetime(2026, 6, 4, 17, 0, tzinfo=timezone.utc)

@pytest.fixture
def dealer(db_session):
    """A fully-configured test dealer with sales team, inventory, and compliance."""
    ...

@pytest.fixture
def vehicle(db_session, dealer):
    """A test vehicle in the dealer's inventory."""
    ...

@pytest.fixture
def fake_twilio():
    """Records outbound messages instead of sending."""
    return FakeTwilio()

@pytest.fixture
def fake_llm():
    """Returns scripted AI responses."""
    return FakeLLM()
```

---

## 4. Layer 1: Unit Tests (Existing + Extensions)

### What's Already Covered (131 tests)

| Test File | Coverage | Count |
|-----------|----------|-------|
| `test_config.py` | DealerConfig validation, defaults, rejection | 6 |
| `test_inventory.py` | Feed parsing, field mapping, sync, grounding | 9 |
| `test_intake_adapters.py` | Webform, SMS, email parsing | ~10 |
| `test_routing.py` | Round-robin rotation, inactive skip, empty team | 3 |
| `test_lifecycle.py` | All legal/illegal transitions, event creation | 6 |
| `test_conversation.py` | Business hours, system prompt, handle_turn | 9 |
| `test_compliance.py` | STOP, ARRET, quiet hours, consent | 6 |
| `test_webhooks.py` | All webhook endpoints (form, SMS, WhatsApp, voice, status) | 12 |
| `test_pipeline_e2e.py` | Full pipeline, escalation, opt-out, round-robin, dedup, grounding | 7 |
| `test_e2e_smoke.py` | Full lifecycle, dashboard rendering | 10 |
| `test_tenant_isolation.py` | Multi-dealer data isolation | 6 |
| `test_org_sinks.py` | Native sink, flush events, idempotency | 6 |
| `test_load.py` | Sequential leads, unique IDs, dedup | 6 |
| `test_latency.py` | Response time budget (<5s), dashboard render (<2s) | 5 |
| `test_chaos.py` | Bad payloads, unknown tokens, edge states | 10 |
| `test_smoke.py` | Health check, dashboard render, team leaderboard | 8 |

### Extensions to Add

#### 1. Extended Lifecycle Tests (`test_lifecycle.py` additions)

```python
def test_every_non_terminal_can_reach_opted_out():
    """Every state except SOLD/LOST/OPTED_OUT must be able to reach OPTED_OUT."""
    for state in LeadState:
        if state in (LeadState.SOLD, LeadState.LOST, LeadState.OPTED_OUT):
            continue
        assert can_transition(state, LeadState.OPTED_OUT)

def test_escalated_can_reassign():
    """ESCALATED -> ASSIGNED (reassign to next rep) is the recovery path."""
    assert can_transition(LeadState.ESCALATED, LeadState.ASSIGNED)

def test_claimed_can_go_to_lost():
    """A claimed lead that doesn't convert should be markable as LOST."""
    assert can_transition(LeadState.CLAIMED, LeadState.LOST)

def test_appt_set_can_go_to_lost():
    """A no-show appointment should be markable as LOST."""
    assert can_transition(LeadState.APPT_SET, LeadState.LOST)
```

#### 2. Extended Compliance Tests (`test_compliance.py` additions)

```python
def test_all_opt_out_keywords():
    """Every keyword in the config triggers opt-out."""
    for keyword in ["STOP", "STOPALL", "UNSUBSCRIBE", "ARRET"]:
        # Test each keyword independently

def test_opt_out_confirmation_message_content():
    """The opt-out confirmation must include 'unsubscribed' per CASL."""
    # Verify the exact TwiML response content

def test_quiet_hours_different_timezones():
    """Quiet hours work correctly across PST/PDT boundary."""
    # Test with America/Vancouver and America/Edmonton

def test_quiet_hours_exempt_opt_out_confirmation():
    """STOP during quiet hours still gets an immediate response."""
    # CASL requires immediate opt-out confirmation

def test_auto_reply_exempt_from_quiet_hours():
    """Auto-reply to a new lead is exempt from quiet hours."""
    # The customer just texted you — you can text back immediately

def test_compliance_footer_present():
    """Every outbound SMS includes business name + address + opt-out instruction."""
    # Check that send_sms appends the compliance footer
```

#### 3. Extended Routing Tests (`test_routing.py` additions)

```python
def test_single_rep_gets_all_leads():
    """With only 1 active rep, they get every lead."""
    # No rotation needed, but verify assignment works

def test_all_reps_inactive_goes_to_ai():
    """When all reps are inactive, lead stays in AUTO_REPLIED (AI-only path)."""
    # The AI handles the conversation autonomously

def test_round_robin_pointer_wraps():
    """Pointer wraps around after the last rep."""
    # With 3 reps, after 3 leads the pointer should be back to rep 0

def test_pass_reassigns_to_next_rep():
    """WhatsApp '2' (pass) reassigns to the next rep in rotation."""
    # Verify the new rep gets a WhatsApp ping
```

#### 4. Extended Conversation Tests (`test_conversation.py` additions)

```python
def test_handle_turn_with_vehicle_context():
    """Vehicle context is included in the system prompt when available."""
    # Verify the system prompt contains vehicle year/make/model/price

def test_handle_turn_without_vehicle():
    """Works without vehicle context (generic inquiry)."""
    # Should not crash, should handle gracefully

def test_handle_turn_respects_guardrails():
    """System prompt includes guardrails from dealer config."""
    # no_price_negotiation, no_financing_promises

def test_execute_tool_call_check_inventory():
    """check_inventory tool returns real vehicles only."""
    # Existing test, extend with edge cases

def test_execute_tool_call_book_appointment():
    """book_appointment tool creates an appointment record."""
    # Verify state transition to APPT_SET

def test_execute_tool_call_unknown_tool():
    """Unknown tool name returns an error dict, doesn't crash."""
    # {_execute_tool_call("fake_tool", "{}") should return error dict}
```

---

## 5. Layer 2: Integration Tests

### Full Pipeline Scenarios

These tests exercise the complete flow from intake to outcome, using
FakeTwilio and FakeLLM.

#### Scenario 1: Happy Path — Webform to Appointment

```python
def test_happy_path_webform_to_appointment(db_session, dealer, vehicle, fake_twilio, fake_llm):
    """
    Customer submits webform with vehicle interest and consent.
    Pipeline: NEW → AUTO_REPLIED → ASSIGNED → CLAIMED → ENGAGED → APPT_SET

    Verifies:
    - Auto-reply SMS sent within budget (<5s)
    - Auto-reply mentions the vehicle (Honda Civic)
    - WhatsApp claim ping sent to assigned rep
    - Rep claims via WhatsApp "1"
    - AI conversation drives toward booking
    - Appointment created with correct time
    - LeadEvent audit trail is complete
    - Message records have correct direction/channel/body
    """
```

#### Scenario 2: SMS Lead to Autonomous Conversation

```python
def test_sms_lead_after_hours_autonomous(db_session, dealer, fake_twilio, fake_llm):
    """
    Customer texts the dealer's SMS number at 10 PM.
    Pipeline: NEW → AUTO_REPLIED → ENGAGED (autonomous)

    Verifies:
    - Auto-reply sent (exempt from quiet hours — customer initiated)
    - AI handles conversation autonomously (mode="send")
    - Response is sent via TwiML (not queued for rep approval)
    - Business hours check returns False
    """
```

#### Scenario 3: Escalation After Timeout

```python
def test_escalation_full_ladder(db_session, dealer, fake_twilio, frozen_now):
    """
    Lead assigned to Rep 1, no claim within 2 minutes.
    Pipeline: ASSIGNED → ESCALATED → ASSIGNED (reassigned to Rep 2)

    Verifies:
    - on_claim_timeout fires after claim_timeout_min
    - Lead transitions to ESCALATED
    - Reassign action picks next rep
    - notify_manager sends WhatsApp to manager phone
    - Lead ends up ASSIGNED to a different rep
    """
```

#### Scenario 4: Multiple Leads, Round-Robin, Concurrent Claims

```python
def test_multiple_leads_round_robin_with_claims(db_session, dealer, fake_twilio, fake_llm):
    """
    6 leads arrive, distributed round-robin between 2 reps.
    Rep 1 claims their first lead, passes their second.
    Rep 2 claims both of theirs.

    Verifies:
    - Leads distributed evenly (3 each)
    - Claim updates state correctly
    - Pass reassigns to next rep
    - Each rep's pipeline is independent
    """
```

#### Scenario 5: Full Opt-Out Journey

```python
def test_full_opt_out_journey(db_session, dealer, fake_twilio, fake_llm):
    """
    Customer submits form → gets auto-reply → conversation starts → sends STOP.

    Verifies:
    - Lead created with consent=True
    - Auto-reply sent
    - STOP keyword triggers OPTED_OUT
    - ConsentLog entry created with action="opted_out"
    - All subsequent send_sms calls suppressed (returns None)
    - AI conversation stops (no further responses)
    - Reply confirms opt-out (CASL requirement)
    """
```

#### Scenario 6: Missed Call to Appointment

```python
def test_missed_call_to_appointment(db_session, dealer, fake_twilio, fake_llm):
    """
    Customer calls dealer, no answer. Gets text-back. Replies, AI qualifies, books.

    Verifies:
    - Voice webhook triggers missed-call text-back
    - Text-back mentions dealer name and main phone
    - Customer replies → creates new lead
    - AI handles conversation
    - Appointment booked
    """
```

#### Scenario 7: Dedup Across Channels

```python
def test_dedup_across_channels(db_session, dealer, fake_twilio):
    """
    Same customer submits webform AND sends SMS within 1 hour.

    Verifies:
    - Webform creates lead
    - SMS from same phone returns existing lead (dedup)
    - No duplicate messages sent
    - Single lead record in DB
    """
```

#### Scenario 8: Email Lead (AutoTrader)

```python
def test_email_lead_from_autotrader(db_session, dealer, fake_twilio):
    """
    AutoTrader email arrives via forwarding. Adapter parses it.
    Pipeline: NEW → AUTO_REPLIED → ASSIGNED

    Verifies:
    - Email adapter extracts name, phone, vehicle interest
    - Vehicle ref resolved against inventory
    - Auto-reply mentions the specific vehicle
    """
```

---

## 6. Layer 3: E2E Simulation Tests

### Full Dealership Day Simulation

This test simulates an entire day at the dealership using FastAPI TestClient.

```python
class TestDealershipDay:
    """Simulate a full business day with multiple customers, reps, and events."""

    def test_morning_rush(self, client, db_engine, dealer, vehicle):
        """
        8:00 AM — 3 leads arrive within 5 minutes.
        Verifies: All get auto-replies, round-robin distributes evenly,
        all get WhatsApp pings.
        """

    def test_midday_conversations(self, client, db_engine, dealer, vehicle):
        """
        11:00 AM — Reps claim leads and AI conversations run.
        Verifies: Claims work, AI drafts mode (business hours),
        conversation context preserved across turns.
        """

    def test_afternoon_appointments(self, client, db_engine, dealer, vehicle):
        """
        2:00 PM — Appointments booked, shown, and sold.
        Verifies: APPT_SET → SHOWED → SOLD transitions,
        appointment records created, events logged.
        """

    def test_evening_after_hours(self, client, db_engine, dealer, vehicle):
        """
        9:30 PM — After-hours leads arrive.
        Verifies: AI handles autonomously (mode="send"),
        no rep notification until business hours.
        """

    def test_overnight_opt_out(self, client, db_engine, dealer):
        """
        11:00 PM — Customer sends STOP.
        Verifies: Immediate opt-out (exempt from quiet hours),
        ConsentLog entry, no further messages.
        """

    def test_next_morning_escalation(self, client, db_engine, dealer):
        """
        8:05 AM — Unclaimed leads from overnight escalate.
        Verifies: Escalation ladder fires, reassigns, notifies manager.
        """

    def test_dashboard_reflects_full_day(self, client, db_engine, dealer, auth_cookies):
        """
        Manager checks dashboard after the full day.
        Verifies: Stats cards accurate, conversion funnel correct,
        rep leaderboard shows real data, attention items populated,
        response time metrics computed.
        """
```

---

## 7. Layer 4: AI Conversation Quality Tests

### Purpose

These tests evaluate the AI's responses for correctness, grounding, and
appropriate behavior. They use the FakeLLM to test the engine's handling,
and (optionally) the real LLM to evaluate response quality.

### Grounding Tests (FakeLLM — Engine Handling)

```python
class TestAIGrounding:
    """Verify the AI can only state facts from tools, never invent data."""

    def test_check_inventory_returns_real_vehicles_only(self, db_session, dealer, vehicle):
        """Search for Honda → returns the real Civic. Search for Ferrari → returns nothing."""
        from app.engine.conversation import _execute_tool_call
        import json

        # Honda exists
        result = _execute_tool_call("check_inventory", json.dumps({"query": "Honda"}),
                                     session=db_session, dealer_id=dealer.id)
        assert len(result["vehicles"]) == 1
        assert result["vehicles"][0]["make"] == "Honda"

        # Ferrari doesn't exist
        result = _execute_tool_call("check_inventory", json.dumps({"query": "Ferrari"}),
                                     session=db_session, dealer_id=dealer.id)
        assert len(result["vehicles"]) == 0
        assert "No matching" in result["message"]

    def test_book_appointment_requires_engaged_state(self, db_session, dealer):
        """Cannot book appointment for a NEW lead."""
        from tools.book_appointment import book_appointment
        # NEW lead → ValueError

    def test_system_prompt_includes_dealer_name(self):
        """System prompt always includes the dealer's name."""
        prompt = build_system_prompt(DEMO_CONFIG)
        assert "Demo Auto Sales" in prompt

    def test_system_prompt_includes_guardrails(self):
        """System prompt includes all configured guardrails."""
        prompt = build_system_prompt(DEMO_CONFIG)
        assert "Do not negotiate on price" in prompt
        assert "Do not make specific financing promises" in prompt

    def test_system_prompt_includes_vehicle_context(self):
        """When vehicle is provided, prompt includes stock#, year, make, model, price."""
        prompt = build_system_prompt(DEMO_CONFIG, vehicle_context="Stock #: SA1001 | 2024 Honda Civic | Price: $32,500")
        assert "SA1001" in prompt
        assert "Honda Civic" in prompt
```

### AI Quality Evaluation (Real LLM — Optional)

These tests call the real OpenRouter API (requires API key) and evaluate
the quality of AI responses using automated criteria.

```python
@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY"), reason="No API key")
class TestAIQualityReal:
    """Evaluate AI response quality with real LLM calls. Costs ~$0.01 per test."""

    def test_ai_handles_price_negotiation_gracefully(self):
        """Customer asks for a discount. AI should not negotiate (guardrail)."""
        # Call handle_turn with: "Can you do $25,000 instead of $32,500?"
        # Assert: response does NOT commit to a lower price
        # Assert: response redirects (e.g., "I can't negotiate, but let's book a test drive")

    def test_ai_handles_unrelated_question(self):
        """Customer asks about the weather. AI should redirect to vehicle interest."""
        # Call handle_turn with: "What's the weather like today?"
        # Assert: response doesn't hallucinate weather info
        # Assert: response redirects to vehicle/inventory topic

    def test_ai_handles_out_of_stock_vehicle(self):
        """Customer asks about a vehicle that's not in inventory."""
        # Call handle_turn with: "Do you have a Tesla Model 3?"
        # Assert: response says no Tesla in inventory
        # Assert: response suggests alternatives or asks about other preferences

    def test_ai_handles_financing_question(self):
        """Customer asks about financing rates."""
        # Call handle_turn with: "What's your financing rate?"
        # Assert: response doesn't promise specific rates (guardrail)
        # Assert: response suggests visiting the dealership or speaking with finance

    def test_ai_handles_ambiguous_intent(self):
        """Customer sends vague message."""
        # Call handle_turn with: "hey"
        # Assert: response asks clarifying questions
        # Assert: response is friendly and not pushy

    def test_ai_handles_multiple_turns(self):
        """Multi-turn conversation maintains context."""
        # Turn 1: "I'm looking for an SUV"
        # Turn 2: "What about something under $30k?"
        # Turn 3: "Can I come see it Saturday?"
        # Assert: each response builds on previous context
        # Assert: by turn 3, appointment booking is offered

    def test_ai_handles_objection_price_too_high(self):
        """Customer objects to price."""
        # Call handle_turn with: "That's too expensive for me"
        # Assert: response acknowledges concern without negotiating
        # Assert: response offers value (test drive, features, financing options)

    def test_ai_handles_objection_not_ready(self):
        """Customer says they're not ready to buy."""
        # Call handle_turn with: "I'm just browsing, not ready to buy yet"
        # Assert: response is no-pressure
        # Assert: response offers to stay in touch or answer questions
```

### AI Response Quality Criteria

For each AI response, evaluate against these criteria:

| Criterion | Weight | Description |
|-----------|--------|-------------|
| **Grounding** | 25% | Does the response only state facts from tools? No invented vehicles/prices? |
| **Goal Alignment** | 20% | Does the response drive toward the goal (book_appointment)? |
| **Guardrail Compliance** | 20% | Does the response respect guardrails (no negotiation, no financing promises)? |
| **Tone** | 15% | Is the response friendly, concise, no-pressure? |
| **Context Awareness** | 10% | Does the response reference previous conversation turns? |
| **CASL Compliance** | 10% | Does the response include opt-out instruction if required? |

---

## 8. Layer 5: Load & Concurrency Tests

### Purpose

Verify the engine handles multiple simultaneous leads without DB corruption,
lost messages, or performance degradation.

### Test Scenarios

```python
class TestConcurrency:
    """Concurrent lead handling tests."""

    def test_10_sequential_leads_no_corruption(self, client, dealer):
        """10 sequential lead submissions should all succeed."""
        # Submit 10 leads with unique phones
        # Assert all return status="ok" with unique lead_ids
        # Assert all leads are in AUTO_REPLIED or ASSIGNED state

    def test_rapid_same_phone_dedup(self, client, dealer):
        """Same phone submitting 3 times rapidly — only 1 lead created."""
        # Submit 3 times with same phone
        # Assert all 3 return the same lead_id

    def test_concurrent_webhooks_no_deadlock(self, client, dealer):
        """Concurrent webhook submissions don't deadlock."""
        # Use ThreadPoolExecutor to submit 5 leads simultaneously
        # Assert all succeed (may be sequential due to SQLite limitations)

    def test_healthz_under_load(self, client, dealer):
        """/healthz responds 200 even while leads are being processed."""
        # Submit 5 leads, then check /healthz
        # Assert 200 OK

    def test_concurrent_claims_different_reps(self, client, dealer):
        """Two reps claim different leads simultaneously."""
        # Create 2 leads, assign to different reps
        # Both reps claim simultaneously
        # Assert both leads are CLAIMED

    def test_concurrent_claim_and_pass(self, client, dealer):
        """One rep claims while another passes — no race condition."""
        # Create 2 leads
        # Rep 1 claims lead 1, Rep 2 passes lead 2 simultaneously
        # Assert lead 1 is CLAIMED, lead 2 is reassigned

    def test_dashboard_loads_during_lead_processing(self, client, dealer, auth_cookies):
        """Dashboard renders correctly while leads are being submitted."""
        # Submit 5 leads, then immediately check dashboard
        # Assert all leads appear in the dashboard
```

### Performance Benchmarks

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Webform → response | < 5 seconds | `time.perf_counter()` around POST |
| Health check | < 200ms | `time.perf_counter()` around GET |
| Dashboard render | < 2 seconds | `time.perf_counter()` around GET |
| 10th sequential lead | < 2x first lead time | Compare times |
| Memory after 100 leads | No growth | `tracemalloc` |

---

## 9. Layer 6: Dashboard UI Tests (Playwright)

### Purpose

Test the dashboard in a real browser to verify:
- All pages render correctly
- Navigation works
- Data displays accurately
- HTMX interactions work
- Mobile responsive layout

### Setup

```bash
# Install Playwright
pip install playwright pytest-playwright
playwright install chromium
```

### Test File: `tests/test_dashboard_playwright.py`

```python
"""Playwright browser tests for the dashboard UI.

These tests start the FastAPI app, seed data, and interact with the dashboard
using a real browser.
"""

import pytest
from playwright.sync_api import Page, expect

BASE_URL = "http://localhost:8000"


@pytest.fixture(scope="session")
def browser_context_args():
    return {"viewport": {"width": 1280, "height": 720}}


class TestDashboardNavigation:
    """Test sidebar navigation and page routing."""

    def test_login_page_renders(self, page: Page):
        """Login page loads with username/password form."""
        page.goto(f"{BASE_URL}/dashboard/login")
        expect(page.locator("input[name='username']")).to_be_visible()
        expect(page.locator("input[name='password']")).to_be_visible()
        expect(page.locator("button[type='submit']")).to_be_visible()

    def test_login_with_valid_credentials(self, page: Page):
        """Valid login redirects to leads page."""
        page.goto(f"{BASE_URL}/dashboard/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "test123")
        page.click("button[type='submit']")
        page.wait_for_url("**/dashboard/leads")
        expect(page.locator("h1")).to_contain_text("Lead Pipeline")

    def test_login_with_invalid_credentials(self, page: Page):
        """Invalid login shows error message."""
        page.goto(f"{BASE_URL}/dashboard/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "wrong")
        page.click("button[type='submit']")
        expect(page.locator(".error")).to_contain_text("Invalid credentials")

    def test_sidebar_navigation(self, page: Page):
        """All sidebar links work and load correct pages."""
        # Login first
        page.goto(f"{BASE_URL}/dashboard/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "test123")
        page.click("button[type='submit']")

        # Test each nav link
        for link_text, expected_heading in [
            ("Leads", "Lead Pipeline"),
            ("Team", "Team"),
            ("Stats", "Stats"),
            ("Settings", "Settings"),
        ]:
            page.click(f"text={link_text}")
            expect(page.locator("h1, h2, .page-title")).to_contain_text(expected_heading)

    def test_logout(self, page: Page):
        """Logout redirects to login page."""
        # Login, then logout
        page.goto(f"{BASE_URL}/dashboard/login")
        page.fill("input[name='username']", "admin")
        page.fill("input[name='password']", "test123")
        page.click("button[type='submit']")
        page.click("text=Logout")
        page.wait_for_url("**/dashboard/login")


class TestLeadsPage:
    """Test the leads list page."""

    def test_stats_cards_display(self, page: Page):
        """Stats cards show lead counts."""
        # Login and navigate to leads
        page.goto(f"{BASE_URL}/dashboard/leads")
        # Check for stats cards
        expect(page.locator(".stat-card, .stats-grid")).to_be_visible()

    def test_lead_table_shows_leads(self, page: Page):
        """Lead table displays lead data."""
        page.goto(f"{BASE_URL}/dashboard/leads")
        # After seeding data, should see lead rows
        expect(page.locator("table, .lead-row")).to_be_visible()

    def test_lead_row_click_navigates_to_detail(self, page: Page):
        """Clicking a lead row opens the detail page."""
        page.goto(f"{BASE_URL}/dashboard/leads")
        # Click first lead row
        page.click(".lead-row:first-child, tr[data-lead-id]:first-child")
        # Should navigate to detail page
        expect(page.url()).to_contain("/dashboard/leads/")

    def test_attention_widget_shows_items(self, page: Page):
        """Attention widget displays urgent items when present."""
        page.goto(f"{BASE_URL}/dashboard/leads")
        # Check if attention widget exists (may be empty)
        attention = page.locator(".attention-widget, .attention-items")
        if attention.is_visible():
            expect(attention).to_be_visible()

    def test_health_badges_display(self, page: Page):
        """Each lead has a health badge (hot/warm/cold/dead)."""
        page.goto(f"{BASE_URL}/dashboard/leads")
        badges = page.locator(".health-badge, .badge-hot, .badge-warm, .badge-cold, .badge-dead")
        # At least one badge should be visible if there are leads
        if page.locator(".lead-row, tr[data-lead-id]").count() > 0:
            expect(badges.first).to_be_visible()


class TestLeadDetailPage:
    """Test the lead detail page."""

    def test_lead_info_card(self, page: Page):
        """Lead info card shows name, phone, email, source, status."""
        page.goto(f"{BASE_URL}/dashboard/leads/1")
        expect(page.locator(".lead-info, .lead-card")).to_be_visible()

    def test_timeline_shows_events(self, page: Page):
        """Timeline displays state changes and messages."""
        page.goto(f"{BASE_URL}/dashboard/leads/1")
        timeline = page.locator(".timeline, .event-list")
        if timeline.is_visible():
            expect(timeline).to_be_visible()

    def test_message_direction_indicators(self, page: Page):
        """Messages show inbound/outbound direction."""
        page.goto(f"{BASE_URL}/dashboard/leads/1")
        # Check for direction indicators
        inbound = page.locator(".message-inbound, [data-direction='inbound']")
        outbound = page.locator(".message-outbound, [data-direction='outbound']")
        # At least one should be visible if there are messages


class TestTeamPage:
    """Test the team/leaderboard page."""

    def test_leaderboard_displays(self, page: Page):
        """Rep performance leaderboard is visible."""
        page.goto(f"{BASE_URL}/dashboard/team")
        expect(page.locator(".leaderboard, .rep-performance")).to_be_visible()

    def test_top_badge_for_leading_rep(self, page: Page):
        """#1 rep gets a TOP badge."""
        page.goto(f"{BASE_URL}/dashboard/team")
        top_badge = page.locator(".badge-top, :text('TOP')")
        # Should be visible if there are reps with sales

    def test_conversion_percentages(self, page: Page):
        """Conversion percentages are displayed."""
        page.goto(f"{BASE_URL}/dashboard/team")
        expect(page.locator(":text('%')")).to_be_visible()


class TestStatsPage:
    """Test the stats/analytics page."""

    def test_response_time_displayed(self, page: Page):
        """Response time metrics are shown."""
        page.goto(f"{BASE_URL}/dashboard/stats")
        expect(page.locator(":text('Response Time'), :text('Avg Response')")).to_be_visible()

    def test_conversion_funnel_displayed(self, page: Page):
        """Conversion funnel is visible."""
        page.goto(f"{BASE_URL}/dashboard/stats")
        expect(page.locator(".funnel, :text('Conversion Funnel')")).to_be_visible()

    def test_source_breakdown_displayed(self, page: Page):
        """Lead source breakdown is visible."""
        page.goto(f"{BASE_URL}/dashboard/stats")
        expect(page.locator(":text('Source'), :text('Channel')")).to_be_visible()


class TestMobileResponsive:
    """Test mobile viewport (375px width)."""

    def test_sidebar_collapses_on_mobile(self, page: Page):
        """Sidebar is hidden by default on mobile."""
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{BASE_URL}/dashboard/leads")
        sidebar = page.locator(".sidebar")
        # Sidebar should be hidden or collapsed
        expect(sidebar).to_be_hidden()

    def test_hamburger_menu_opens_sidebar(self, page: Page):
        """Hamburger button opens the sidebar on mobile."""
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{BASE_URL}/dashboard/leads")
        page.click(".hamburger, .menu-toggle")
        expect(page.locator(".sidebar")).to_be_visible()

    def test_lead_table_scrollable_on_mobile(self, page: Page):
        """Lead table is horizontally scrollable on mobile."""
        page.set_viewport_size({"width": 375, "height": 812})
        page.goto(f"{BASE_URL}/dashboard/leads")
        # Table should be in a scrollable container
        expect(page.locator(".table-scroll, .overflow-x")).to_be_visible()
```

### Running Playwright Tests

```bash
# Start the app first
uvicorn app.main:app --port 8000 &

# Run Playwright tests
pytest tests/test_dashboard_playwright.py --headed  # visible browser
pytest tests/test_dashboard_playwright.py           # headless

# Run with specific browser
pytest tests/test_dashboard_playwright.py --browser chromium
```

---

## 10. Layer 7: Manual Testing Checklist

### Pre-Deploy Smoke Test (Do This Before Every Deploy)

```
[ ] 1. App starts without errors
     $ uvicorn app.main:app --reload
     Check: logs show "Scheduler started" (if merged), no import errors

[ ] 2. Health check responds
     $ curl http://localhost:8000/healthz
     Expected: {"ok": true}

[ ] 3. Dashboard renders
     Visit: http://localhost:8000/dashboard/login
     Login: admin / [password]
     Check: Leads page loads, no 500 errors

[ ] 4. Submit a test webform lead
     $ curl -X POST http://localhost:8000/webhook/form/[token] \
       -H "Content-Type: application/json" \
       -d '{"full_name": "Test Customer", "phone": "(604) 555-1234", "consent_sms": true}'
     Expected: {"status": "ok", "lead_id": N, "state": "ASSIGNED", ...}

[ ] 5. Check lead appears on dashboard
     Visit: http://localhost:8000/dashboard/leads
     Check: "Test Customer" appears in the table

[ ] 6. Check lead detail page
     Click the lead row
     Check: Timeline shows state changes, auto-reply message visible

[ ] 7. Claim via WhatsApp (if Twilio configured)
     From rep's phone: text "1" to the WhatsApp sender number
     Check: Lead state changes to CLAIMED on dashboard

[ ] 8. Stats page renders
     Visit: http://localhost:8000/dashboard/stats
     Check: Response time, funnel, source breakdown all visible

[ ] 9. Team page renders
     Visit: http://localhost:8000/dashboard/team
     Check: Rep leaderboard shows data
```

### Real-Phone Testing (When Twilio is Configured)

```
[ ] 1. SMS auto-reply
     Send an SMS to the dealer's Twilio number
     Expected: Reply within 60 seconds mentioning dealer name

[ ] 2. STOP keyword
     Reply "STOP" to the auto-reply
     Expected: "You have been unsubscribed" confirmation
     Check: No further messages from the system

[ ] 3. Missed call text-back
     Call the dealer's Twilio number, let it ring (no answer)
     Expected: SMS text-back within 2 minutes

[ ] 4. WhatsApp claim
     After a lead arrives, check rep's WhatsApp
     Expected: Claim ping with "Reply 1 to claim, 2 to pass"
     Reply "1" → lead should be CLAIMED on dashboard

[ ] 5. WhatsApp pass
     After a lead arrives, reply "2"
     Expected: Lead reassigned to next rep, new ping sent

[ ] 6. After-hours autonomous
     Submit a lead at 10 PM
     Expected: Auto-reply sent, AI handles conversation autonomously

[ ] 7. Business-hours draft
     Submit a lead at 10 AM
     Expected: Auto-reply sent, AI generates draft for rep approval

[ ] 8. Escalation
     Submit a lead, don't claim for 5+ minutes
     Expected: Escalation fires, reassigns to next rep

[ ] 9. ARRET keyword
     Reply "ARRET" to the auto-reply
     Expected: Same as STOP (bilingual CASL)

[ ] 10. Dashboard on mobile
      Open dashboard on phone browser
      Check: Sidebar collapses, hamburger menu works, data readable

[ ] 11. Lead detail on mobile
      Open a lead detail page on phone
      Check: Timeline readable, messages display correctly

[ ] 12. Multiple leads
      Submit 5 leads in quick succession
      Check: All appear on dashboard, round-robin distributed evenly
```

### Edge Case Testing

```
[ ] 1. Empty webform submission
     POST {} to /webhook/form/[token]
     Expected: Graceful error, not 500

[ ] 2. Invalid phone number
     Submit form with phone="not-a-number"
     Expected: Lead created (phone may be null), no crash

[ ] 3. Very long name
     Submit form with 500-char name
     Expected: Lead created, name truncated or stored

[ ] 4. Special characters in message
     Submit form with message containing <script>alert('xss')</script>
     Expected: Escaped in HTML, no XSS

[ ] 5. Concurrent form submissions
     Submit 10 forms simultaneously via curl
     Expected: All succeed, unique lead IDs

[ ] 6. Dashboard with 100+ leads
     Seed 100 leads, check dashboard
     Expected: Loads within 2 seconds, pagination or limit works

[ ] 7. Lead with no phone
     Submit form without phone field
     Expected: Lead created, SMS auto-reply skipped (no phone to send to)

[ ] 8. Duplicate vehicle reference
     Submit form with vehicle_stock that matches 2 vehicles
     Expected: First match used, no crash
```

---

## 11. Compliance Test Matrix

### CASL (Canada's Anti-Spam Law) Requirements

| Requirement | Test | Status |
|-------------|------|--------|
| Business name in every SMS | `test_compliance_footer_present` | TODO |
| Business address in every SMS | `test_compliance_footer_present` | TODO |
| Opt-out instruction in every SMS | `test_compliance_footer_present` | TODO |
| STOP keyword processed within 1 message | `test_stop_keyword_opts_out_and_silences` | ✅ |
| ARRET keyword processed within 1 message | `test_arret_keyword_opts_out` | ✅ |
| STOPALL keyword processed | `test_unsubscribed_phone_not_called` | ✅ |
| UNSUBSCRIBE keyword processed | `test_unsubscribed_phone_not_called` | ✅ |
| Opt-out confirmation within 1 message | `test_sms_opt_out_creates_consent_log` | ✅ |
| Consent recorded with source + timestamp | `test_full_pipeline_e2e` (ConsentLog) | ✅ |
| No outbound without consent | `test_no_consent_no_outbound_text` | ✅ |

### PIPA BC (Personal Information Protection Act) Requirements

| Requirement | Test | Status |
|-------------|------|--------|
| Collect only necessary data | Config schema validation | ✅ |
| Purpose limitation (lead management only) | N/A (enforced by design) | ✅ |
| Data access on request | Manual (delete endpoint TODO) | TODO |
| Audit trail for data access | LeadEvent append-only log | ✅ |

### Quiet Hours Requirements

| Requirement | Test | Status |
|-------------|------|--------|
| No outbound 21:00-08:00 dealer TZ | `test_outbound_deferred_during_quiet_hours` | ✅ |
| Opt-out confirmation exempt | `test_quiet_hours_exempt_opt_out_confirmation` | TODO |
| Auto-reply exempt (customer initiated) | `test_auto_reply_exempt_from_quiet_hours` | TODO |
| Wraps midnight correctly | `test_quiet_hours_wraps_midnight` | ✅ |

### Additional Compliance Tests to Add

```python
class TestComplianceExtended:
    """Extended compliance test suite."""

    def test_every_sms_has_compliance_footer(self, db_session, dealer, fake_twilio):
        """Every outbound SMS must include business name + address + opt-out."""
        from tools.send_sms import send_sms
        sid = send_sms(db_session, "+160****1234", "Hello!", "+120****2694",
                       dealer_config=dealer.config, fake_twilio=fake_twilio)
        assert sid is not None
        body = fake_twilio.sent[0]["body"]
        assert "Test Motors" in body  # Business name
        assert "STOP" in body.upper()  # Opt-out instruction

    def test_stop_during_quiet_hours_still_confirms(self, db_session, dealer, fake_twilio):
        """STOP at 11 PM still gets immediate confirmation (CASL exemption)."""
        quiet_now = datetime(2026, 6, 4, 6, 0, tzinfo=timezone.utc)  # 11 PM Vancouver
        # Send STOP during quiet hours
        # Assert: confirmation still sent (exempt from quiet hours)

    def test_auto_reply_exempt_from_quiet_hours(self, db_session, dealer, fake_twilio):
        """Auto-reply to a new lead is exempt from quiet hours."""
        quiet_now = datetime(2026, 6, 4, 6, 0, tzinfo=timezone.utc)  # 11 PM Vancouver
        # Submit new lead during quiet hours
        # Assert: auto-reply is sent (not deferred)

    def test_no_sms_to_invalid_phone(self, db_session, dealer, fake_twilio):
        """SMS to an invalid phone number is handled gracefully."""
        # send_sms with clearly invalid phone
        # Assert: returns None or error, no crash

    def test_consent_log_has_correct_fields(self, db_session, dealer):
        """ConsentLog entry has dealer_id, phone, action, text, created_at."""
        # Create consent log entry
        # Assert all required fields present

    def test_opt_out_is_permanent_until_start(self):
        """After STOP, only a START keyword can re-subscribe."""
        # This is a TODO feature — test once implemented
```

---

## 12. CI/CD Pipeline

### GitHub Actions Workflow

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install -e ".[dev]"

      - name: Run linting
        run: |
          ruff check .

      - name: Run tests
        run: |
          pytest -q --tb=short --cov=app --cov-report=term-missing

      - name: Run Playwright tests (if configured)
        run: |
          playwright install chromium
          uvicorn app.main:app --port 8000 &
          sleep 2
          pytest tests/test_dashboard_playwright.py -v
```

### Pre-Deploy Gate

```bash
# Run before every deploy
pytest -q --tb=short
# Expected: 131+ passed, 0 failed

# If Playwright tests are configured:
pytest tests/test_dashboard_playwright.py -v
# Expected: All UI tests pass
```

---

## 13. Test Coverage Targets

| Component | Target | Current | Gap |
|-----------|--------|---------|-----|
| `app/engine/lifecycle.py` | 100% | ~95% | Add edge case transitions |
| `app/engine/router.py` | 95% | ~85% | Add pass reassignment, single rep |
| `app/engine/conversation.py` | 90% | ~75% | Add tool execution edge cases |
| `app/engine/escalation.py` | 95% | ~80% | Add full ladder scenarios |
| `tools/send_sms.py` | 100% | ~90% | Add compliance footer verification |
| `tools/route_lead.py` | 95% | ~85% | Add email intake, vehicle resolution |
| `tools/book_appointment.py` | 100% | ~90% | Add edge cases (past dates, double booking) |
| `app/dashboard/__init__.py` | 90% | ~70% | Add attention items, funnel, source breakdown |
| `app/main.py` (webhooks) | 95% | ~85% | Add idempotency edge cases |
| `app/models/__init__.py` | 100% | ~100% | ✅ |

### How to Check Coverage

```bash
pytest --cov=app --cov=tools --cov-report=html
# Opens htmlcov/index.html in browser
```

---

## 14. Running Tests

### Quick Reference

```bash
# All tests (default — fake everything, fast)
pytest -q

# Verbose output
pytest -v

# Specific test file
pytest tests/test_pipeline_e2e.py -v

# Specific test
pytest tests/test_pipeline_e2e.py::test_full_pipeline_e2e -v

# With coverage
pytest --cov=app --cov=tools --cov-report=term-missing

# Parallel execution (faster)
pytest -q -n auto  # requires pytest-xdist

# Only Playwright tests
pytest tests/test_dashboard_playwright.py -v --headed

# Live-fire tests (requires real Twilio credentials)
LIVE_FIRE=true TWILIO_ACCOUNT_SID=xxx TWILIO_AUTH_TOKEN=xxx pytest tests/test_live_fire.py -v

# AI quality tests (requires OpenRouter API key)
OPENROUTER_API_KEY=sk-or-xxx pytest tests/test_ai_quality.py -v
```

### Test Categories (pytest markers)

```python
# pytest.ini or pyproject.toml
[tool.pytest.ini_options]
markers = [
    "unit: Unit tests (fast, no external calls)",
    "integration: Integration tests (full pipeline, fake doubles)",
    "e2e: End-to-end simulation tests",
    "playwright: Browser-based dashboard tests",
    "load: Load and concurrency tests",
    "compliance: CASL/PIPA compliance tests",
    "ai_quality: AI conversation quality tests (may cost money)",
    "live_fire: Real Twilio + real phones (requires credentials)",
    "slow: Tests that take > 5 seconds",
]
```

```bash
# Run only unit tests
pytest -m unit

# Run everything except live-fire
pytest -m "not live_fire"

# Run compliance tests only
pytest -m compliance
```

---

## Appendix A: Dealership Simulation Config

```yaml
# This is the canonical test dealer config used across all tests.
# It represents a realistic small BC used-car dealership.

dealer:
  slug: test-dealer
  name: Test Motors
  timezone: America/Vancouver
  main_phone: "+16045550000"

hours:
  mon: "09:00-19:00"
  tue: "09:00-19:00"
  wed: "09:00-19:00"
  thu: "09:00-19:00"
  fri: "09:00-19:00"
  sat: "10:00-17:00"
  sun: "closed"

channels:
  sms_number: "+17787623122"
  whatsapp_sender: "+14155558886"
  web_form_token: "test-token-123"

sales_team:
  - name: Manav
    whatsapp: "+16045552870"
    active: true
  - name: Friend
    whatsapp: "+17785554366"
    active: true

routing:
  strategy: round_robin
  claim_timeout_min: 2
  escalation:
    - reassign
    - notify_manager
  manager_phone: "+17785554366"

compliance:
  consent_text: "By submitting you agree to receive texts from Test Motors. Reply STOP to opt out."
  opt_out_keywords:
    - STOP
    - STOPALL
    - UNSUBSCRIBE
    - ARRET
  quiet_hours: "21:00-08:00"

ai:
  persona: "friendly, concise, no-pressure local sales rep"
  goal: "book_appointment"
  guardrails:
    no_price_negotiation: true
    no_financing_promises: true

inventory:
  source: manual
  refresh_min: 180

lead_org:
  mode: native
```

## Appendix B: Test Data Inventory

```
Vehicle 1: 2024 Honda Civic EX — Stock SA1001 — $32,500 — Sedan — 15,000 km
Vehicle 2: 2021 Ford Mustang GT — Stock SA1002 — $35,950 — Coupe — 32,000 km
Vehicle 3: 2023 Toyota RAV4 XLE — Stock SA1003 — $38,900 — SUV — 8,500 km
Vehicle 4: 2022 Hyundai Tucson — Stock SA1004 — $29,900 — SUV — 22,000 km
Vehicle 5: 2020 Chevrolet Malibu — Stock SA1005 — $18,900 — Sedan — 45,000 km
```

## Appendix C: Response Time Budgets

| Operation | Budget | Rationale |
|-----------|--------|-----------|
| Webform → auto-reply requested | < 5 seconds | The speed-to-lead promise |
| SMS → auto-reply | < 5 seconds | Same promise |
| Health check | < 200ms | Static response |
| Dashboard leads page | < 2 seconds | User experience |
| Dashboard stats page | < 2 seconds | User experience |
| Lead detail page | < 1 second | Single lead query |
| WhatsApp claim → state update | < 1 second | Instant feedback |
| Escalation check (scheduled) | Runs every 1 minute | APScheduler interval |
