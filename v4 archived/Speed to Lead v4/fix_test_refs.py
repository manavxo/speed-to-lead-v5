
content = open("tests/test_pipeline_e2e.py").read()
old = "+120****2694"
new = "+17787623122"
count = content.count(old)
content = content.replace(old, new)
open("tests/test_pipeline_e2e.py", "w").write(content)
print(f"Replaced {count} occurrences in test_pipeline_e2e.py")
