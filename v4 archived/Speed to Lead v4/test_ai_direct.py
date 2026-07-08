
import os, sys, traceback
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

from app.db import init_db, get_session_factory
from app.models import Lead
from app.engine.conversation import handle_turn
from sqlalchemy import select

init_db()
s = get_session_factory()()

# Use lead #36 (has real phone digits)
lead = s.get(Lead, 36)
print(f"Lead #{lead.id}: {lead.name} state={lead.state} phone={repr(lead.phone)}")

# Get dealer config
from app.models import Dealer
dealer = s.execute(select(Dealer).where(Dealer.slug == 'premier-auto')).scalars().first()
print(f"Dealer: {dealer.name}")

try:
    result = handle_turn(
        s, lead, "Hi, I'm looking for a used SUV under $35k. What do you have?",
        dealer_config=dealer.config or {},
    )
    print(f"Result: {result}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    traceback.print_exc()
