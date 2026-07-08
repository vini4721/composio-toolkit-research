"""
research_agent_gemini.py
------------------------
Research agent — Gemini reasoner (free tier) + Composio tools via the direct
REST API. This version calls Composio the same way a plain `curl` does
(POST https://backend.composio.dev/api/v3/tools/execute/<slug> with x-api-key),
which avoids the SDK's newer Tool Router "session" feature that isn't enabled on
free-tier accounts.

It degrades gracefully: if a Composio search call fails for any reason, the
agent falls back to reading the app's docs URL directly, so a run always
produces data instead of crashing.

Setup
-----
    pip install -r requirements.txt
    export COMPOSIO_API_KEY=...       # your valid key (curl to /api/v3/toolkits returns 200)
    export GOOGLE_API_KEY=...         # free key from https://aistudio.google.com/apikey
    export COMPOSIO_USER_ID=default

    python3 agent/research_agent_gemini.py --limit 5      # smoke test
    python3 agent/research_agent_gemini.py                # full 100

Output: ../data/results.json  (then: python3 agent/verify.py --score-only)
"""
from __future__ import annotations
import argparse, csv, json, os, sys, time
from pathlib import Path

import requests
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
MODEL = "gemini-2.5-flash"                       # free-tier eligible
COMPOSIO_BASE = "https://backend.composio.dev/api/v3"

SYSTEM = """You are a developer-relations researcher for Composio, which turns apps into
tools AI agents can call. For ONE app, use the tools to find the truth in official docs,
then return ONLY a JSON object with these keys:
category, one_liner, auth, self_serve, serve_note, api_surface, mcp, verdict, blocker,
evidence, confidence.
- self_serve: "self-serve" | "partial" | "gated" | "unknown".
- mcp: "yes" (official) | "community" | "no" | "unknown". ALWAYS search "<app> MCP server"
  before answering mcp — it is easy to under-count.
- verdict: "easy" | "buildable" | "gated" | "needs-human".
- confidence: "high" only if official docs were explicit; else "medium"/"low".
A gated/undocumented app is a valid finding, not a failure. Return strict JSON only."""


# --------------------------------------------------------------------------- #
# Composio via direct REST (the path that works with a plain API key)
# --------------------------------------------------------------------------- #
class Composio:
    def __init__(self, api_key, user_id):
        self.h = {"x-api-key": api_key, "Content-Type": "application/json"}
        self.user_id = user_id
        self.search_slug = self._discover_search_slug()

    def _discover_search_slug(self):
        try:
            r = requests.get(f"{COMPOSIO_BASE}/tools",
                             params={"toolkit_slug": "COMPOSIO_SEARCH", "limit": 50},
                             headers=self.h, timeout=30)
            r.raise_for_status()
            items = r.json().get("items", r.json() if isinstance(r.json(), list) else [])
            slugs = [it.get("slug", "") for it in items]
            # prefer a general web-search tool
            for want in ("COMPOSIO_SEARCH_SEARCH", "COMPOSIO_SEARCH_TAVILY_SEARCH",
                         "COMPOSIO_SEARCH_DUCK_DUCK_GO_SEARCH"):
                if want in slugs:
                    return want
            for s in slugs:
                if "SEARCH" in s and "NEWS" not in s and "IMAGE" not in s:
                    return s
            return slugs[0] if slugs else None
        except Exception as e:
            print(f"[composio] could not list search tools ({e}); will use direct fetch",
                  file=sys.stderr)
            return None

    def search(self, query):
        """Run Composio search; return text. Returns None on any failure."""
        if not self.search_slug:
            return None
        url = f"{COMPOSIO_BASE}/tools/execute/{self.search_slug}"
        for body in ({"user_id": self.user_id, "arguments": {"query": query}},
                     {"user_id": self.user_id, "text": query}):
            try:
                r = requests.post(url, headers=self.h, json=body, timeout=45)
                if r.status_code == 200:
                    data = r.json()
                    return json.dumps(data.get("data", data))[:6000]
            except Exception:
                continue
        return None


def fetch_url(url):
    try:
        r = requests.get(url if url.startswith("http") else "https://" + url,
                         timeout=25, headers={"User-Agent": "composio-research/1.0"})
        return r.text[:6000]
    except Exception as e:
        return f"ERROR fetching {url}: {e}"


# --------------------------------------------------------------------------- #
# Gemini tool-calling loop
# --------------------------------------------------------------------------- #
def gemini_tools():
    return [types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="search_web",
            description="Search the web for docs about an app's API, auth, or MCP server.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={
                "query": types.Schema(type=types.Type.STRING)}, required=["query"])),
        types.FunctionDeclaration(
            name="read_url",
            description="Fetch the readable text of a documentation URL.",
            parameters=types.Schema(type=types.Type.OBJECT, properties={
                "url": types.Schema(type=types.Type.STRING)}, required=["url"])),
    ])]


def send(chat, message, tries=5):
    for i in range(tries):
        try:
            return chat.send_message(message)
        except Exception as e:
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                w = 2 ** i; print(f"   rate-limited, waiting {w}s", file=sys.stderr); time.sleep(w); continue
            raise
    raise RuntimeError("gave up after repeated rate limits")


def research_one(client, composio, app, max_turns=6):
    cfg = types.GenerateContentConfig(tools=gemini_tools(), system_instruction=SYSTEM)
    chat = client.chats.create(model=MODEL, config=cfg)
    resp = send(chat, f"App #{app['id']}: {app['name']}\nDocs hint: {app['website']}\n"
                       f"Category (given): {app['category']}\nResearch it and return the JSON object.")
    for _ in range(max_turns):
        calls = getattr(resp, "function_calls", None)
        if not calls:
            break
        parts = []
        for fc in calls:
            args = dict(fc.args or {})
            if fc.name == "search_web":
                out = composio.search(args.get("query", "")) or fetch_url(app["website"])
            elif fc.name == "read_url":
                out = fetch_url(args.get("url", app["website"]))
            else:
                out = "unknown tool"
            parts.append(types.Part.from_function_response(name=fc.name, response={"result": str(out)[:6000]}))
        resp = send(chat, parts)

    text = (resp.text or "").strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        d = json.loads(text); d.update(id=app["id"], name=app["name"], website=app["website"]); return d
    except json.JSONDecodeError:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    for v in ("COMPOSIO_API_KEY", "GOOGLE_API_KEY"):
        if not os.environ.get(v):
            sys.exit(f"Set {v}")

    user_id = os.environ.get("COMPOSIO_USER_ID", "default")
    composio = Composio(os.environ["COMPOSIO_API_KEY"], user_id)
    print(f"[tools] Composio search slug: {composio.search_slug or 'NONE -> direct fetch fallback'}",
          file=sys.stderr)
    client = genai.Client()   # reads GOOGLE_API_KEY

    with open(ROOT / "apps.csv") as f:
        apps = list(csv.DictReader(f))
    if args.limit:
        apps = apps[: args.limit]

    results = []
    for i, app in enumerate(apps, 1):
        app["id"] = int(app["id"])
        print(f"[{i}/{len(apps)}] {app['name']} ...", file=sys.stderr)
        try:
            row = research_one(client, composio, app)
        except Exception as e:
            print(f"   error: {e}", file=sys.stderr); row = None
        if row is None:
            row = {**app, "verdict": "needs-human", "confidence": "low",
                   "blocker": "agent failed to produce structured output"}
        results.append(row)
        time.sleep(12)

    DATA.mkdir(exist_ok=True)
    (DATA / "results.json").write_text(json.dumps(results, indent=2))
    print(f"\nWrote {len(results)} rows -> {DATA/'results.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()