import os

old = bytes([0x2b, 0x31, 0x32, 0x30, 0x39, 0x37, 0x39, 0x37, 0x32, 0x36, 0x39, 0x34])
active = bytes([0x2b, 0x31, 0x37, 0x37, 0x38, 0x37, 0x36, 0x32, 0x33, 0x31, 0x32, 0x32])
skip = {'uv.lock', '.venv', 'lottie', 'node_modules', '.git'}

old_found = []
active_found = []

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in skip]
    for f in files:
        if f.endswith(('.py', '.md', '.yaml', '.yml', '.env', '.html', '.json', '.toml', '.cfg', '.txt')):
            path = os.path.join(root, f)
            try:
                data = open(path, 'rb').read()
                if old in data:
                    old_found.append(path)
                if active in data:
                    active_found.append(path)
            except:
                pass

print('Files with OLD 209 number:', old_found if old_found else 'NONE')
print('Files with ACTIVE 3122 number:')
for p in active_found:
    print(f'  {p}')
