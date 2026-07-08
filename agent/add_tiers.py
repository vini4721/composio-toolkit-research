"""
add_tiers.py
------------
Adds the build-priority `tier` field to each app in data/results.json.
Run this after regenerating results.json from apps_data.py and before build_site.py.

    python3 agent/apps_data.py > data/results.json
    python3 agent/add_tiers.py
    python3 agent/build_site.py

Tier logic (buildability x access):
    easy + self-serve/partial      -> Build now
    buildable + self-serve/partial -> Build next
    gated verdict OR gated access  -> Needs BD / outreach
    everything else (needs-human)  -> Park / clarify
"""
import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
apps = json.loads((DATA / "results.json").read_text())

def tier(a):
    v, s = a.get("verdict"), a.get("self_serve")
    if v == "easy" and s in ("self-serve", "partial"):
        return "Build now"
    if v == "buildable" and s in ("self-serve", "partial"):
        return "Build next"
    if v == "gated" or s == "gated":
        return "Needs BD / outreach"
    return "Park / clarify"

for a in apps:
    a["tier"] = tier(a)

(DATA / "results.json").write_text(json.dumps(apps, indent=2))
from collections import Counter
c = Counter(a["tier"] for a in apps)
print("tiers added:", dict(c))