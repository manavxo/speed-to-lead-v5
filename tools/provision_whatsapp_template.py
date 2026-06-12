"""Auto-create WhatsApp content templates via Twilio Content API.

Usage:
    python tools/provision_whatsapp_template.py dealers/<slug>.yaml

What it does:
1. Reads the dealer YAML
2. Creates a WhatsApp content template via Twilio Content API
3. Submits for WhatsApp approval (UTILITY category)
4. Updates all reps' notify_template_sid in the YAML
5. Prints the template SID and approval status

Requires: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN in env or .env

Cost: FREE (template creation is free; approval is free; only message sends cost).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

import requests
import yaml


def load_env():
    """Load .env file if it exists."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


def get_twilio_creds():
    """Get Twilio credentials from env."""
    sid = os.environ.get("TWILIO_ACCOUNT_SID")
    token = os.environ.get("TWILIO_AUTH_TOKEN")
    if not sid or not token:
        print("ERROR: TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN must be set.")
        print("Set them in .env or as environment variables.")
        sys.exit(1)
    return sid, token


def create_content_template(sid, token, friendly_name, body_template):
    """Create a WhatsApp content template via Twilio Content API.
    
    Returns (content_sid, error) tuple.
    """
    url = "https://content.twilio.com/v1/Content"
    
    payload = {
        "friendly_name": friendly_name,
        "language": "en",
        "types": {
            "twilio/text": {
                "body": body_template
            }
        },
        "variables": {
            "1": "Customer Name"
        },
    }
    
    resp = requests.post(url, json=payload, auth=(sid, token))
    
    if resp.status_code == 201:
        data = resp.json()
        return data["sid"], None
    elif resp.status_code == 409:
        # Template already exists — try to find it
        existing = find_existing_template(sid, token, friendly_name)
        if existing:
            return existing, None
        return None, f"Conflict (409) but could not find existing template: {resp.text}"
    else:
        return None, f"HTTP {resp.status_code}: {resp.text}"


def find_existing_template(sid, token, friendly_name):
    """Find an existing template by name."""
    url = "https://content.twilio.com/v1/Content"
    resp = requests.get(url, auth=(sid, token))
    
    if resp.status_code == 200:
        data = resp.json()
        for template in data.get("contents", []):
            if template.get("friendly_name") == friendly_name:
                return template["sid"]
    return None


def submit_for_approval(sid, token, content_sid, name, category="UTILITY"):
    """Submit a content template for WhatsApp approval.
    
    Returns (status, error) tuple.
    """
    url = f"https://content.twilio.com/v1/Content/{content_sid}/ApprovalRequests/whatsapp"
    
    payload = {
        "name": name,
        "category": category,
    }
    
    resp = requests.post(url, json=payload, auth=(sid, token))
    
    if resp.status_code in (200, 201):
        data = resp.json()
        return data.get("status", "submitted"), None
    else:
        return None, f"HTTP {resp.status_code}: {resp.text}"


def check_approval_status(sid, token, content_sid):
    """Check if a template is approved for WhatsApp.
    
    Returns (status, error) tuple.
    """
    url = f"https://content.twilio.com/v1/Content/{content_sid}"
    resp = requests.get(url, auth=(sid, token))
    
    if resp.status_code == 200:
        data = resp.json()
        return data.get("status", "unknown"), None
    else:
        return None, f"HTTP {resp.status_code}: {resp.text}"


def update_yaml_template_sid(yaml_path, content_sid):
    """Update all notify_template_sid values in the YAML file.
    
    Returns number of replacements made.
    """
    content = yaml_path.read_text(encoding="utf-8")
    
    # Replace HX_replace_with_real_sid and any existing HX... SIDs
    new_content = re.sub(
        r'notify_template_sid:\s*["\']?HX[a-zA-Z0-9_]*["\']?',
        f'notify_template_sid: "{content_sid}"',
        content
    )
    
    # Count replacements
    count = len(re.findall(
        r'notify_template_sid:\s*["\']?' + re.escape(content_sid) + r'["\']?',
        new_content
    ))
    
    yaml_path.write_text(new_content, encoding="utf-8")
    return count


def main():
    parser = argparse.ArgumentParser(description="Provision WhatsApp content template for a dealer")
    parser.add_argument("yaml_path", help="Path to dealer YAML file (e.g., dealers/sunrise-auto.yaml)")
    parser.add_argument("--name", default="Speed to Lead - New Lead Alert", help="Template friendly name")
    parser.add_argument("--body", default="New lead: {{1}}. Reply 1 to claim, 2 to pass.", help="Template body with {{1}} for customer name")
    parser.add_argument("--check-only", action="store_true", help="Only check approval status, don't create")
    parser.add_argument("--approve", action="store_true", help="Submit for WhatsApp approval after creation")
    parser.add_argument("--update-yaml", action="store_true", help="Update dealer YAML with template SID")
    
    args = parser.parse_args()
    load_env()
    
    yaml_path = Path(args.yaml_path)
    if not yaml_path.exists():
        print(f"ERROR: {yaml_path} not found.")
        sys.exit(1)
    
    sid, token = get_twilio_creds()
    
    if args.check_only:
        # Just check status of existing template
        content_sid = input("Enter content SID (HX...): ").strip()
        if not content_sid.startswith("HX"):
            print("ERROR: Invalid content SID. Must start with HX.")
            sys.exit(1)
        
        status, err = check_approval_status(sid, token, content_sid)
        if err:
            print(f"ERROR: {err}")
            sys.exit(1)
        print(f"Template {content_sid} status: {status}")
        return
    
    # Create template
    print(f"Creating template: {args.name}")
    print(f"Body: {args.body}")
    
    content_sid, err = create_content_template(sid, token, args.name, args.body)
    if err:
        print(f"ERROR: {err}")
        sys.exit(1)
    
    print(f"Template created/found: {content_sid}")
    
    # Submit for approval if requested
    if args.approve:
        print("Submitting for WhatsApp approval...")
        approval_status, err = submit_for_approval(sid, token, content_sid, 
                                                     args.name.lower().replace(" ", "_").replace("-", "_"))
        if err:
            print(f"WARNING: Approval submission failed: {err}")
            print("You can manually submit via Twilio console.")
        else:
            print(f"Approval status: {approval_status}")
    
    # Update YAML if requested
    if args.update_yaml:
        count = update_yaml_template_sid(yaml_path, content_sid)
        print(f"Updated {count} reps in {yaml_path}")
    
    print(f"\nDone. Template SID: {content_sid}")
    print("Use this SID in your dealer YAML's notify_template_sid field.")
    
    if not args.approve:
        print("\nTo submit for WhatsApp approval, run with --approve flag.")
        print("Approval usually takes 1-24 hours.")


if __name__ == "__main__":
    main()
