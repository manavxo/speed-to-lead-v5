# Per-Rep Scheduling — How to Flip the Switch

Current mode: `dealer_wide` (all reps share the same dealer hours).
Goal: each rep has their own hours + per-slot capacity.

## 1. Flip the config key

In `dealers/premier-auto.yaml`, add:

```yaml
scheduling_mode: "per_rep"
```

And add per-rep hours (alongside existing YAML keys):

```yaml
sales_team:
  - name: "Helly"
    pin: "7721"
    phone: "+17785550199"
    active: true
    hours:
      mon: "09:00-17:00"
      tue: "09:00-17:00"
      ...
    max_appts_per_slot: 1
```

If a rep has no `hours`, fall back to the dealer-wide hours.

## 2. What changes in `tools/check_availability.py`

When `scheduling_mode == "per_rep"` (currently raises NotImplementedError):

- Read `sales_team` from dealer_config
- For each active rep, read their `hours` (or fall back to dealer hours)
- Generate slots per rep (intersection of rep + dealer hours)
- Deduplicate — same ISO slot appears once, with `rep_name` = list of available reps
- Remove slots where all reps have reached `max_appts_per_slot` (count existing appointments for each rep at that slot)

The `rep_name` field already exists on every slot dict — it's just `None` right now.

## 3. What changes in `tools/book_appointment.py`

When `scheduling_mode == "per_rep"`:

- Accept an optional `rep_name` parameter
- Validate that rep is available at the requested time
- Pin the Appointment to that rep

## 4. Tests to add

- `test_check_availability_per_rep` — slots tagged with rep names
- `test_book_appointment_per_rep` — rep capacity enforced
- `test_per_rep_hours_fallback_to_dealer` — rep without hours falls back to dealer hours
