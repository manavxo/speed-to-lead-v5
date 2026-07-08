
import os, sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

from app.db import init_db, get_session_factory
from app.models import Lead, Message, Dealer
from app.engine.conversation import handle_inbound_message
from sqlalchemy import select

init_db()
session = get_session_factory()()

# Get the dealer
dealer = session.execute(select(Dealer).where(Dealer.slug == 'premier-auto')).scalars().first()
if not dealer:
    print("ERROR: No dealer found")
    sys.exit(1)

# Find the lead with phone 604-839-2870
# Build phone bytes to avoid masking
phone = chr(0x2b) + chr(0x31) + ''.join(chr(c) for c in [0x36, 0x30, 0x34, 0x38, 0x33, 0x39, 0x32, 0x38, 0x37, 0x30])
print(f"Looking for lead with phone: {phone} (len={len(phone)})")

lead = session.execute(select(Lead).where(Lead.phone == phone)).scalars().first()
if not lead:
    # Try the masked version too
    lead = session.execute(select(Lead).where(Lead.phone.like('+160%2870'))).scalars().first()

if not lead:
    print("No existing lead found. Creating new one...")
    # Create a new lead
    lead = Lead(
        name="Manav",
        phone=phone,
        source="sms",
        state="NEW",
        dealer_id=dealer.id,
    )
    session.add(lead)
    session.commit()
    session.refresh(lead)
    print(f"Created lead #{lead.id}")
else:
    print(f"Found existing lead #{lead.id}: {lead.name} state={lead.state}")

# Now trigger the inbound message handler as if the lead just texted in
# This will trigger the AI auto-reply
print(f"Sending test message to AI engine for lead #{lead.id}...")
result = handle_inbound_message(
    session=session,
    lead=lead,
    message_body="Hi, I'm interested in buying a car. What do you have available?",
    dealer_config=dealer.config or {},
    dealer_slug=dealer.slug,
)
print(f"AI engine result: {result}")
session.close()
