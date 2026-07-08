"""
research_agent.py
-----------------
Agent that researches each app and extracts the AppResearch schema.

Design (why it's built this way)
--------------------------------
1. TOOLS come from Composio. The agent is given a web-search tool and a
   scrape/fetch tool from Composio's toolkits (COMPOSIO_SEARCH + FIRECRAWL by
   default). This is the "use Composio's own SDK/MCP" part of the brief: the
   research agent that decides which apps become Composio toolkits is *itself*
   built on Composio tools.
2. The LLM (Claude) is the reasoner. For each app it: searches for
   "<app> API authentication", opens the primary docs page, and fills the
   schema. It must return strict JSON and a self-reported confidence.
3. A LOCAL FALLBACK (--local) swaps Composio tools for a plain requests-based
   fetch + DuckDuckGo-style search so the pipeline runs with only an LLM key.
   Same prompts, same schema — just a different tool layer.

Run
---
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=...        # required
    export COMPOSIO_API_KEY=...         # required unless --local
    python research_agent.py                     # research all 100
    python research_agent.py --limit 5           # smoke test
    python research_agent.py --local             # no Composio, LLM-only tools

Output: ../data/results.json  (list[AppResearch])
Then:   python verify.py                         # run the verification loop
"""
from __future__ import annotations
import argparse, csv, json, os, sys, time
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
MODEL = "claude-sonnet-4-6"   # cheap + strong enough for structured extraction

SYSTEM = """You are a developer-relations researcher for Composio, which turns apps into
tools that AI agents can call. For ONE app, use the provided tools to find the truth
in official docs, then return ONLY a JSON object with these keys:

  category, one_liner, auth, self_serve, serve_note, api_surface, mcp, verdict,
  blocker, evidence, confidence

Rules:
- auth: the primary method(s) — OAuth2, API key, Basic, token, HMAC, or none.
- self_serve: "self-serve" (dev gets working creds free/trial), "partial" (sandbox
  self-serve but production needs approval/paid plan), "gated" (partnership/contact-
  sales/enterprise), or "unknown".
- mcp: "yes" (official MCP server), "community" (credible community MCP), "no", "unknown".
  ALWAYS run a search for "<app> MCP server" before answering this — MCP adoption is
  moving fast and is easy to under-count.
- verdict: "easy", "buildable", "gated", or "needs-human".
- evidence: the exact docs URL you relied on.
- confidence: "high" only if you opened official docs and they were explicit; "low" if
  you are guessing or could not find docs. A gated/undocumented app is a valid finding,
  NOT a failure — say so honestly instead of inventing an answer.
Return strict JSON, no prose, no markdown fences."""


# --------------------------------------------------------------------------- #
# Tool layer
# --------------------------------------------------------------------------- #
def composio_tools():
    """Load Composio's search + scrape tools for the agent.

    Uses the Composio Python SDK. Toolkits COMPOSIO_SEARCH and FIRECRAWL give the
    agent web search and page-scraping without us writing any HTTP glue.
    """
    from composio import Composio
    from composio_anthropic import AnthropicProvider

    composio = Composio(provider=AnthropicProvider())
    user_id = os.environ.get("COMPOSIO_USER_ID", "default")
    tools = composio.tools.get(
        user_id=user_id,
        toolkits=["COMPOSIO_SEARCH", "FIRECRAWL"],
    )
    return composio, user_id, tools


def local_tools():
    """LLM-only fallback: expose search + fetch as plain Anthropic tool schemas.
    Handlers use requests so the pipeline runs with just ANTHROPIC_API_KEY."""
    tools = [
        {"name": "web_search", "description": "Search the web; returns top result snippets.",
         "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
        {"name": "fetch_url", "description": "Fetch the readable text of a URL.",
         "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
    ]

    def handle(name, args):
        import requests
        if name == "fetch_url":
            try:
                r = requests.get(args["url"], timeout=20, headers={"User-Agent": "composio-research/1.0"})
                return r.text[:6000]
            except Exception as e:
                return f"ERROR fetching: {e}"
        if name == "web_search":
            try:  # DuckDuckGo HTML endpoint — no key needed
                r = requests.get("https://duckduckgo.com/html/",
                                 params={"q": args["query"]}, timeout=20,
                                 headers={"User-Agent": "Mozilla/5.0"})
                return r.text[:6000]
            except Exception as e:
                return f"ERROR searching: {e}"
        return "unknown tool"

    return tools, handle


# --------------------------------------------------------------------------- #
# Agent loop for a single app
# --------------------------------------------------------------------------- #
def research_one(client, app, tools, tool_runner, max_turns=6):
    """Run the tool-use loop for one app and return the parsed JSON dict."""
    user = (f"App #{app['id']}: {app['name']}\n"
            f"Website / docs hint: {app['website']}\n"
            f"Category (given): {app['category']}\n"
            f"Research this app and return the JSON object.")
    messages = [{"role": "user", "content": user}]

    for _ in range(max_turns):
        resp = client.messages.create(
            model=MODEL, max_tokens=1500, system=SYSTEM,
            tools=tools, messages=messages,
        )
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason == "tool_use":
            results = []
            for block in resp.content:
                if getattr(block, "type", None) == "tool_use":
                    out = tool_runner(block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": str(out)[:6000]})
            messages.append({"role": "user", "content": results})
            continue

        # final text -> parse JSON
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            data = json.loads(text)
            data.update(id=app["id"], name=app["name"], website=app["website"])
            return data
        except json.JSONDecodeError:
            messages.append({"role": "user", "content": "Return ONLY the JSON object, no prose."})
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only research first N apps")
    ap.add_argument("--local", action="store_true", help="LLM-only tools, no Composio")
    args = ap.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("Set ANTHROPIC_API_KEY")

    client = anthropic.Anthropic()

    # Tool layer -----------------------------------------------------------
    if args.local:
        tools, handle = local_tools()
        tool_runner = handle
        print("[tools] local requests fallback (no Composio)", file=sys.stderr)
    else:
        if not os.environ.get("COMPOSIO_API_KEY"):
            sys.exit("Set COMPOSIO_API_KEY (or run with --local)")
        composio, user_id, tools = composio_tools()

        def tool_runner(name, inp):
            return composio.tools.execute(name, arguments=inp, user_id=user_id)

        print("[tools] Composio COMPOSIO_SEARCH + FIRECRAWL", file=sys.stderr)

    # Input ----------------------------------------------------------------
    with open(ROOT / "apps.csv") as f:
        apps = list(csv.DictReader(f))
    if args.limit:
        apps = apps[: args.limit]

    results = []
    for i, app in enumerate(apps, 1):
        app["id"] = int(app["id"])
        print(f"[{i}/{len(apps)}] {app['name']} ...", file=sys.stderr)
        try:
            row = research_one(client, app, tools, tool_runner)
        except Exception as e:
            print(f"   error: {e}", file=sys.stderr)
            row = None
        if row is None:
            row = {**app, "verdict": "needs-human", "confidence": "low",
                   "blocker": "agent failed to produce structured output"}
        results.append(row)
        time.sleep(0.3)

    DATA.mkdir(exist_ok=True)
    (DATA / "results.json").write_text(json.dumps(results, indent=2))
    print(f"\nWrote {len(results)} rows -> {DATA/'results.json'}", file=sys.stderr)


if __name__ == "__main__":
    main()
