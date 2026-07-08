
# Old 209 number bytes: +1 209 797 2694
old_bytes = bytes([0x2b, 0x31, 0x32, 0x30, 0x39, 0x37, 0x39, 0x37, 0x32, 0x36, 0x39, 0x34])
# New 3122 number bytes: +1 778 762 3122
new_bytes = bytes([0x2b, 0x31, 0x37, 0x37, 0x38, 0x37, 0x36, 0x32, 0x33, 0x31, 0x32, 0x32])

content = open("tests/test_pipeline_e2e.py", "rb").read()
count = content.count(old_bytes)
content = content.replace(old_bytes, new_bytes)
open("tests/test_pipeline_e2e.py", "wb").write(content)
print(f"Replaced {count} occurrences of 209 number with 3122 number in test_pipeline_e2e.py")

# Verify
verify = open("tests/test_pipeline_e2e.py", "rb").read()
remaining = verify.count(old_bytes)
print(f"Remaining 209 references: {remaining}")
