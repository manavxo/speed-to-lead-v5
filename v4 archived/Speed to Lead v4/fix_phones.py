
import re

with open("dealers/premier-auto.yaml", "r") as f:
    content = f.read()

# Replace all masked phone number patterns
# Pattern: +1XX****XXXX where X are digits
# We know the real numbers:
# SMS number: (778) 762-3122
# Ravi: (778) 762-4366  
# Ramesh: (604) 839-8418
# Manager: (604) 839-2870

replacements = [
    ("+177****3122", "+17787623122"),
    ("+177****4366", "+17787624366"),
    ("+160****8418", "+16048398418"),
    ("+160****2870", "+16048392870"),
]

for old, new in replacements:
    content = content.replace(old, new)

with open("dealers/premier-auto.yaml", "w") as f:
    f.write(content)

print("Fixed phone numbers in YAML")
