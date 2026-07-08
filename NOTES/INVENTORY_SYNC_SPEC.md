# Inventory Sync & Sold-Car Management — Build Spec (for Mimo / DeepSeek V4 Flash)

> **HOW TO READ THIS SPEC (DeepSeek V4 Flash):** Do the steps in order. Do exactly what each step says.
> The code blocks are copy-paste ready — paste them, adjust only what the step tells you to. Do NOT
> redesign, do NOT add extra features, do NOT refactor unrelated code. If something is unclear, re-read
> the step; the answer is in the KEY FILES. After each task: run its test, then commit. After ALL tasks:
> push to git. Keep messages short. One task = one commit.

---

## WHAT & WHY (1 paragraph)
The Manager uploads inventory at **Dashboard → Settings → Inventory**. Today the upload **upserts by
`stock_no`** (updates matches, adds new) but **never removes cars missing from the new file**, and it
**forces every row to `status="available"`**. So when a dealer sells a car and uploads a smaller feed, the
sold car stays live and the AI still offers it. We are adding: (I1) a full-sync mode that removes missing
cars, (I2) a per-row `status` column, (I3) one-click Mark sold / Relist buttons, (I4) a locked guarantee
the AI never offers a sold/removed car, (I5) a full test suite, then (I6) **commit + push to git**.

## ROLE
Senior Python/FastAPI engineer. Shell is **bash** (git-bash/MSYS), NOT PowerShell. Working dir:
`C:\Speed to Lead v5`. Confirm each thing in the code before changing it. Fix your own errors. Do not pester.

## HARD RULES (read every line)
1. **Run tests before every commit.** Command: `python -m pytest tests/` (bare `pytest` breaks on
   `v4 archived/`). **Baseline = 220 passed, 1 skipped.** Never commit red.
2. **One task = one commit.** Use `git add <specific files>`. NEVER `git add -A`.
3. **After ALL tasks pass: push to git** (Task I6). Render auto-deploys `main`. This is MANDATORY.
4. **After push: verify on the live prod site** with a real browser (Task I6).
5. **No real sends.** Keep `OUTBOUND_ENABLED=false` for all local runs. No real SMS/Telegram.
6. **Dealer scope every query.** Every DB read/write filters by `dealer_id == current_dealer.id`.
   NEVER touch another dealer's rows.
7. **Reuse existing code.** Do not rewrite the upload endpoint or templates from scratch.
8. **Record receipts** in `NOTES/FIX_RECEIPTS.md` (test output + commit SHA + prod screenshot).

## KEY FILES (open these before coding)
| File | What's there |
|------|--------------|
| `app/dashboard/__init__.py` | `upload_inventory` = `POST /dashboard/inventory/upload` (~line 2164). `settings_page` builds Inventory tab context `inventory`/`inventory_count` (~line 1496). `require_auth`, `get_dealer_from_auth`. `Form`, `select`, `HTMLResponse`, `Vehicle` already imported. |
| `app/dashboard/templates/settings.html` | The **Inventory** tab: form `#inventory-upload-form`, result div `#inventory-upload-result`, and the **Current Inventory** table. |
| `app/models/__init__.py` | `Vehicle` model. `status` is a string: `"available" | "sold" | "removed"`. Has `stock_no`, `dealer_id`, `raw`, `photos`. |
| `tools/check_inventory.py` | `search()` already does `.where(Vehicle.status == "available")`. This is the AI's only window into stock. |
| `tests/test_inventory_upload.py` | Has `_client(tmp_path)` and `_manager_cookie()` helpers + a `CSV` string. **Copy these for new tests.** |
| `tests/e2e/upload_inventory.js` | Real-browser upload script (login as Manager → Settings → Inventory → upload). **Copy this for live verify.** |
| `demo/premier-auto-inventory.csv` | The 20-car sample file = current prod inventory. |

---

# TASK I1 — Full-sync mode (remove cars missing from the file)

### Step I1.1 — Add the checkbox to the upload form
In `app/dashboard/templates/settings.html`, inside `#inventory-upload-form`, add this RIGHT BEFORE the
submit button (`#inventory-upload-btn`):
```html
<label style="display:flex; align-items:center; gap:8px; margin:0 0 14px;">
    <input type="checkbox" name="full_sync" value="on">
    This is my full current inventory — mark anything not in this file as removed
</label>
```

### Step I1.2 — Read the checkbox in the endpoint
In `app/dashboard/__init__.py`, in `upload_inventory(...)`, add ONE parameter to the function signature
(next to `file: UploadFile = File(...)`):
```python
    full_sync: str = Form(""),
```

### Step I1.3 — Collect the uploaded stock numbers
Inside `upload_inventory`, find the line `upserted = 0` (just before `for row_idx, row in enumerate(...)`).
Add one line under it:
```python
    upserted = 0
    uploaded_stock_nos = set()     # I1: track which stock_nos were in THIS file
```
Then inside the loop, right after the `if vehicle:` / `else:` block where `upserted += 1` happens, add:
```python
                uploaded_stock_nos.add(stock_no)
```

### Step I1.4 — Remove missing cars when full_sync is on
In `upload_inventory`, find `if upserted > 0: session.commit()`. Immediately AFTER it, add:
```python
        removed = 0
        if full_sync == "on" and uploaded_stock_nos:
            from sqlalchemy import update as sa_update
            res = session.execute(
                sa_update(Vehicle)
                .where(
                    Vehicle.dealer_id == current_dealer.id,
                    Vehicle.status != "removed",
                    Vehicle.stock_no.notin_(uploaded_stock_nos),
                )
                .values(status="removed")
            )
            removed = res.rowcount or 0
            session.commit()
```

### Step I1.5 — Report the removed count in the toast
Find the line that builds `msg = f'<div class="toast success">{upserted} vehicles uploaded.</div>'`.
Replace it with:
```python
        msg = f'<div class="toast success">{upserted} vehicles uploaded.'
        if full_sync == "on":
            msg += f' {removed} removed (not in file).'
        msg += '</div>'
```
**DONE I1.** Run `python -m pytest tests/ -q`. Then commit:
`git add app/dashboard/__init__.py app/dashboard/templates/settings.html`
`git commit -m "feat(inventory): full-sync mode removes cars missing from upload"`

---

# TASK I2 — Honor a `status` column in the file

### Step I2.1 — Read the status from each row
In `upload_inventory`, find where `raw_specs = {` is built (it uses `_clean(...)`). Just BEFORE the
`if vehicle:` block, add:
```python
                status_val = str(row.get("status", "")).strip().lower()
                if status_val not in ("available", "sold", "removed"):
                    status_val = "available"   # default / blank / unknown
```

### Step I2.2 — Use it instead of hardcoded "available"
In the SAME function, change BOTH places that say `status="available"`:
- In the `if vehicle:` branch, change `vehicle.status = "available"` → `vehicle.status = status_val`
- In the `else:` branch (the `Vehicle(...)` constructor), change `status="available",` → `status=status_val,`

**DONE I2.** Run tests. Commit:
`git add app/dashboard/__init__.py`
`git commit -m "feat(inventory): honor per-row status column on upload"`

---

# TASK I3 — Mark sold / Relist buttons in the dashboard

### Step I3.1 — Add the status endpoint
In `app/dashboard/__init__.py`, add this NEW endpoint right after the `upload_inventory` function ends:
```python
@router.post("/inventory/{stock_no}/status")
async def set_inventory_status(
    request: Request,
    stock_no: str,
    status: str = Form(...),
    _auth: dict = Depends(require_auth),
):
    """Manager sets a single vehicle's status (available | sold | removed)."""
    if _auth.get("role") != "manager":
        return HTMLResponse("Unauthorized", status_code=403)
    if status not in ("available", "sold", "removed"):
        return HTMLResponse("Invalid status", status_code=400)
    session = _get_session()
    try:
        cookie_value = request.cookies.get("session")
        current_dealer = get_dealer_from_auth(session, cookie_value) if cookie_value else None
        if not current_dealer:
            return HTMLResponse("Unauthorized", status_code=401)
        vehicle = session.execute(
            select(Vehicle).where(
                Vehicle.dealer_id == current_dealer.id,
                Vehicle.stock_no == stock_no,
            )
        ).scalars().first()
        if not vehicle:
            return HTMLResponse("Not found", status_code=404)
        vehicle.status = status
        session.commit()
        return HTMLResponse(f'<div class="toast success">{stock_no} set to {status}.</div>', status_code=200)
    finally:
        session.close()
```

### Step I3.2 — Add Status + Actions columns to the table
In `settings.html`, in the Current Inventory `<table>`: add a header cell `<th style="padding:6px 8px;">Status / Action</th>`
at the end of the header row, and add this as the LAST `<td>` in the `{% for v in inventory %}` row:
```html
                                <td style="padding:6px 8px;">
                                    <span style="margin-right:8px;">{{ v.status }}</span>
                                    {% if v.status == 'available' %}
                                    <button class="btn btn-secondary"
                                            hx-post="/dashboard/inventory/{{ v.stock_no }}/status"
                                            hx-vals='{"status":"sold"}'
                                            hx-target="#inventory-upload-result" hx-swap="innerHTML"
                                            hx-on::after-request="setTimeout(function(){location.reload();},600)">
                                        Mark sold
                                    </button>
                                    {% else %}
                                    <button class="btn btn-secondary"
                                            hx-post="/dashboard/inventory/{{ v.stock_no }}/status"
                                            hx-vals='{"status":"available"}'
                                            hx-target="#inventory-upload-result" hx-swap="innerHTML"
                                            hx-on::after-request="setTimeout(function(){location.reload();},600)">
                                        Relist
                                    </button>
                                    {% endif %}
                                </td>
```
**DONE I3.** Run tests. Commit:
`git add app/dashboard/__init__.py app/dashboard/templates/settings.html`
`git commit -m "feat(inventory): per-row mark-sold / relist in dashboard"`

---

# TASK I4 — Confirm the AI never offers a sold/removed car
Open `tools/check_inventory.py`. Confirm `search()` has `.where(Vehicle.status == "available")`.
It already does. **Do NOT change it.** (It is locked by a test in I5.) No commit for this task.

---

# TASK I5 — Test suite (the most important task)

Create `tests/test_inventory_sync.py`. Copy the helpers from `tests/test_inventory_upload.py`
(`_client`, `_manager_cookie`). Write these tests EXACTLY (same names). Each must check the DB AND
`check_inventory.search()`, not just the HTTP status.

```python
import io, time
from fastapi.testclient import TestClient
from app.main import app

def _manager_cookie(dealer_slug="premier-auto"):
    from app.dashboard import _get_serializer
    return {"session": _get_serializer().dumps(
        {"role":"manager","rep_name":"Manager","dealer_slug":dealer_slug,"ts":time.time()})}

def _client(tmp_path):
    import app.db as db
    from app.main import _auto_provision_dealers
    url=f"sqlite:///{(tmp_path/'inv.db').as_posix()}"
    db.init_db(url); db.get_session_factory(url); _auto_provision_dealers()
    return TestClient(app)

def _upload(client, csv, full_sync=False):
    data = {"full_sync":"on"} if full_sync else {}
    return client.post("/dashboard/inventory/upload",
        files={"file":("inv.csv", io.BytesIO(csv.encode()), "text/csv")},
        data=data, cookies=_manager_cookie())

HDR = "stock_no,year,make,model,trim,body,price,mileage\n"
def _row(stock, mk, md): return f"{stock},2023,{mk},{md},XLE,SUV,30000,10000\n"
```

Required test functions (write all of them):
1. `test_merge_mode_keeps_absent_cars` — upload [A,B,C] (no full_sync). Upload [B,D] (no full_sync).
   Assert all of A,B,C,D exist and are `available`.
2. `test_full_sync_removes_absent_cars` — upload [A,B,C]. Upload [A,B] with `full_sync=True`.
   Assert C.status == "removed"; assert `search(... query="<C model>")` returns no C.
3. `test_full_sync_scopes_to_current_dealer` — provision/seed a 2nd dealer with a vehicle (insert a
   `Vehicle` row directly with that dealer's id). Run full_sync for premier-auto. Assert the 2nd dealer's
   vehicle is still `available`.
4. `test_status_column_marks_sold` — upload a CSV that includes a `status` column with one row `sold`.
   Assert that car is not `available` and `search()` excludes it; a row with blank status is `available`.
5. `test_manual_mark_sold_and_relist` — upload [A]. POST `/dashboard/inventory/A/status` status=sold →
   A not in `search()`. POST status=available → A back in `search()`.
6. `test_check_inventory_excludes_sold_and_removed` — insert vehicles with status sold and removed
   directly; assert `search()` returns neither, for 2-3 queries.
7. `test_status_endpoint_requires_manager` — POST status with NO cookie →
   `follow_redirects=False` → 303 to `/dashboard/login`. With a rep cookie
   (`role":"rep"`) → 403. Assert the vehicle's status did NOT change.
8. `test_reupload_no_duplicate_stock` — upload [A] twice. Assert exactly ONE Vehicle row with stock_no A.

Run `python -m pytest tests/test_inventory_sync.py -q` until ALL pass. Then full suite
`python -m pytest tests/ -q` (must be ≥ 228 passed, 1 skipped). Commit:
`git add tests/test_inventory_sync.py`
`git commit -m "test(inventory): sync/full-sync/status/mark-sold suite"`

---

# TASK I6 — DEPLOY TO GIT (MANDATORY — do not skip)

After every task is committed and `python -m pytest tests/` is fully green:
```bash
git status                      # confirm only your intended files changed
git log --oneline -6            # confirm your commits are there
git push origin main            # THIS deploys — Render auto-deploys main
```
Then **verify on the live site** (copy `tests/e2e/upload_inventory.js` into a new
`tests/e2e/verify_inventory_sync.js`):
1. `cd tests/e2e && node verify_inventory_sync.js`
2. Log into prod dashboard as Manager (dealer `premier-auto`, PIN `1234`), open Settings → Inventory.
3. Click **Mark sold** on the RAV4 (PAG011). Screenshot the table showing RAV4 = sold.
4. Click **Relist** on the RAV4 to restore it (PAG011 back to `available`). Screenshot.
5. **Restore prod**: re-upload `demo/premier-auto-inventory.csv` (full 20, no full_sync) so prod is back to
   all 20 available.
Record the push SHA + screenshots in `NOTES/FIX_RECEIPTS.md`.

---

## DEFINITION OF DONE (check every box)
- [ ] I1 full-sync, I2 status column, I3 buttons all built in the dashboard (no separate page).
- [ ] `tests/test_inventory_sync.py`: all 8 tests pass. Full suite green (≥ 228 passed, 1 skipped).
- [ ] `check_inventory.search()` still only returns `available` cars (test #6 proves it).
- [ ] Code **committed AND pushed to `main`** (Task I6). Render deploy triggered.
- [ ] Live-verified on prod (Mark sold → AI can't see it; Relist → it's back). **Prod restored to 20.**
- [ ] Receipts in `NOTES/FIX_RECEIPTS.md`: test output, push SHA, screenshots.

## DO / DON'T (DeepSeek, re-read before you start)
- DO follow steps in order. DO paste the code blocks. DO run tests after each task. DO push at the end.
- DON'T add features not in this spec. DON'T change `check_inventory` filter. DON'T use `git add -A`.
  DON'T touch other dealers' rows. DON'T mark the task done until it's pushed AND live-verified.
