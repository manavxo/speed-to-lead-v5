# Mimo Kickoff — Engine Test Harness

Paste this to Mimo to start the dry-run engine test.

---

TASK: Build and run the AI engine test harness, then write the report.

Read the full spec first: NOTES/ENGINE_TEST_HARNESS_SPEC.md — follow it exactly.

Summary of what to build:
- Create scripts/engine_test_harness.py (upgrade the existing test_t2_ai_engine.py
  pattern). It drives the REAL conversation engine in-process via handle_turn() — no
  fake_llm, real DeepSeek/GPT-4o-mini.
- Load dealers/premier-auto.yaml as the dealer_config (real sales_team + Telegram
  routing; Helly is the only active rep, chat_id 8990699115).
- Seed inventory + a fresh lead per scenario on in-memory SQLite.
- Run scenarios S1–S8 from the spec.
- Score deterministic checks D1–D8 in code (pass/fail).
- Capture every transcript.
- Write NOTES/ENGINE_TEST_REPORT.md in the format the spec specifies.

HARD RULES:
- OUTBOUND_ENABLED=false the whole time. This is a DRY RUN. No real SMS, no real
  Telegram, nobody's phone gets pinged. Confirm the env before running.
- Verify lead assignment + rep notification by reading the logged rep Message row
  and the resolved rep config (assigned_rep == Helly, backend telegram, chat_id
  8990699115) — NOT by anyone receiving anything.
- Requires OPENROUTER_API_KEY (tool turns) + DEEPSEEK_API_KEY (chat). If
  OPENROUTER_API_KEY is missing, print a loud warning in the report (tool reliability
  degrades) and continue.
- DO NOT fix any engine bugs you find. Report only — expected vs actual for every
  failure. Fixing is a separate decision.

DONE = scripts/engine_test_harness.py runs clean and NOTES/ENGINE_TEST_REPORT.md
exists with all D1–D8 scored + every transcript captured.
