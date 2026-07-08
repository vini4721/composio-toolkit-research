"""
verify.py
---------
The verification loop. Accuracy is the thing the brief cares about most, so this
runs AFTER research_agent.py and does three things:

1. SECOND PASS (automated): re-check every low/medium-confidence row with an
   independent, narrower prompt that must OPEN the primary docs page and confirm
   two things the first pass most often got wrong: (a) the auth method and
   (b) whether an MCP server exists. Disagreements are recorded and the row is
   updated, keeping a `first_pass` snapshot so the change is auditable.

2. MCP SWEEP: because the first pass systematically UNDER-counts MCP servers, we
   force a dedicated "<app> MCP server" search for every row currently marked
   mcp="no", and upgrade if a credible server is found. (In our run this alone
   corrected Pylon and Reducto.)

3. HUMAN SAMPLE SCORING: load agent answers for a hand-labelled sample
   (human_labels.json), diff field-by-field, and print first-pass vs post-loop
   accuracy. This is the number reported on the deliverable.

Run:
    python verify.py                 # full loop over results.json
    python verify.py --score-only    # just recompute accuracy vs human_labels.json
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
import anthropic

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
MODEL = "claude-sonnet-4-6"
FIELDS = ["auth", "self_serve", "api_surface", "mcp", "verdict"]

RECHECK = """Re-verify ONE claim about {name} ({website}) by opening official docs.
Current agent answer:
  auth: {auth}
  self_serve: {self_serve}
  mcp: {mcp}
  verdict: {verdict}
Open the primary docs and CONFIRM or CORRECT auth, self_serve and mcp. You MUST run a
search for "{name} MCP server" before answering mcp. Return ONLY JSON:
{{"auth": "...", "self_serve": "...", "mcp": "...", "verdict": "...",
  "evidence": "<docs url>", "confidence": "high|medium|low", "changed": true|false}}"""


def recheck(client, row, tools, tool_runner, max_turns=5):
    msg = [{"role": "user", "content": RECHECK.format(**{k: row.get(k, "") for k in
            ["name", "website", "auth", "self_serve", "mcp", "verdict"]})}]
    for _ in range(max_turns):
        resp = client.messages.create(model=MODEL, max_tokens=800, tools=tools, messages=msg)
        msg.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason == "tool_use":
            outs = [{"type": "tool_result", "tool_use_id": b.id,
                     "content": str(tool_runner(b.name, b.input))[:6000]}
                    for b in resp.content if getattr(b, "type", None) == "tool_use"]
            msg.append({"role": "user", "content": outs})
            continue
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            msg.append({"role": "user", "content": "Return ONLY the JSON."})
    return None


def score_against_humans():
    """Diff agent answers vs a hand-labelled sample; print accuracy before/after."""
    labels_path = DATA / "human_labels.json"
    results_path = DATA / "results.json"
    if not labels_path.exists():
        print("No human_labels.json — skipping scoring.", file=sys.stderr)
        return
    labels = {l["id"]: l for l in json.loads(labels_path.read_text())}
    rows = {r["id"]: r for r in json.loads(results_path.read_text())}

    fp_right = fp_tot = pl_right = pl_tot = 0
    print(f"\n{'app':12} {'field':12} {'first-pass':22} {'verified':22} ok?")
    for aid, truth in labels.items():
        row = rows.get(aid, {})
        fp = row.get("first_pass") or {}
        for f in FIELDS:
            if f not in truth:
                continue
            gold = truth[f]
            post = str(row.get(f, "")).split("(")[0].strip().lower()
            pre = str(fp.get(f, row.get(f, ""))).split("(")[0].strip().lower()
            gold_n = str(gold).split("(")[0].strip().lower()
            fp_tot += 1; pl_tot += 1
            fp_ok = gold_n in pre or pre in gold_n
            pl_ok = gold_n in post or post in gold_n
            fp_right += fp_ok; pl_right += pl_ok
            flag = "" if pl_ok else "  <-- still off"
            if not fp_ok or not pl_ok:
                print(f"{truth['name'][:11]:12} {f:12} {pre[:20]:22} {post[:20]:22} {flag}")
    print(f"\nFirst-pass accuracy : {fp_right}/{fp_tot} = {round(100*fp_right/fp_tot)}%")
    print(f"Post-loop accuracy  : {pl_right}/{pl_tot} = {round(100*pl_right/pl_tot)}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--score-only", action="store_true")
    ap.add_argument("--local", action="store_true")
    args = ap.parse_args()

    if args.score_only:
        score_against_humans()
        return

    import research_agent as ra
    client = anthropic.Anthropic()
    if args.local:
        tools, tool_runner = ra.local_tools()
    else:
        composio, user_id, tools = ra.composio_tools()
        tool_runner = lambda n, i: composio.tools.execute(n, arguments=i, user_id=user_id)

    rows = json.loads((DATA / "results.json").read_text())
    changes = 0
    for row in rows:
        needs = row.get("confidence") in ("low", "medium") or row.get("mcp") == "no"
        if not needs:
            continue
        print(f"re-checking {row['name']} ...", file=sys.stderr)
        v = recheck(client, row, tools, tool_runner)
        if not v:
            continue
        snap = {f: row.get(f) for f in FIELDS if str(v.get(f, "")).lower() not in ("", str(row.get(f, "")).lower())}
        if snap:
            row["first_pass"] = {**(row.get("first_pass") or {}), **snap}
            for f in FIELDS:
                if v.get(f):
                    row[f] = v[f]
            row["verified"] = True
            row["evidence"] = v.get("evidence", row["evidence"])
            row["confidence"] = v.get("confidence", row["confidence"])
            changes += 1

    (DATA / "results.json").write_text(json.dumps(rows, indent=2))
    print(f"\nVerification loop updated {changes} rows.", file=sys.stderr)
    score_against_humans()


if __name__ == "__main__":
    main()
