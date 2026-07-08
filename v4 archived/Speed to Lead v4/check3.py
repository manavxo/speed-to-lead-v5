
from app.db import init_db, get_session_factory
from app.models import Lead, Message
from sqlalchemy import select, desc
init_db()
s = get_session_factory()()
msgs = s.execute(select(Message).order_by(desc(Message.id)).limit(4)).scalars().all()
print("Latest 4 messages:")
for m in msgs:
    body = (m.body or "")[:150]
    sid = (m.provider_sid or "")[:30]
    print(f"  #{m.id} lead={m.lead_id} dir={m.direction} sid={sid} body={body}")
