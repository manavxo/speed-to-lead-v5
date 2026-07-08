
from app.db import init_db, get_session_factory
from app.models import Lead, Message
from sqlalchemy import select, desc

init_db()
s = get_session_factory()()

msgs = s.execute(select(Message).order_by(desc(Message.id)).limit(6)).scalars().all()
print("Latest 6 messages:")
for m in msgs:
    body = (m.body or "")[:120]
    sid = m.provider_sid or ""
    print(f"  #{m.id} lead={m.lead_id} dir={m.direction} sid={sid[:25]} body={body}")
