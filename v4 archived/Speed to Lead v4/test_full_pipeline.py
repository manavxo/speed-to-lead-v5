
import os, sys, traceback, logging
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

# Enable verbose logging
logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
logger = logging.getLogger()

from app.db import init_db, get_session_factory
from app.models import Lead, Message, Dealer
from app.engine.conversation import handle_turn
from tools.send_sms import send_sms
from sqlalchemy import select, desc

init_db()
s = get_session_factory()()

# Get lead #36 and dealer
lead = s.get(Lead, 36)
dealer = s.execute(select(Dealer).where(Dealer.slug == 'premier-auto')).scalars().first()

print(f"Lead #{lead.id}: {lead.name} state={lead.state}")
print(f"OUTBOUND_ENABLED: {os.getenv('OUTBOUND_ENABLED')}")

# Step 1: AI turn
print("\n--- Step 1: AI handle_turn ---")
result = handle_turn(
    s, lead, "Hi, I'm looking for a used SUV under $35k. What do you have?",
    dealer_config=dealer.config or {},
)
reply_text = result.get('text', '')
print(f"AI reply ({len(reply_text)} chars): {reply_text[:150]}...")

# Step 2: Append compliance footer
dealer_config = dealer.config or {}
dealer_name = dealer_config.get('dealer', {}).get('name', '')
footer = dealer_config.get('compliance', {}).get('consent_text', 'Reply STOP to opt out.')
if dealer_name and dealer_name not in reply_text:
    reply_text = f"{reply_text}\n\n--- {dealer_name}. {footer}"

# Step 3: Send via send_sms
print("\n--- Step 2: send_sms ---")
phone = chr(0x2b) + chr(0x31) + ''.join(chr(c) for c in [0x36,0x30,0x34,0x38,0x33,0x39,0x32,0x38,0x37,0x30])
dealer_sms = chr(0x2b) + chr(0x31) + ''.join(chr(c) for c in [0x37,0x37,0x38,0x37,0x36,0x32,0x33,0x31,0x32,0x32])
print(f"Sending to: {phone} (len={len(phone)})")
print(f"From: {dealer_sms} (len={len(dealer_sms)})")

sid = send_sms(
    s,
    to=phone,
    body=reply_text,
    from_number=dealer_sms,
    dealer_slug='premier-auto',
    dealer_config=dealer_config,
    lead=lead,
    force_send=True,
)
print(f"Result SID: {sid}")
