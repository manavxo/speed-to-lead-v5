
import requests
import time

phone = "+16048392870"
dealer_num = "+17787623122"

print(f"Sending inbound SMS from {phone} to {dealer_num}...")

# Hit the Twilio SMS webhook
resp = requests.post(
    "http://localhost:8000/webhook/twilio/sms",
    data={
        "From": phone,
        "To": dealer_num,
        "Body": "Hi, I'm interested in buying a car. What do you have available?",
    },
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    timeout=30,
)
print(f"Webhook response: {resp.status_code} {resp.text[:200]}")
