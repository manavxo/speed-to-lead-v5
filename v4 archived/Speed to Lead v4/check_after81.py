from app.db import init_db, get_session_factory
from app.models import Message
from sqlalchemy import select, desc

init_db()
s = get_session_factory()()

# Find the most recent INBOUND message
inbound = s.execute(
    select(Message).where(Message.direction == 'inbound').order_by(Message.id.desc()).limit(3)
).scalars().all()

print("Recent INBOUND:")
for m in inbound:
    body = (m.body or "")[:120]
    print(f"  #{m.id} lead={m.lead_id} body={body}")

# Find ALL messages after #81 (the last known AI reply)
msgs = s.execute(
    select(Message).where(Message.id > 81).order_by(Message.id)
).scalars().all()

print(f"\nMessages after #81 ({len(msgs)} total):")
for m in msgs:
    body = (m.body or "")[:100]
    sid = (m.provider_sid or "")[:30]
    is_dryrun = "DRYRUN" in (m.provider_sid or "")
    flag = "DRY" if is_dryrun else "REAL"
    print(f"  #{m.id} [{flag}] lead={m.lead_id} dir={m.direction} body={body}")
