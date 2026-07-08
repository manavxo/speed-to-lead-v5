
import yaml, json
from app.db import init_db, get_session_factory
from app.models import Dealer
from sqlalchemy import select

# Build correct phone numbers from chr codes
def build_phone(digits_after_1):
    """Build +1XXXXXXXXXX from a list of digit character codes."""
    return chr(0x2b) + chr(0x31) + ''.join(chr(c) for c in digits_after_1)

# 778-762-3122
sms_phone = build_phone([0x37,0x37,0x38,0x37,0x36,0x32,0x33,0x31,0x32,0x32])
# 778-762-4366
ravi_phone = build_phone([0x37,0x37,0x38,0x37,0x36,0x32,0x34,0x33,0x36,0x36])
# 604-839-8418
ramesh_phone = build_phone([0x36,0x30,0x34,0x38,0x33,0x39,0x38,0x34,0x31,0x38])
# 604-839-2870
manager_phone = build_phone([0x36,0x30,0x34,0x38,0x33,0x39,0x32,0x38,0x37,0x30])

print(f"SMS: {repr(sms_phone)} bytes={[hex(ord(c)) for c in sms_phone]}")
print(f"Ravi: {repr(ravi_phone)}")
print(f"Ramesh: {repr(ramesh_phone)}")
print(f"Manager: {repr(manager_phone)}")

init_db()
sf = get_session_factory()
s = sf()
dealer = s.execute(select(Dealer).where(Dealer.slug == 'premier-auto')).scalars().first()

config = dealer.config or {}

# Update channels
if 'channels' not in config:
    config['channels'] = {}
config['channels']['sms_number'] = sms_phone

# Update dealer main_phone
if 'dealer' not in config:
    config['dealer'] = {}
config['dealer']['main_phone'] = sms_phone

# Update sales_team
config['sales_team'] = [
    {'name': 'Ravi', 'phone': ravi_phone, 'active': True},
    {'name': 'Ramesh', 'phone': ramesh_phone, 'active': True},
]

# Update routing
if 'routing' not in config:
    config['routing'] = {}
config['routing']['manager_phone'] = manager_phone

dealer.config = config
s.commit()

# Verify
d2 = s.execute(select(Dealer).where(Dealer.slug == 'premier-auto')).scalars().first()
sms2 = d2.config['channels']['sms_number']
print(f"\nDB verify: {repr(sms2)} bytes={[hex(ord(c)) for c in sms2]}")
print(f"Match API: {sms2 == sms_phone}")
s.close()
