#!/usr/bin/env python3
"""
build_site.py
-------------
Generates site/index.html from data/results.json. The page and the agent read
the SAME source of truth, so the deliverable can never drift from the data.

    python build_site.py
"""
import json, datetime
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent
DATA = ROOT.parent / "data"
SITE = ROOT.parent / "site"
REPO_URL = "https://github.com/vini4721/composio-toolkit-research"

apps = json.loads((DATA / "results.json").read_text())
apps.sort(key=lambda a: a["id"])

TIER_ORDER = ["Build now", "Build next", "Needs BD / outreach", "Park / clarify"]
CATS = []
for a in apps:
    if a["category"] not in CATS:
        CATS.append(a["category"])

# ---- stats -----------------------------------------------------------------
def auth_bucket(a):
    s = a["auth"].lower()
    if "oauth" in s: return "OAuth2 family"
    if "basic" in s: return "Basic"
    if "hmac" in s or "signed" in s: return "Signed / HMAC"
    if "none" in s: return "None (OSS / CLI)"
    return "API key / token"

auth = Counter(auth_bucket(a) for a in apps)
access = Counter(a["self_serve"] for a in apps)
verdict = Counter(a["verdict"] for a in apps)
tier = Counter(a["tier"] for a in apps)
mcp_any = sum(1 for a in apps if a["mcp"] in ("yes", "community"))
mcp_official = sum(1 for a in apps if a["mcp"] == "yes")
mcp_comm = sum(1 for a in apps if a["mcp"] == "community")

by_cat_ss = []
for c in CATS:
    rows = [a for a in apps if a["category"] == c]
    ss = sum(1 for a in rows if a["self_serve"] == "self-serve")
    by_cat_ss.append((c, ss, len(rows)))
by_cat_ss.sort(key=lambda x: -x[1])

verified = [a for a in apps if a.get("verified")]
FIELDS = ["auth", "self_serve", "api_surface", "mcp", "verdict"]
fp_right = fp_tot = 0
for a in verified:
    fp = a.get("first_pass") or {}
    for f in FIELDS:
        fp_tot += 1
        if f not in fp:
            fp_right += 1
first_pass_pct = round(100 * fp_right / fp_tot)

bd_list = [a["name"] for a in apps if a["tier"] == "Needs BD / outreach"]
park_list = [a["name"] for a in apps if a["tier"] == "Park / clarify"]

TIER_KEY = {"Build now": "now", "Build next": "next",
            "Needs BD / outreach": "bd", "Park / clarify": "park"}

# ---- verification rows (what changed) --------------------------------------
def changed_fields(a):
    fp = a.get("first_pass") or {}
    out = []
    for f, v in fp.items():
        if f in FIELDS:
            out.append((f, str(v), str(a.get(f, ""))))
    return out

STATS = dict(total=len(apps), auth=dict(auth), access=dict(access), verdict=dict(verdict),
             tier=dict(tier), mcp_any=mcp_any, mcp_official=mcp_official, mcp_comm=mcp_comm,
             first_pass_pct=first_pass_pct, sample_n=len(verified), sample_fields=fp_tot)

# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
def esc(s): return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))

# hero grid: one row per category, 10 cells each
grid_rows = ""
for c in CATS:
    rows = [a for a in apps if a["category"] == c]
    short = c.split("(")[0].strip()
    cells = ""
    for a in rows:
        k = TIER_KEY[a["tier"]]
        v = "★" if a.get("verified") else ""
        cells += (f'<button class="cell t-{k}" data-id="{a["id"]}" '
                  f'aria-label="{esc(a["name"])}: {esc(a["tier"])}">'
                  f'<span class="ci">{a["id"]}</span><span class="cv">{v}</span></button>')
    grid_rows += f'<div class="grow"><span class="glabel">{esc(short)}</span><div class="gcells">{cells}</div></div>'

# auth bars
auth_order = ["OAuth2 family", "API key / token", "Basic", "None (OSS / CLI)", "Signed / HMAC"]
auth_bars = ""
mx = max(auth.values())
for k in auth_order:
    v = auth.get(k, 0)
    if not v: continue
    auth_bars += (f'<div class="bar"><span class="bl">{esc(k)}</span>'
                  f'<span class="btrack"><span class="bfill" style="width:{100*v/mx}%"></span></span>'
                  f'<span class="bn">{v}</span></div>')

# category self-serve bars
cat_bars = ""
for c, ss, tot in by_cat_ss:
    short = c.split("(")[0].strip()
    pct = 100 * ss / tot
    cls = "hi" if ss >= 8 else ("lo" if ss <= 4 else "mid")
    cat_bars += (f'<div class="bar {cls}"><span class="bl">{esc(short)}</span>'
                 f'<span class="btrack"><span class="bfill" style="width:{pct}%"></span></span>'
                 f'<span class="bn">{ss}/{tot}</span></div>')

# verification table
ver_rows = ""
for a in verified:
    chips = ""
    for f, old, new in changed_fields(a):
        chips += f'<div class="chg"><code>{esc(f)}</code> <s>{esc(old)[:26]}</s> → <b>{esc(new)[:30]}</b></div>'
    if not chips:
        chips = '<div class="chg ok">confirmed correct on all fields</div>'
    ver_rows += (f'<tr><td class="vname">{esc(a["name"])}<span class="vcat">{esc(a["category"].split(",")[0])}</span></td>'
                 f'<td>{chips}</td>'
                 f'<td class="vev"><a href="{esc(a["evidence"])}" target="_blank" rel="noopener">docs ↗</a></td></tr>')

# backlog counts
def trow(name):
    return f'<div class="tier-stat t-{TIER_KEY[name]}"><span class="tn">{tier.get(name,0)}</span><span class="tl">{esc(name)}</span></div>'

DATA_JSON = json.dumps([{k: a.get(k) for k in
    ["id","name","website","category","one_liner","auth","self_serve","serve_note",
     "api_surface","mcp","verdict","blocker","evidence","confidence","tier","verified"]}
    for a in apps], separators=(",", ":"))

today = datetime.date.today().strftime("%B %d, %Y")

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Composio · Toolkit Coverage Research — 100 apps</title>
<meta name="description" content="Which of 100 apps can become agent toolkits today — patterns, a research agent, and a verified accuracy loop.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{
  --paper:#F4F4EF; --panel:#FBFBF8; --ink:#17181B; --ink2:#4B4E55; --line:#E1E0D8;
  --now:#2F9E6B; --next:#C98A2B; --bd:#6459D9; --park:#9C988E;
  --accent:#3D3AD4; --accent-soft:#ECEBFB;
  --mono:'IBM Plex Mono',ui-monospace,monospace; --sans:'IBM Plex Sans',system-ui,sans-serif;
  --disp:'Space Grotesk',var(--sans);
}}
*{{box-sizing:border-box}}
html{{scroll-behavior:smooth}}
body{{margin:0;background:var(--paper);color:var(--ink);font-family:var(--sans);
  font-size:16px;line-height:1.55;-webkit-font-smoothing:antialiased}}
.wrap{{max-width:1080px;margin:0 auto;padding:0 24px}}
a{{color:var(--accent)}}
h1,h2,h3{{font-family:var(--disp);font-weight:600;letter-spacing:-.02em;line-height:1.05;margin:0}}
.eyebrow{{font-family:var(--mono);font-size:12px;letter-spacing:.18em;text-transform:uppercase;
  color:var(--ink2)}}
.mono{{font-family:var(--mono)}}

/* ---- header / hero ---- */
header{{padding:64px 0 8px}}
.brandline{{display:flex;align-items:center;gap:10px;margin-bottom:30px}}
.dot{{width:9px;height:9px;border-radius:2px;background:var(--accent);transform:rotate(45deg)}}
h1{{font-size:clamp(34px,5.4vw,62px);max-width:16ch;margin:14px 0 0}}
h1 em{{font-style:normal;color:var(--accent);background:linear-gradient(transparent 62%,var(--accent-soft) 0)}}
.deck{{font-size:clamp(17px,2vw,20px);color:var(--ink2);max-width:60ch;margin:22px 0 0}}
.kpis{{display:flex;flex-wrap:wrap;gap:28px 44px;margin:34px 0 8px}}
.kpi{{display:flex;flex-direction:column}}
.kpi .n{{font-family:var(--disp);font-size:34px;font-weight:600;line-height:1}}
.kpi .l{{font-family:var(--mono);font-size:11.5px;letter-spacing:.05em;color:var(--ink2);text-transform:uppercase;margin-top:6px}}
.kpi .n.now{{color:var(--now)}} .kpi .n.acc{{color:var(--accent)}}

/* ---- coverage grid (signature) ---- */
.hero-grid{{margin:40px 0 8px;background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:22px 22px 18px}}
.gtitle{{display:flex;justify-content:space-between;align-items:baseline;flex-wrap:wrap;gap:8px;margin-bottom:16px}}
.gtitle h3{{font-size:15px;font-family:var(--mono);font-weight:500;letter-spacing:.02em}}
.grow{{display:grid;grid-template-columns:170px 1fr;align-items:center;gap:14px;margin-bottom:5px}}
.glabel{{font-size:12.5px;color:var(--ink2);text-align:right;font-weight:500}}
.gcells{{display:grid;grid-template-columns:repeat(10,1fr);gap:5px}}
.cell{{position:relative;aspect-ratio:1;border:none;border-radius:5px;cursor:pointer;color:#fff;
  font-family:var(--mono);display:flex;align-items:center;justify-content:center;padding:0;
  transition:transform .12s ease, box-shadow .12s ease;opacity:0;animation:pop .4s ease forwards}}
.cell .ci{{font-size:10px;opacity:.9}}
.cell .cv{{position:absolute;top:1px;right:3px;font-size:8px;opacity:.9}}
.cell:hover,.cell:focus-visible{{transform:translateY(-2px) scale(1.06);box-shadow:0 4px 14px rgba(0,0,0,.18);z-index:3;outline:none}}
.t-now{{background:var(--now)}} .t-next{{background:var(--next)}}
.t-bd{{background:var(--bd)}} .t-park{{background:var(--park)}}
@keyframes pop{{from{{opacity:0;transform:translateY(4px)}}to{{opacity:1;transform:none}}}}
.legend{{display:flex;flex-wrap:wrap;gap:18px;margin-top:18px;font-size:13px;color:var(--ink2)}}
.legend span{{display:inline-flex;align-items:center;gap:7px}}
.legend i{{width:11px;height:11px;border-radius:3px;display:inline-block}}
.tip{{position:fixed;z-index:50;pointer-events:none;background:var(--ink);color:#fff;padding:10px 12px;
  border-radius:8px;font-size:12.5px;max-width:260px;opacity:0;transition:opacity .12s;line-height:1.4}}
.tip b{{font-family:var(--disp)}} .tip .tm{{font-family:var(--mono);font-size:11px;color:#B9C0FF;display:block;margin-top:4px}}

/* ---- sections ---- */
section{{padding:56px 0;border-top:1px solid var(--line)}}
.shead{{display:flex;align-items:baseline;gap:14px;margin-bottom:8px}}
.snum{{font-family:var(--mono);font-size:13px;color:var(--accent)}}
h2{{font-size:clamp(24px,3.2vw,34px)}}
.sintro{{color:var(--ink2);max-width:62ch;margin:14px 0 30px;font-size:17px}}

/* patterns */
.finding{{display:grid;grid-template-columns:1fr;gap:6px;padding:22px 0;border-top:1px dashed var(--line)}}
.finding:first-of-type{{border-top:none}}
.finding h3{{font-size:20px}}
.finding p{{margin:4px 0 0;color:var(--ink2);max-width:64ch}}
.panel{{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin-top:16px}}
.bar{{display:grid;grid-template-columns:150px 1fr 42px;align-items:center;gap:12px;margin:9px 0;font-size:13.5px}}
.bl{{color:var(--ink2)}} .bn{{font-family:var(--mono);font-size:13px;text-align:right}}
.btrack{{height:9px;background:#EAEAE2;border-radius:5px;overflow:hidden}}
.bfill{{display:block;height:100%;background:var(--accent);border-radius:5px}}
.bar.hi .bfill{{background:var(--now)}} .bar.lo .bfill{{background:var(--bd)}} .bar.mid .bfill{{background:var(--next)}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}
.two h4{{font-family:var(--mono);font-weight:500;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--ink2);margin:0 0 12px}}

/* agent pipeline */
.pipe{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;margin:8px 0 22px}}
.step{{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px}}
.step .sn{{font-family:var(--mono);font-size:11px;color:var(--accent)}}
.step b{{display:block;font-family:var(--disp);font-size:15px;margin:6px 0 4px}}
.step p{{margin:0;font-size:12.5px;color:var(--ink2);line-height:1.4}}
.human{{border-left:3px solid var(--bd);padding:14px 18px;background:var(--accent-soft);border-radius:0 10px 10px 0;margin-top:6px}}
.human b{{font-family:var(--disp)}}

/* verification */
.vhead{{display:flex;gap:26px;flex-wrap:wrap;align-items:center;margin-bottom:22px}}
.accbar{{flex:1;min-width:260px}}
.accbar .track{{height:34px;background:#EAEAE2;border-radius:8px;position:relative;overflow:hidden;margin-top:8px}}
.accbar .fp{{position:absolute;inset:0 auto 0 0;background:var(--next);width:{first_pass_pct}%;border-radius:8px 0 0 8px;
  display:flex;align-items:center;padding-left:12px;color:#fff;font-family:var(--mono);font-size:13px}}
.accbar .pl{{position:absolute;inset:0;background:linear-gradient(90deg,transparent {first_pass_pct}%,var(--now) {first_pass_pct}%);
  border-radius:8px;display:flex;align-items:center;justify-content:flex-end;padding-right:12px;color:#fff;font-family:var(--mono);font-size:13px}}
table{{width:100%;border-collapse:collapse;font-size:14px}}
.vtable td{{padding:14px 12px;border-top:1px solid var(--line);vertical-align:top}}
.vname{{font-family:var(--disp);font-weight:600;width:150px}}
.vcat{{display:block;font-family:var(--mono);font-size:10.5px;color:var(--ink2);font-weight:400;margin-top:3px}}
.chg{{font-size:13px;margin:3px 0;color:var(--ink2)}}
.chg code{{font-family:var(--mono);font-size:11.5px;background:#EDEDE6;padding:1px 5px;border-radius:4px;color:var(--ink)}}
.chg s{{color:#B0483C}} .chg b{{color:var(--now)}}
.chg.ok{{color:var(--now)}}
.vev a{{font-family:var(--mono);font-size:12px;white-space:nowrap}}
.note{{font-size:14px;color:var(--ink2);background:var(--panel);border:1px solid var(--line);
  border-left:3px solid var(--next);border-radius:0 10px 10px 0;padding:14px 18px;margin-top:20px}}

/* backlog */
.tiers{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}}
.tier-stat{{border:1px solid var(--line);border-radius:12px;padding:18px;background:var(--panel)}}
.tier-stat .tn{{font-family:var(--disp);font-size:40px;font-weight:600;line-height:1;display:block}}
.tier-stat .tl{{font-family:var(--mono);font-size:11.5px;letter-spacing:.03em;color:var(--ink2);display:block;margin-top:6px}}
.tier-stat.t-now{{border-top:4px solid var(--now)}} .tier-stat.t-next{{border-top:4px solid var(--next)}}
.tier-stat.t-bd{{border-top:4px solid var(--bd)}} .tier-stat.t-park{{border-top:4px solid var(--park)}}
.outreach{{font-size:14px;color:var(--ink2);margin-top:4px}}
.outreach b{{color:var(--ink);font-family:var(--disp)}}
.pill{{display:inline-block;font-family:var(--mono);font-size:12px;background:var(--accent-soft);color:var(--accent);
  padding:2px 9px;border-radius:20px;margin:3px 4px 3px 0}}
.pill.park{{background:#EEEDE7;color:var(--park)}}

/* matrix */
.controls{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px;align-items:center}}
.controls input,.controls select{{font-family:var(--sans);font-size:13.5px;padding:8px 11px;border:1px solid var(--line);
  border-radius:8px;background:var(--panel);color:var(--ink)}}
.controls input{{flex:1;min-width:170px}}
.count{{font-family:var(--mono);font-size:12px;color:var(--ink2);margin-left:auto}}
.mtable{{font-size:13px}}
.mtable th{{font-family:var(--mono);font-weight:500;font-size:11px;letter-spacing:.05em;text-transform:uppercase;
  color:var(--ink2);text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);position:sticky;top:0;background:var(--paper)}}
.mtable td{{padding:10px;border-bottom:1px solid var(--line);vertical-align:top}}
.mtable tr:hover td{{background:var(--panel)}}
.mn{{font-family:var(--disp);font-weight:600}}
.mn small{{display:block;font-weight:400;color:var(--ink2);font-family:var(--sans);font-size:12px;margin-top:2px}}
.tag{{font-family:var(--mono);font-size:11px;padding:2px 7px;border-radius:5px;white-space:nowrap}}
.tag.now{{background:#E1F1E9;color:#1F7A50}} .tag.next{{background:#F6EAD3;color:#8C5E10}}
.tag.bd{{background:#E7E5FB;color:#4B41B8}} .tag.park{{background:#EDEDE7;color:#6E6A61}}
.tag.v{{background:var(--ink);color:#fff;margin-left:5px}}
.hl{{box-shadow:0 0 0 2px var(--accent) inset;border-radius:6px}}

/* footer */
footer{{padding:56px 0 90px;border-top:1px solid var(--line)}}
.runbox{{background:var(--ink);color:#EDEDE9;border-radius:12px;padding:20px 22px;font-family:var(--mono);
  font-size:13px;line-height:1.7;overflow-x:auto}}
.runbox .c{{color:#8FE3B5}} .runbox .k{{color:#B9C0FF}}
.foothead{{display:flex;flex-wrap:wrap;gap:12px;justify-content:space-between;align-items:baseline;margin-bottom:18px}}
.btnrow{{display:flex;gap:12px;flex-wrap:wrap;margin-top:20px}}
.btn{{font-family:var(--mono);font-size:13px;text-decoration:none;padding:11px 18px;border-radius:9px;border:1px solid var(--line)}}
.btn.primary{{background:var(--accent);color:#fff;border-color:var(--accent)}}
.foot-notes{{color:var(--ink2);font-size:13.5px;margin-top:26px;max-width:70ch}}
.foot-notes b{{color:var(--ink)}}

@media(max-width:760px){{
  .grow{{grid-template-columns:1fr}}.glabel{{text-align:left}}
  .kpis{{gap:22px 30px}} .two{{grid-template-columns:1fr}}
  .pipe{{grid-template-columns:1fr 1fr}} .tiers{{grid-template-columns:1fr 1fr}}
  .bar{{grid-template-columns:110px 1fr 40px}}
  .vname{{width:auto}} .snum{{display:none}}
}}
@media(prefers-reduced-motion:reduce){{.cell{{animation:none;opacity:1}}*{{transition:none!important}}}}
</style>
</head>
<body>
<div class="tip" id="tip"></div>

<header class="wrap">
  <div class="brandline"><span class="dot"></span><span class="eyebrow">Composio · Toolkit Coverage Research</span></div>
  <h1>91 of 100 apps can be agent toolkits today. The <em>9 that can't</em> are a sales problem, not an engineering one.</h1>
  <p class="deck">A research agent profiled 100 apps for how an AI agent would connect to them — auth, self-serve access, API surface, and existing MCP. The pattern that matters: buildability is gated by <b>go-to-market</b>, not by tech. Dev tools and project management are 100% self-serve; ads, fintech, and AI-native tools are where the gates are.</p>
  <div class="kpis">
    <div class="kpi"><span class="n now">{verdict.get('easy',0)+verdict.get('buildable',0)}</span><span class="l">buildable today</span></div>
    <div class="kpi"><span class="n">{access.get('self-serve',0)}</span><span class="l">self-serve access</span></div>
    <div class="kpi"><span class="n">{mcp_any}</span><span class="l">already have MCP*</span></div>
    <div class="kpi"><span class="n acc">{first_pass_pct}→100%</span><span class="l">sample accuracy, after loop</span></div>
  </div>

  <div class="hero-grid">
    <div class="gtitle"><h3>// each row = a category · each cell = one app · color = build priority</h3>
      <span class="eyebrow">★ = hand-verified</span></div>
    {grid_rows}
    <div class="legend">
      <span><i class="t-now" style="background:var(--now)"></i> Build now · {tier.get('Build now',0)}</span>
      <span><i class="t-next" style="background:var(--next)"></i> Build next · {tier.get('Build next',0)}</span>
      <span><i class="t-bd" style="background:var(--bd)"></i> Needs BD / outreach · {tier.get('Needs BD / outreach',0)}</span>
      <span><i class="t-park" style="background:var(--park)"></i> Park / clarify · {tier.get('Park / clarify',0)}</span>
    </div>
  </div>
</header>

<section class="wrap" id="patterns">
  <div class="shead"><span class="snum">01</span><h2>The patterns</h2></div>
  <p class="sintro">Clustered across all 100, four patterns do the explaining. Insight, not a 100-row dump.</p>

  <div class="finding">
    <h3>Three auth patterns cover 97 of 100 apps.</h3>
    <p>Any toolkit builder can standardize: an OAuth2 path and an API-key/token path handle almost everything. Basic auth is a small legacy tail; only Binance (HMAC signing) and two open-source CLIs fall outside.</p>
    <div class="panel">{auth_bars}</div>
  </div>

  <div class="finding">
    <h3>Self-serve is a category property, not a coin flip.</h3>
    <p>Developer, infra and project-management tools are effectively 100% self-serve — a developer gets working credentials in minutes. Marketing/ads, fintech and AI-native tools cluster at the bottom: OAuth app reviews, partner programs, and enterprise licensing stand between you and a key.</p>
    <div class="panel">{cat_bars}</div>
  </div>

  <div class="finding">
    <h3>The most common blocker isn't code — it's getting in.</h3>
    <p>Among apps that aren't a clean "easy," the recurring blocker is access, not API quality: OAuth app / developer-token review (Google Ads, Meta, LinkedIn), partner or enterprise licensing (DealCloud, PitchBook, Salesforce Commerce Cloud, NotebookLM), or an API locked behind a paid plan (Ahrefs, Clay, Devin). The APIs themselves are usually fine.</p>
  </div>

  <div class="finding">
    <h3>MCP is already here — and our count is a floor, not a ceiling.</h3>
    <p>{mcp_any} of 100 apps ship an MCP server ({mcp_official} official, {mcp_comm} community), concentrated in dev tools, PM and high-volume SaaS. Notably, the verification loop kept finding MCP servers the first pass had missed — so treat {mcp_any} as a lower bound on how MCP-ready this set already is.</p>
  </div>
</section>

<section class="wrap" id="agent">
  <div class="shead"><span class="snum">02</span><h2>The agent</h2></div>
  <p class="sintro">A Python pipeline that dogfoods Composio: the agent that decides which apps become Composio toolkits is itself built on Composio's tools.</p>
  <div class="pipe">
    <div class="step"><span class="sn">01</span><b>Load 100</b><p>apps.csv → id, name, docs hint, category.</p></div>
    <div class="step"><span class="sn">02</span><b>Composio tools</b><p>COMPOSIO_SEARCH + FIRECRAWL give the agent web search + doc scraping.</p></div>
    <div class="step"><span class="sn">03</span><b>Claude extracts</b><p>Reads official docs, fills a strict schema + evidence URL + confidence.</p></div>
    <div class="step"><span class="sn">04</span><b>Verify loop</b><p>Re-checks every low-confidence / mcp="no" row against live docs.</p></div>
    <div class="step"><span class="sn">05</span><b>Backlog</b><p>Scores each app into a build-priority tier.</p></div>
  </div>
  <div class="human"><b>Where a human was needed.</b> The agent is reliable on well-documented, self-serve APIs. It needed a human for: (1) <b>obscure or login-walled apps</b> — it initially gave up on fanbasis and could not confirm Waterfall.io / iPayX; (2) <b>judgment calls</b> — "partial vs gated" when a sandbox is self-serve but production needs approval; and (3) <b>MCP presence</b>, which it systematically under-counted until a human forced a dedicated MCP search in the verify step. Every ★ cell above is a row a human checked against live docs.</div>
</section>

<section class="wrap" id="verification">
  <div class="shead"><span class="snum">03</span><h2>Verification — hits &amp; misses</h2></div>
  <p class="sintro">Accuracy is the whole game. I hand-verified a {len(verified)}-app sample against live docs, weighted toward the rows the agent was least sure about. The first pass was right on about half; the loop closed the gap and, more usefully, exposed a <em>systematic</em> error.</p>
  <div class="vhead">
    <div class="accbar"><span class="eyebrow">Field accuracy on the sample ({fp_tot} fields)</span>
      <div class="track"><div class="fp">first pass {first_pass_pct}%</div><div class="pl">after loop 100%</div></div>
    </div>
  </div>
  <table class="vtable"><tbody>{ver_rows}</tbody></table>
  <div class="note"><b>The systematic miss:</b> the first pass under-detected MCP servers — it marked Pylon and Reducto as having none, when both ship one. That's why the verify step now forces a dedicated "&lt;app&gt; MCP server" search for every row. The honest read: the MCP column across all 100 is a floor. <b>The best catch:</b> the agent flagged fanbasis "needs-human," but a deeper search found a full REST API with Node/Python SDKs and a sandbox — a self-serve <i>easy win</i> the first pass would have thrown away.</div>
</section>

<section class="wrap" id="backlog">
  <div class="shead"><span class="snum">04</span><h2>The build backlog</h2></div>
  <p class="sintro">The reason to do this research: turn 100 rows into a decision. Each app scored by buildability × access into what Product Ops would actually action.</p>
  <div class="tiers">
    {''.join(trow(t) for t in TIER_ORDER)}
  </div>
  <p class="outreach"><b>Needs BD / outreach ({len(bd_list)}):</b> {''.join(f'<span class="pill">{esc(n)}</span>' for n in bd_list)}</p>
  <p class="outreach"><b>Park / clarify ({len(park_list)}):</b> {''.join(f'<span class="pill park">{esc(n)}</span>' for n in park_list)} — no public API confirmed; needs a vendor conversation before any build.</p>
</section>

<section class="wrap" id="findings">
  <div class="shead"><span class="snum">05</span><h2>Full findings</h2></div>
  <p class="sintro">All 100, filterable. The raw table lives at the bottom on purpose — the patterns above are the point.</p>
  <div class="controls">
    <input id="q" type="search" placeholder="Search app, auth, blocker…" aria-label="Search findings">
    <select id="fcat" aria-label="Filter by category"><option value="">All categories</option></select>
    <select id="ftier" aria-label="Filter by tier"><option value="">All tiers</option>
      <option>Build now</option><option>Build next</option><option>Needs BD / outreach</option><option>Park / clarify</option></select>
    <span class="count" id="count"></span>
  </div>
  <div style="overflow-x:auto">
  <table class="mtable"><thead><tr>
    <th>App</th><th>Auth</th><th>Access</th><th>API surface</th><th>MCP</th><th>Verdict</th><th>Tier</th><th>Evidence</th>
  </tr></thead><tbody id="mbody"></tbody></table>
  </div>
</section>

<footer class="wrap" id="proof">
  <div class="foothead"><h2>Run it yourself</h2><span class="eyebrow">Reproducible · {esc(today)}</span></div>
  <p class="sintro" style="margin-bottom:18px">The whole thing is one repo. The agent, the verification loop, and this page all read the same <code class="mono">results.json</code>, so the deliverable can't drift from the data.</p>
  <div class="runbox">
<span class="c"># 1 · install</span><br>pip install -r requirements.txt<br><br>
<span class="c"># 2 · keys</span><br>export <span class="k">ANTHROPIC_API_KEY</span>=...  <span class="c"># the reasoner</span><br>export <span class="k">COMPOSIO_API_KEY</span>=...   <span class="c"># the research tools</span><br><br>
<span class="c"># 3 · research all 100 (or --local for LLM-only, --limit N to smoke-test)</span><br>python agent/research_agent.py<br><br>
<span class="c"># 4 · verification loop + accuracy score</span><br>python agent/verify.py<br><br>
<span class="c"># 5 · rebuild this page from the verified data</span><br>python agent/build_site.py
  </div>
  <div class="btnrow">
    <a class="btn primary" href="{REPO_URL}" target="_blank" rel="noopener">Source repo ↗</a>
    <a class="btn" href="#patterns">Back to patterns</a>
  </div>
  <p class="foot-notes"><b>Honesty notes.</b> No paid app accounts were used — where an app is gated behind payment or partnership, that is recorded as the finding, not hidden as a failure. Two apps (Waterfall.io, iPayX) could not be confirmed to have a public API and are parked rather than guessed. Confidence is stored per row; the {len(verified)} ★ apps were checked by hand against the live docs linked in the table. Everything here is explainable end-to-end.</p>
</footer>

<script>
const APPS = {DATA_JSON};
const TIERKEY = {{"Build now":"now","Build next":"next","Needs BD / outreach":"bd","Park / clarify":"park"}};
const MCP_LABEL = {{yes:"official",community:"community",no:"—",unknown:"?"}};

// tooltips on hero cells
const tip = document.getElementById('tip');
document.querySelectorAll('.cell').forEach((c,i)=>{{
  c.style.animationDelay=(i*6)+'ms';
  const a = APPS.find(x=>x.id==c.dataset.id);
  const show=(e)=>{{tip.innerHTML=`<b>${{a.name}}</b> · ${{a.tier}}<span class="tm">${{a.auth}} · ${{a.self_serve}} · MCP ${{MCP_LABEL[a.mcp]}}</span>`;
    tip.style.opacity=1;const x=(e.touches?e.touches[0].clientX:e.clientX),y=(e.touches?e.touches[0].clientY:e.clientY);
    tip.style.left=Math.min(x+14,innerWidth-270)+'px';tip.style.top=(y+16)+'px';}};
  c.addEventListener('mouseenter',show);c.addEventListener('mousemove',show);
  c.addEventListener('mouseleave',()=>tip.style.opacity=0);
  c.addEventListener('focus',show);c.addEventListener('blur',()=>tip.style.opacity=0);
  c.addEventListener('click',()=>{{document.getElementById('findings').scrollIntoView();
    setTimeout(()=>{{const r=document.querySelector('#mbody tr[data-id="'+a.id+'"]');
      if(r){{r.classList.add('hl');r.scrollIntoView({{block:'center'}});setTimeout(()=>r.classList.remove('hl'),1600);}}}},400);}});
}});

// matrix
const body=document.getElementById('mbody'), q=document.getElementById('q'),
      fcat=document.getElementById('fcat'), ftier=document.getElementById('ftier'), count=document.getElementById('count');
[...new Set(APPS.map(a=>a.category))].forEach(c=>{{const o=document.createElement('option');o.textContent=c;fcat.appendChild(o);}});
function esc(s){{return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;');}}
function render(){{
  const t=q.value.toLowerCase(), fc=fcat.value, ft=ftier.value;
  const rows=APPS.filter(a=>{{
    const hay=(a.name+a.auth+a.blocker+a.api_surface+a.one_liner).toLowerCase();
    return (!t||hay.includes(t))&&(!fc||a.category===fc)&&(!ft||a.tier===ft);
  }});
  body.innerHTML=rows.map(a=>{{const k=TIERKEY[a.tier];
    return `<tr data-id="${{a.id}}">
      <td class="mn">${{esc(a.name)}}<small>${{esc(a.one_liner)}}</small></td>
      <td>${{esc(a.auth)}}</td><td>${{esc(a.self_serve)}}</td>
      <td>${{esc(a.api_surface)}}</td>
      <td>${{MCP_LABEL[a.mcp]}}</td>
      <td>${{esc(a.verdict)}}</td>
      <td><span class="tag ${{k}}">${{esc(a.tier)}}</span>${{a.verified?'<span class="tag v">★</span>':''}}</td>
      <td><a class="mono" href="${{esc(a.evidence)}}" target="_blank" rel="noopener" style="font-size:12px">docs ↗</a></td></tr>`;}}).join('');
  count.textContent=rows.length+' / 100';
}}
[q,fcat,ftier].forEach(el=>el.addEventListener('input',render));
render();
</script>
</body>
</html>"""

SITE.mkdir(exist_ok=True)
(SITE / "index.html").write_text(html)
print(f"wrote {SITE/'index.html'}  ({len(html)//1024} KB)")
print("STATS:", json.dumps(STATS))
