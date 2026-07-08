# Composio — Toolkit Coverage Research (100 apps)

Which of 100 apps can become **agent toolkits** today, what blocks the rest, and
how do we *know* the answers are right? A research agent profiles each app for
the things Composio cares about before building a toolkit — auth method,
self-serve vs. gated access, API surface, and any existing MCP server — then a
verification loop checks the agent against live docs.

**→ Live case study:** `https://YOUR_USERNAME.github.io/composio-toolkit-research/`
*(the 2-minute read: patterns, the agent, the verified accuracy loop, and a build backlog)*

---

## The headline

- **91 / 100** apps are buildable today (57 easy, 34 buildable). The 9 that aren't
  are gated by **go-to-market, not engineering** — partner programs, OAuth/dev-token
  review, or enterprise licensing.
- **Three auth patterns cover 97/100** (OAuth2, API key/token, Basic).
- **Self-serve is a category property:** Dev/Infra and PM are 100% self-serve;
  Marketing/Ads, Fintech and AI-native are where the gates cluster.
- **33/100 already ship an MCP server** — and that's a *lower bound* (see below).

## How the agent works

```
apps.csv → [Composio tools: SEARCH + FIRECRAWL] → [Claude extracts schema] → results.json → [verify loop] → build_site.py → site/index.html
```

1. **`agent/research_agent.py`** — for each app, the agent is given web-search and
   doc-scraping tools **from Composio** (`COMPOSIO_SEARCH`, `FIRECRAWL`) and Claude
   fills a strict schema (`agent/schema.py`) with an evidence URL and a
   self-reported confidence. Dogfooding Composio here is deliberate: the agent that
   decides what becomes a Composio toolkit is itself built on Composio.
2. **`agent/verify.py`** — re-checks every low-confidence (or `mcp="no"`) row with an
   independent pass that must open the docs and run a dedicated `"<app> MCP server"`
   search, then scores the agent against a hand-labelled sample (`data/human_labels.json`).
3. **`agent/build_site.py`** — renders the single-file case study from
   `data/results.json`, so the page can never drift from the data.

## Where a human was needed

- **Obscure / login-walled apps** — the agent initially gave up on *fanbasis* and
  could not confirm *Waterfall.io* / *iPayX*. A human resolved fanbasis (it has a
  full REST API + SDKs) and parked the other two honestly.
- **Judgment calls** — "partial vs. gated" when a sandbox is self-serve but
  production needs approval.
- **MCP detection** — the first pass *systematically under-counted* MCP servers
  (it missed Pylon's and Reducto's). The human fix became a permanent step in
  `verify.py`.

## Verification result

Hand-verified sample weighted toward the agent's least-confident rows:
**first-pass field accuracy 50% → 100% after the loop.** Full hits/misses are on
the case-study page. Honesty policy: a gated or undocumented app is recorded as
the *finding*, not hidden as a failure — no paid app accounts were used.

## Run it

Two reasoner options — both use your Composio key for the tools.

**Option A — Gemini (free, recommended).** Free Gemini API key from
[aistudio.google.com/apikey](https://aistudio.google.com/apikey), no card required.

```bash
pip install -r requirements.txt
export COMPOSIO_API_KEY=...      # free key from composio.dev
export GOOGLE_API_KEY=...        # free key from Google AI Studio
export COMPOSIO_USER_ID=default

python agent/research_agent_gemini.py --limit 5   # smoke test first
python agent/research_agent_gemini.py             # full 100
```

**Option B — Claude (paid, ~$1–2 for 100 apps).**

```bash
export ANTHROPIC_API_KEY=...
export COMPOSIO_API_KEY=...
python agent/research_agent.py            # (--local for LLM-only, no Composio)
```

**Then, for either option:**

```bash
python agent/verify.py --score-only   # reproduce the 50% -> 100% accuracy (no keys needed)
python agent/verify.py                # full automated re-check loop (needs an LLM key)
python agent/build_site.py            # rebuild site/index.html from results.json
```

The committed `data/results.json` is the verified canonical output the case study is
built from. `--score-only` reproduces the headline accuracy number from that data with
no API calls, so the result is checkable even without keys.

## Repo layout

```
agent/
  apps_data.py       # the 100-app dataset (source of truth) -> results.json
  apps.csv           # agent input (id, name, docs hint, category)
  schema.py          # pydantic AppResearch schema (the output contract)
  research_agent.py  # main agent — Claude reasoner (Composio tools); --local fallback
  research_agent_gemini.py  # same agent — free Gemini reasoner (Composio tools)
  verify.py          # verification loop + human-sample scoring
  build_site.py      # renders the case study from results.json
data/
  results.json       # enriched output (fields + tier + verification snapshots)
  human_labels.json  # hand-verified ground-truth sample
site/
  index.html         # the deliverable — single self-contained page
requirements.txt
```

## Deploy the page (GitHub Pages)

1. Push this repo to GitHub.
2. Repo → **Settings → Pages** → Source: *Deploy from a branch* → `main` / `/root`
   (or move `site/index.html` to the repo root / `/docs`).
3. Replace `REPO_URL` in `build_site.py` and the URL at the top of this README with
   your live link, then re-run `python agent/build_site.py`.

## Honesty & limitations

The dataset was produced by an LLM-driven pipeline (Claude + web tools) and then
corrected by a verification loop and hand checks against the live docs linked in
each row. Confidence is stored per row. Re-run the agent with your own keys to
reproduce or extend it — every claim is explainable end-to-end.
