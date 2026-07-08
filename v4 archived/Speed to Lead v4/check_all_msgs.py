from app.db import init_db, get_session_factory
from app.models import Message
from sqlalchemy import select, desc, and_

init_db()
s = get_session_factory()()

# Get ALL messages for lead 36 and 37, ordered by ID
msgs = s.execute(
    select(Message).where(Message.lead_id.in_([36, 37])).order_by(Message.id.desc())
).scalars().all()

print(f"All messages for leads 36/37 ({len(msgs)} total):")
for m in msgs:
    body = (m.body or "")[:120]
    sid = (m.provider_sid or "")[:35]
    is_dryrun = "DRYRUN" in (m.provider_sid or "")
    flag = " [DRYRUN]" if is_dryrun else " [REAL]"
    print(f"  #{m.id} lead={m.lead_id} dir={m.direction}{flag} sid={sid}")
    print(f"    body={body}")
