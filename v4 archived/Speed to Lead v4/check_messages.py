
from app.db import init_db, get_session_factory
from app.models import Lead, Message
from sqlalchemy import select, desc

init_db()
s = get_session_factory()()

# Check latest messages
msgs = s.execute(select(Message).order_by(desc(Message.id)).limit(8)).scalars().all()
print("Latest 8 messages:")
for m in msgs:
    body = (m.body or "")[:100]
    print(f"  #{m.id} lead={m.lead_id} dir={m.direction} via={m.channel} body={body}")

# Check lead state for phone 604-839-2870
phone = chr(0x2b) + chr(0x31) + ''.join(chr(c) for c in [0x36,0x30,0x34,0x38,0x33,0x39,0x32,0x38,0x37,0x30])
lead = s.execute(select(Lead).where(Lead.phone == phone)).scalars().first()
if lead:
    print(f"Lead #{lead.id}: state={lead.state} name={lead.name}")
else:
    # try masked
    lead = s.execute(select(Lead).where(Lead.phone.like('+160%2870'))).scalars().first()
    if lead:
        print(f"Lead #{lead.id} (masked): state={lead.state} name={lead.name} phone_repr={repr(lead.phone)}")
    else:
        print("No lead found for 604-839-2870")
