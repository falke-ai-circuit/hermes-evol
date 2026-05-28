"""
EVOL — Full GLOBAL Cycle: All Phases × All Profiles
deepseek-v4-pro via Venice for every phase.
Shows per-profile results so you can verify config scoping.
"""
import os, json, time, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

with open('/opt/data/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            if k and v:
                os.environ[k] = v.strip('"').strip("'")

from config import EvolConfig
from registry import absorb, reflect, explore, express, memorize

DEEPSEEK = {"provider": "venice", "model": "deepseek-v4-pro"}

PROFILES = [
    "analyst", "architect", "coder", "conductor", "operative",
    "orchestrator", "researcher", "reviewer", "shadow", "valmet",
]

def banner(text):
    print(f"\n{'#'*70}")
    print(f"# {text}")
    print(f"{'#'*70}")

def phase_header(phase, profile=None):
    tag = f" — {profile}" if profile else ""
    print(f"\n{'─'*70}")
    print(f"│ {phase}{tag}")
    print(f"{'─'*70}")

def set_ds(cfg):
    for p in cfg.phase_models:
        cfg.phase_models[p].provider = DEEPSEEK["provider"]
        cfg.phase_models[p].model = DEEPSEEK["model"]
        cfg.phase_models[p].max_tokens = 4096 if p == "explore" else 8192
        cfg.phase_models[p].temperature = 0.5 if p in ("reflect","memorize") else 0.9

# ═══════════════════════════════════════════════════════════════════
# PHASE 1: ABSORB — all profiles
# ═══════════════════════════════════════════════════════════════════

banner("PHASE 1: ABSORB — All 10 Profiles")
all_absorbed = {}

for prof in PROFILES:
    phase_header("ABSORB", prof)
    t0 = time.time()
    cfg = EvolConfig(profile=prof)
    cfg.search_backend = "duckduckgo"
    set_ds(cfg)
    
    a = absorb(cfg)
    files = a.get("circuit_files", {})
    dt = time.time() - t0
    
    print(f"  files: {list(files.keys())}")
    for fn, content in files.items():
        print(f"    {fn}: {len(content)} chars")
    gw_log = a.get("gateway_log_tail", "")
    print(f"  gateway_log: {len(gw_log)} chars")
    
    all_absorbed[prof] = a
    print(f"  ⏱ {dt:.1f}s")

# ═══════════════════════════════════════════════════════════════════
# PHASE 2: REFLECT — per-profile (profile mode)
# ═══════════════════════════════════════════════════════════════════

banner("PHASE 2: REFLECT — Per-Profile Mode")
all_reflected = {}

for prof in PROFILES:
    phase_header("REFLECT", prof)
    cfg = EvolConfig(profile=prof)
    cfg.edit_mode = "suggested"
    cfg.search_backend = "duckduckgo"
    set_ds(cfg)
    
    t0 = time.time()
    r = reflect(cfg, all_absorbed[prof])
    dt = time.time() - t0
    
    patterns = r.get("patterns", [])
    anomalies = r.get("anomalies", [])
    bridge = r.get("bridge_signals", [])
    alive = len(patterns) > 0 and patterns[0].get("name") != "unparsed-reflect"
    
    print(f"  patterns: {len(patterns)} | anomalies: {len(anomalies)} | bridge: {len(bridge)}")
    for p in patterns[:3]:
        name = p.get("name", "?")
        wt = p.get("weight", 0)
        ev = p.get("evidence", "")[:100]
        print(f"    → {name} (wt={wt:.2f}): {ev}...")
    print(f"  status: {'✅ ALIVE' if alive else '❌ FLAT'} | ⏱ {dt:.1f}s")
    
    all_reflected[prof] = r

# ═══════════════════════════════════════════════════════════════════
# PHASE 3: EXPLORE — per-profile
# ═══════════════════════════════════════════════════════════════════

banner("PHASE 3: EXPLORE — Per-Profile Mode")
all_explored = {}

for prof in PROFILES:
    phase_header("EXPLORE", prof)
    cfg = EvolConfig(profile=prof)
    cfg.edit_mode = "suggested"
    cfg.search_backend = "duckduckgo"
    set_ds(cfg)
    
    t0 = time.time()
    e = explore(cfg, all_reflected[prof])
    dt = time.time() - t0
    
    queries = e.get("queries", [])
    results = e.get("results", [])
    discoveries = e.get("discoveries", [])
    
    print(f"  queries: {len(queries)} | results: {len(results)} | discoveries: {len(discoveries)}")
    for q in queries[:2]:
        print(f"    query: {q[:120]}...")
    for r in results[:2]:
        print(f"    result: {r.get('source','')[:70]} → {r.get('snippet','')[:80]}...")
    for d in discoveries[:2]:
        print(f"    discovery: {d.get('topic','?')[:100]} (novelty={d.get('novelty',0):.2f})")
    print(f"  ⏱ {dt:.1f}s")
    
    all_explored[prof] = e

# ═══════════════════════════════════════════════════════════════════
# PHASE 4: EXPRESS — per-profile
# ═══════════════════════════════════════════════════════════════════

banner("PHASE 4: EXPRESS — Per-Profile Mode")
all_expressed = {}

for prof in PROFILES:
    phase_header("EXPRESS", prof)
    cfg = EvolConfig(profile=prof)
    cfg.edit_mode = "suggested"
    cfg.search_backend = "duckduckgo"
    set_ds(cfg)
    cfg.phase_models["express"].temperature = 0.9
    
    t0 = time.time()
    x = express(cfg, all_reflected[prof], all_explored.get(prof))
    dt = time.time() - t0
    
    mood = x.get("mood", "?")
    mono = x.get("monologue", "")
    insights = x.get("insights", [])
    
    print(f"  mood: {mood} | monologue: {len(mono)} chars | insights: {len(insights)}")
    for i in insights[:3]:
        print(f"    → {i[:150]}...")
    alive = len(mono) > 200
    print(f"  status: {'✅ ALIVE' if alive else '❌ FLAT'} | ⏱ {dt:.1f}s")
    
    all_expressed[prof] = x

# ═══════════════════════════════════════════════════════════════════
# PHASE 5: MEMORIZE — per-profile
# ═══════════════════════════════════════════════════════════════════

banner("PHASE 5: MEMORIZE — Per-Profile Mode")
all_memorized = {}

for prof in PROFILES:
    phase_header("MEMORIZE", prof)
    cfg = EvolConfig(profile=prof)
    cfg.edit_mode = "suggested"
    cfg.search_backend = "duckduckgo"
    set_ds(cfg)
    
    t0 = time.time()
    m = memorize(
        cfg,
        all_reflected[prof],
        all_expressed.get(prof),
        all_explored.get(prof),
    )
    dt = time.time() - t0
    
    items = m.get("items", [])
    applied = m.get("applied", [])
    proposed = m.get("proposals", [])
    
    print(f"  scored: {len(items)} | applied: {len(applied)} | proposed: {len(proposed)}")
    for p in proposed[:3]:
        print(f"    → {p.get('file','?')} (wt={p.get('weight',0):.2f} vs thr={p.get('threshold',0):.2f})")
        print(f"      {p.get('proposed_change','')[:130]}...")
    print(f"  ⏱ {dt:.1f}s")
    
    all_memorized[prof] = m

# ═══════════════════════════════════════════════════════════════════
# FINAL VERDICT TABLE
# ═══════════════════════════════════════════════════════════════════

banner("FINAL VERDICT — Per-Profile Summary")

print(f"\n{'Profile':<15} {'ABSORB':>8} {'REFLECT':>10} {'EXPLORE':>10} {'EXPRESS':>12} {'MEMORIZE':>12}")
print(f"{'─'*15} {'─'*8} {'─'*10} {'─'*10} {'─'*12} {'─'*12}")

for prof in PROFILES:
    ab = f"{len(all_absorbed[prof].get('circuit_files',{}))}f"
    
    rp = all_reflected[prof]
    r_ok = len(rp.get("patterns",[])) > 0 and rp["patterns"][0].get("name") != "unparsed-reflect"
    rf = f"{len(rp.get('patterns',[]))}p" + ("✅" if r_ok else "❌")
    
    ep = all_explored[prof]
    ex = f"{len(ep.get('discoveries',[]))}d"
    
    xp = all_expressed[prof]
    x_ok = len(xp.get("monologue","")) > 200
    xf = f"{len(xp.get('monologue',''))}c" + ("✅" if x_ok else "❌")
    
    mp = all_memorized[prof]
    mf = f"{len(mp.get('proposed',[]))}prop"
    
    print(f"{prof:<15} {ab:>8} {rf:>10} {ex:>10} {xf:>12} {mf:>12}")

# Quick stats
total_ok = sum(1 for prof in PROFILES 
    if len(all_reflected[prof].get("patterns",[])) > 0 
    and all_reflected[prof]["patterns"][0].get("name") != "unparsed-reflect"
    and len(all_expressed[prof].get("monologue","")) > 200)

total_proposals = sum(len(all_memorized[prof].get("proposed",[])) for prof in PROFILES)
total_discoveries = sum(len(all_explored[prof].get("discoveries",[])) for prof in PROFILES)

print(f"\nProfiles with all phases alive: {total_ok}/{len(PROFILES)}")
print(f"Total proposals generated:      {total_proposals}")
print(f"Total discoveries:              {total_discoveries}")

banner("GLOBAL CYCLE COMPLETE")
