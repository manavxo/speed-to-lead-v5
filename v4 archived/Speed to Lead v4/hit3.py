
import requests
resp = requests.post(
    "http://localhost:8000/webhook/twilio/sms",
    data={"From": "+16048392870", "To": "+17787623122", "Body": "Hey, any good SUVs under 35k?"},
    headers={"Content-Type": "application/x-www-form-urlencoded"},
    timeout=5,
)
print(f"Status: {resp.status_code} Body: {resp.text[:100]}")
