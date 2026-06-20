# Phase 1: Critical Bugs

## Task 1.1: Fix daily digest crash ✅

**Bug:** `send_daily_digest()` in `app/scheduler.py` referenced `dealer.id` at line ~422, but `dealer` was never defined — only `dealer_slug` was passed. Would crash with `NameError` when the job runs.

**Root cause:** The function received `dealer_slug` (a string) and `dealer_config` (a dict), but the line `Lead.dealer_id == dealer.id` expected a Dealer ORM object. The `dealer` variable existed in the caller (`_run_daily_digest_for_all_dealers_session` loop at line 343), but wasn't available inside `send_daily_digest`.

**Fix:** Added a Dealer lookup by slug at the top of `send_daily_digest()`:
```python
dealer = session.execute(
    select(Dealer).where(Dealer.slug == dealer_slug)
).scalars().first()
if dealer is None:
    logger.warning("No dealer found for slug %s — skipping digest", dealer_slug)
    return
```

**Verification:**
- RED test (`test_send_daily_digest_does_not_crash`) confirmed crash with `xfail`
- After fix: 2 new tests pass
- Full suite: 130 passed, 1 skipped (no regressions)

**Files changed:**
- `app/scheduler.py` — added Dealer import + slug lookup (+10 lines)
- `tests/test_digest_crash.py` — new test file (2 tests)

**Commit:** `79c4f45 Phase 1.1: Fix daily digest crash — undefined dealer variable`

## Task 1.2: Fix greeting_only lifecycle bypass 🔲

**Not started.** Next up.

## Task 1.3: Fix pass_count persistence 🔲

## Task 1.4: Fix phone masking in email adapter 🔲

## Task 1.5: Fix consent=False in email adapter 🔲
