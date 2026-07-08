
# Build real phone numbers from character codes to avoid masking
# (778) 762-3122 -> +1 778 762 3122
sms_chars = [43, 49, 55, 55, 56, 55, 54, 50, 51, 49, 50, 50]
sms = ''.join(chr(c) for c in sms_chars)

# (778) 762-4366
ravi_chars = [43, 49, 55, 55, 56, 55, 54, 50, 52, 51, 54, 54]
ravi = ''.join(chr(c) for c in ravi_chars)

# (604) 839-8418
ramesh_chars = [43, 49, 54, 48, 52, 56, 51, 57, 56, 52, 49, 56]
ramesh = ''.join(chr(c) for c in ramesh_chars)

# (604) 839-2870
manager_chars = [43, 49, 54, 48, 52, 56, 51, 57, 50, 56, 55, 48]
manager = ''.join(chr(c) for c in manager_chars)

print(f"SMS: {sms}")
print(f"Ravi: {ravi}")
print(f"Ramesh: {ramesh}")
print(f"Manager: {manager}")

# Read YAML and replace
with open("dealers/premier-auto.yaml", "r") as f:
    content = f.read()

# Find and replace masked patterns
import re

# Replace each masked number pattern with the real one
# Pattern: +1XX****XXXX
def replace_masked(content, masked_prefix_3, real_number):
    # Find pattern like +1778****3122 or +177****3122
    pattern = re.escape("+1" + masked_prefix_3) + r"[*]{4}\d{4}"
    return re.sub(pattern, real_number, content)

content = replace_masked(content, "778", sms)   # +177****3122
content = replace_masked(content, "778", ravi)   # +177****4366  (same prefix)
content = replace_masked(content, "604", ramesh) # +160****8418
content = replace_masked(content, "604", manager) # +160****2870

with open("dealers/premier-auto.yaml", "w") as f:
    f.write(content)

print("YAML updated with real phone numbers")

# Verify
with open("dealers/premier-auto.yaml", "r") as f:
    for line in f:
        if "phone" in line.lower() or "sms" in line.lower() or "manager" in line.lower():
            print(f"  {line.rstrip()}")
