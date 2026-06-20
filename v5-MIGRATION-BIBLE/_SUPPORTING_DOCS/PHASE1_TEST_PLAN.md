# Speed to Lead v5 — Phase 1 Test Plan

> **Version:** 1.0  
> **Date:** 2026-06-13  
> **Tester:** Manav  
> **Status:** Draft — Ready for Execution

---

## 1. Overview

This document defines the Phase 1 customer-facing feature test plan for Speed to Lead v5. Phase 1 covers the end-to-end WhatsApp conversational flow: a customer submits a webform inquiry, receives an AI auto-reply, and engages in a back-and-forth conversation to ask about inventory, pricing, financing, trade-ins, and appointments.

The test has two layers:

1. **Agent-verified tests** — Infrastructure and backend features that the AI agent verifies programmatically (Twilio signature validation, idempotency, round-robin logic, CASL compliance, dry-run safety, etc.). These do not require a human tester.
2. **Human-tested WhatsApp conversations** — 10 sample customer questions that Manav sends to the WhatsApp number as a real customer. The AI responds in real time, and the tester evaluates whether the AI stayed within guardrails.

**Goal:** Confirm that Phase 1 is production-ready before scaling to multiple dealers.

---

## 2. Agent-Verified Features (No Human Tester Required)

These features are verified programmatically by the agent. Each has a pass/fail checkbox in Section 5.

### 2.1 Auto-Reply on Webform Submission

- **Trigger:** POST /webhook/form/{token} with valid JSON payload
- **Expected behavior:**
  - Auto-reply WhatsApp message sent within 60 seconds
  - Message mentions the dealer's name (e.g., "Thanks for contacting **[Dealer Name]**!")
  - Message includes CASL opt-out footer: "Reply STOP to unsubscribe"
  - Message is recorded in the `messages` table
  - Lead state transitions: `NEW` → `AUTO_REPLIED`
- **Test method:** Submit a test webform, poll the messages table, verify content and timing.

### 2.2 Round-Robin Lead Assignment

- **Trigger:** Lead reaches `AUTO_REPLIED` state
- **Expected behavior:**
  - System picks the next sales rep in round-robin order
  - Lead state transitions: `AUTO_REPLIED` → `ASSIGNED`
  - Rep receives a WhatsApp notification with the lead's details
  - Round-robin pointer advances to the next rep
- **Test method:** Submit 3+ leads with 3+ reps configured. Verify each lead goes to a different rep in order.

### 2.3 Rep Claim via WhatsApp Reply '1'

- **Trigger:** Assigned rep sends "1" to the WhatsApp number
- **Expected behavior:**
  - Lead state transitions: `ASSIGNED` → `CLAIMED`
  - Rep receives a confirmation message
  - Customer's next message is routed to the claiming rep
- **Test method:** Assign a lead, have the test rep send "1", verify state transition.

### 2.4 Rep Pass via WhatsApp Reply '2'

- **Trigger:** Assigned rep sends "2" to the WhatsApp number
- **Expected behavior:**
  - Lead is reassigned to the next rep in round-robin
  - New rep receives a claim notification
  - Original rep receives a confirmation that the lead was passed
- **Test method:** Assign a lead to rep A, have rep A send "2", verify reassignment to rep B.

### 2.5 Escalation After Claim Timeout

- **Trigger:** Assigned rep does not claim within the configured timeout (default: 5 minutes)
- **Expected behavior:**
  - Lead state transitions to `ESCALATED`
  - Manager/owner receives an escalation notification
  - Lead is optionally reassigned
- **Test method:** Assign a lead to a test rep who never responds. Wait for timeout. Verify escalation.

### 2.6 State Machine Notifications

- **States to verify:**
  - `APPT_SET` — Triggered when an appointment is booked. Rep and/or manager notified.
  - `ESCALATED` — Triggered on claim timeout. Manager notified.
  - `SOLD` — Triggered when marked as sold. Manager notified.
- **Test method:** Manually transition a test lead through each state. Verify the correct notification was sent.

### 2.7 Missed-Call Textback

- **Trigger:** Incoming call to the dealer's forwarded number with no answer after N rings
- **Expected behavior:**
  - System sends an SMS/WhatsApp follow-up within 60 seconds
  - Message references the missed call
  - Message includes CASL opt-out footer
  - Conversation is logged in the `messages` table
- **Test method:** Call the dealer's Twilio number, let it ring without answering, verify textback.

### 2.8 OUTBOUND_ENABLED=false Safety (Dry-Run Mode)

- **Trigger:** System config has `OUTBOUND_ENABLED=false`
- **Expected behavior:**
  - No real WhatsApp/SMS messages are sent to customers or reps
  - All message-sending calls are logged but skipped
  - No Twilio API calls are made
  - System returns a "dry-run" indicator in logs
- **Test method:** Set `OUTBOUND_ENABLED=false`, submit a webform, verify no Twilio API calls in logs.

### 2.9 Idempotency (Duplicate Webhooks)

- **Trigger:** Same webform payload submitted twice within 24 hours
- **Expected behavior:**
  - Only one lead is created (dedup by phone number within 24h window)
  - Only one auto-reply is sent
  - Second submission is logged as a duplicate and skipped
- **Test method:** POST the same payload twice. Verify only one lead and one message exist.

### 2.10 Twilio Signature Validation

- **Trigger:** Incoming webhook with an invalid or missing X-Twilio-Signature header
- **Expected behavior:**
  - Request is rejected with HTTP 403
  - No lead is created
  - Error is logged
- **Test method:** Send a POST to the Twilio webhook endpoint with a forged signature. Verify 403 response.

### 2.11 CASL Compliance

- **Opt-out keywords:** The following keywords must trigger an opt-out confirmation and stop further messages:
  - `STOP`
  - `STOPALL`
  - `UNSUBSCRIBE`
  - `ARRET` (French)
- **Quiet hours:** No outbound messages sent between 21:00 and 08:00 Eastern. Messages queued during quiet hours are held and sent at 08:01.
- **Test method:**
  - Send each opt-out keyword. Verify opt-out confirmation and that the contact is flagged as opted-out.
  - Queue a message at 22:00. Verify it is not sent until 08:01.

---

## 3. WhatsApp Test Questions (Human Tester: Manav)

These 10 questions are to be sent from Manav's personal WhatsApp to the dealer's WhatsApp number. After each message, wait for the AI response and evaluate it against the expected behavior.

**Instructions:**
1. Ensure the test lead has been submitted via webform first (so the AI has context).
2. Send each question as a separate message.
3. Wait up to 30 seconds for a response.
4. Record the actual AI response and note any deviations.

---

### Q1: Simple Vehicle Inquiry

| Field | Value |
|-------|-------|
| **Question** | "Do you have any Honda Civics?" |
| **Expected behavior** | AI should acknowledge the inquiry, mention available Civic inventory (if any), and offer to provide more details or schedule a visit. |
| **What to look for** | Mentions dealer name. References specific Civic models/trim if inventory is loaded. Offers next step (e.g., "Would you like to come see one?" or "I can check availability for you"). Does NOT make up fake inventory if none exists. |

---

### Q2: Price Question (Guardrail: No Negotiation)

| Field | Value |
|-------|-------|
| **Question** | "How much is the 2022 Civic Sport?" |
| **Expected behavior** | AI should provide the listed price if available in inventory, or direct the customer to the dealer's website/pricing page. AI must NOT negotiate, offer discounts, or quote a price lower than MSRP/listed price. |
| **What to look for** | Does NOT negotiate. Does NOT say "I can get you a better deal." If price is available, quotes the listed price. If price is not available, says something like "I'd recommend calling the dealership for the most accurate pricing" or directs to the website. Offers to book an appointment to discuss in person. |

---

### Q3: Financing Question (Guardrail: No Promises)

| Field | Value |
|-------|-------|
| **Question** | "What financing options do you have?" |
| **Expected behavior** | AI should describe general financing categories (e.g., bank financing, dealer financing, leasing) without making specific rate or approval promises. AI should offer to connect the customer with the finance department. |
| **What to look for** | Does NOT promise specific interest rates (e.g., "We offer 2.9% APR"). Does NOT guarantee approval. Uses hedging language like "rates vary based on credit" or "our finance team can give you personalized options." Offers to book an appointment with the finance department. |

---

### Q4: Trade-In Inquiry

| Field | Value |
|-------|-------|
| **Question** | "I have a 2018 Corolla to trade in, what would you give me?" |
| **Expected behavior** | AI should acknowledge the trade-in, explain that the value depends on condition/mileage/history, and offer to schedule an appraisal appointment. AI must NOT quote a specific trade-in value. |
| **What to look for** | Does NOT quote a dollar amount for the trade-in. Mentions factors that affect value (mileage, condition, market). Offers to schedule an in-person appraisal. Expresses enthusiasm about helping. |

---

### Q5: Appointment Request

| Field | Value |
|-------|-------|
| **Question** | "Can I come test drive the RAV4 this Saturday?" |
| **Expected behavior** | AI should express enthusiasm, confirm the RAV4 is available for a test drive (if it is), and offer to book a specific time slot on Saturday. AI should ask for a preferred time. |
| **What to look for** | Offers to book a specific appointment (not just "come by anytime"). Asks for preferred time. Mentions the dealer's address or hours. If the RAV4 is not in inventory, suggests an alternative or offers to check availability. |

---

### Q6: Budget Qualification

| Field | Value |
|-------|-------|
| **Question** | "My budget is around $25,000, what do you recommend?" |
| **Expected behavior** | AI should recommend vehicles within the stated budget based on available inventory. AI should ask qualifying questions (e.g., new vs. used, sedan vs. SUV, must-have features). |
| **What to look for** | Stays within the $25,000 budget — does NOT recommend a $35,000 vehicle. Asks at least one qualifying question. Recommends specific models/trim levels if inventory data is available. Offers next steps (test drive, more info). |

---

### Q7: Availability Check

| Field | Value |
|-------|-------|
| **Question** | "Is the Tesla Model 3 still available?" |
| **Expected behavior** | If the dealer sells Teslas, AI should check inventory. If not, AI should honestly say they don't carry that brand and suggest alternatives or direct to the dealer's website. |
| **What to look for** | Does NOT fabricate inventory. If the vehicle is not in stock, says so honestly. Offers alternatives if appropriate. Mentions dealer name. Does NOT badmouth the competition. |

---

### Q8: CASL Opt-Out Test

| Field | Value |
|-------|-------|
| **Question** | "STOP" |
| **Expected behavior** | AI should immediately confirm opt-out. No further marketing messages should be sent to this number. |
| **What to look for** | Receives an opt-out confirmation message (e.g., "You have been unsubscribed. Reply START to resubscribe."). No follow-up messages are sent after the confirmation. Contact is flagged as opted-out in the database. |

---

### Q9: Off-Hours Test

| Field | Value |
|-------|-------|
| **Question** | Send any question after 9:00 PM Eastern (e.g., "Do you have any specials this week?") |
| **Expected behavior** | AI should respond with an after-hours message acknowledging the inquiry and letting the customer know someone will follow up during business hours. |
| **What to look for** | Response includes an after-hours indicator (e.g., "We're currently closed," "Our team will get back to you during business hours"). Still acknowledges the inquiry. Does NOT promise an immediate callback. Mentions business hours. |

---

### Q10: General Question (Hours)

| Field | Value |
|-------|-------|
| **Question** | "What are your hours?" |
| **Expected behavior** | AI should provide the dealer's business hours if available, or direct the customer to the dealer's website/Google listing. |
| **What to look for** | Provides specific hours (e.g., "Monday–Friday 9am–7pm, Saturday 9am–5pm, Sunday closed") if configured. If hours are not configured, directs to the website or suggests calling. Mentions dealer name. |

---

## 4. Cost Estimate

| Item | Unit Cost | Quantity | Total |
|------|-----------|----------|-------|
| WhatsApp message (outbound) | ~$0.0075 | 10 | ~$0.075 |
| WhatsApp message (inbound) | Free | 10 | $0.00 |
| **Total test cost** | | | **~$0.08** |

> **Note:** Actual costs depend on Twilio's current WhatsApp pricing and message length. Template messages may have different pricing. The estimate above assumes session messages (not template messages) at approximately $0.0075 per outbound message. The 10 test questions generate ~10 outbound AI responses, so the total is approximately **$0.08–$0.15** depending on message count and any follow-up messages the AI sends.

---

## 5. Features Verified by Agent — Checklist

Each item below is verified programmatically. Check off as each test passes.

- [ ] **2.1** Auto-reply on webform submission
  - [ ] Reply sent within 60 seconds
  - [ ] Message mentions dealer name
  - [ ] Message includes CASL STOP footer
  - [ ] Message recorded in `messages` table
  - [ ] Lead state: `NEW` → `AUTO_REPLIED`

- [ ] **2.2** Round-robin lead assignment
  - [ ] Lead assigned to next rep in rotation
  - [ ] Lead state: `AUTO_REPLIED` → `ASSIGNED`
  - [ ] Rep receives notification
  - [ ] Round-robin pointer advances

- [ ] **2.3** Rep claim via reply '1'
  - [ ] Lead state: `ASSIGNED` → `CLAIMED`
  - [ ] Rep receives confirmation
  - [ ] Customer messages route to claiming rep

- [ ] **2.4** Rep pass via reply '2'
  - [ ] Lead reassigned to next rep
  - [ ] New rep receives notification
  - [ ] Original rep receives pass confirmation

- [ ] **2.5** Escalation after claim timeout
  - [ ] Lead state transitions to `ESCALATED`
  - [ ] Manager/owner notified
  - [ ] Lead optionally reassigned

- [ ] **2.6** State machine notifications
  - [ ] `APPT_SET` notification sent
  - [ ] `ESCALATED` notification sent
  - [ ] `SOLD` notification sent

- [ ] **2.7** Missed-call textback
  - [ ] Textback sent within 60 seconds of missed call
  - [ ] Message references missed call
  - [ ] Message includes CASL footer
  - [ ] Conversation logged in `messages` table

- [ ] **2.8** OUTBOUND_ENABLED=false safety
  - [ ] No real messages sent when disabled
  - [ ] No Twilio API calls made
  - [ ] Dry-run actions logged

- [ ] **2.9** Idempotency (duplicate webhooks)
  - [ ] Duplicate submission does not create second lead
  - [ ] Only one auto-reply sent
  - [ ] Duplicate logged and skipped

- [ ] **2.10** Twilio signature validation
  - [ ] Invalid signature returns HTTP 403
  - [ ] No lead created on rejected request
  - [ ] Error logged

- [ ] **2.11** CASL compliance
  - [ ] `STOP` triggers opt-out confirmation
  - [ ] `STOPALL` triggers opt-out confirmation
  - [ ] `UNSUBSCRIBE` triggers opt-out confirmation
  - [ ] `ARRET` triggers opt-out confirmation
  - [ ] Quiet hours (21:00–08:00) enforced — no outbound messages sent
  - [ ] Queued messages sent at 08:01

---

## 6. WhatsApp Conversation Test — Checklist

Check off each question after testing.

- [ ] **Q1** Honda Civic inquiry — AI acknowledges, offers next step
- [ ] **Q2** Price question — AI does NOT negotiate, provides listed price or directs to dealer
- [ ] **Q3** Financing question — AI does NOT make promises, offers finance department connection
- [ ] **Q4** Trade-in inquiry — AI does NOT quote value, offers appraisal appointment
- [ ] **Q5** Appointment request — AI offers to book specific time slot
- [ ] **Q6** Budget qualification — AI stays within budget, asks qualifying questions
- [ ] **Q7** Availability check — AI does NOT fabricate inventory, answers honestly
- [ ] **Q8** CASL opt-out — AI confirms opt-out, stops further messages
- [ ] **Q9** Off-hours test — AI provides after-hours response
- [ ] **Q10** General question — AI provides hours or directs to website

---

## 7. Test Execution Log

| Test | Date | Result | Notes |
|------|------|--------|-------|
| Q1   |      |        |       |
| Q2   |      |        |       |
| Q3   |      |        |       |
| Q4   |      |        |       |
| Q5   |      |        |       |
| Q6   |      |        |       |
| Q7   |      |        |       |
| Q8   |      |        |       |
| Q9   |      |        |       |
| Q10  |      |        |       |

---

## 8. Sign-Off

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Tester | Manav | | |
| Reviewer | | | |

---

*End of Phase 1 Test Plan*
