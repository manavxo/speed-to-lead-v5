
from app.db import init_db, get_session_factory
from app.models import Lead
from sqlalchemy import select

init_db()
s = get_session_factory()()

leads = s.execute(select(Lead).where(Lead.name == 'Manav').order_by(Lead.id.desc())).scalars().all()
for l in leads:
    phone_raw = l.phone
    phone_bytes = [hex(b) for b in phone_raw.encode()]
    has_asterisk = '*' in phone_raw
    print(f"Lead #{l.id}: phone={repr(phone_raw)} bytes={phone_bytes} has_asterisk={has_asterisk} state={l.state}")
