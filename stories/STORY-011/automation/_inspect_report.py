import json, re

path = r"C:\Users\james\Downloads\Twilight Caverns_mastered_report.json"
s = open(path, encoding="utf-8").read()

keys = sorted(set(re.findall(r'"[a-zA-Z_]*actions?"', s)))
print("action keys:", keys)

r = json.loads(s)

def find(o, needle, p=""):
    hits = []
    if isinstance(o, dict):
        for k, v in o.items():
            if needle in k:
                hits.append((p + "/" + k, v))
            hits += find(v, needle, p + "/" + k)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            hits += find(v, needle, p + f"[{i}]")
    return hits

for needle in ("transient", "restoration"):
    for p, v in find(r, needle):
        preview = json.dumps(v)[:600]
        print(f"{p} -> {preview}")
