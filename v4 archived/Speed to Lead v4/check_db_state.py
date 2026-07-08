from app.db import init_db, get_session_factory
from app.models import Lead, Message
from sqlalchemy import select

init_db()
s = get_session_factory()()

leads = s.execute(select(Lead).order_by(Lead.id.desc()).limit(5)).scalars().all()
print("Recent leads:")
for l in leads:
    phone_bytes = [hex(b) for b in (l.phone or "").encode()]
    print(f"  #{l.id} {l.name} state={l.state} phone_bytes={phone_bytes}")

msgs = s.execute(select(Message).order_by(Message.id.desc()).limit(5)).scalars().all()
print("Recent messages:")
for m in msgs:
    body_preview = (m.body or "")[:80]
    print(f"  #{m.id} lead={m.lead_id} dir={m.direction} body={body_preview}")
