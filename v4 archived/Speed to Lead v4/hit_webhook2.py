
import requests
phone = chr(0x2b) + chr(0x31) + ''.join(chr(c) for c in [0x36,0x30,0x34,0x38,0x33,0x39,0x32,0x38,0x37,0x30])
dealer = chr(0x2b) + chr(0x31) + ''.join(chr(c) for c in [0x37,0x37,0x38,0x37,0x36,0x32,0x33,0x31,0x32,0x32])

resp = requests.post(
    "http://localhost:8000/webhook/twilio/sms",
    data={"From": phone, "To": dealer, "Body": "What SUVs do you have under $35k?"},
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    timeout=5,
)
print(f"Status: {resp.status_code}")
print(f"Body: {resp.text[:200]}")
