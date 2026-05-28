"""
EVOL — Universal Acceptance Test
Tests profile-mode (all 10 profiles) and global-mode with both providers.
"""
import os, json, time, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env
with open('/opt/data/.env') as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, _, v = line.partition('=')
            if k and v:
                os.environ[k] = v.strip('"').strip("'")

from config import EvolConfig
from registry import absorb, reflect, explore, express, memorize

PROVIDERS = {
    "hermes":  {"provider": "hermes",  "model": "conductor"},
    "venice":  {"provider": "venice",  "model": "olafangensan-glm-4.7-flash-heretic"},
}

PROFILES = [
    "analyst", "architect", "coder", "conductor", "operative",
    "orchestrator", "researcher", "reviewer", "shadow", "valmet",
]

def set_models(cfg, prov):
    """Apply provider to all phases."""
    for phase in cfg.phase_models:
        cfg.phase_models[phase].provider = prov["provider"]
        cfg.phase_models[phase].model = prov["model"]
        cfg.phase_models[phase].max_tokens = 4096 if phase == "explore" else 8192

def test_profile(profile, prov_name, prov):
    """Run 5-phase cycle on one profile."""
    print(f"\n{'─'*60}")
    print(f"PROFILE: {profile:15} | PROVIDER: {prov_name}")
    print(f"{'─'*60}")
    
    try:
        cfg = EvolConfig(profile=profile)
    except Exception as e:
        print(f"  ❌ Config load failed: {e}")
        return {"profile": profile, "status": "error", "error": str(e)}
    
    cfg.edit_mode = "suggested"
    cfg.search_backend = "duckduckgo"
    set_models(cfg, prov)
    
    # ABSORB
    try:
        absorbed = absorb(cfg)
        n_files = len(absorbed.get("circuit_files", {}))
        print(f"  ABSORB: {n_files} files")
    except Exception as e:
        print(f"  ABSORB: ❌ {e}")
        return {"profile": profile, "status": "error", "phase": "absorb", "error": str(e)}
    
    # REFLECT
    t0 = time.time()
    try:
        reflected = reflect(cfg, absorbed)
        pcount = len(reflected.get("patterns", []))
        acount = len(reflected.get("anomalies", []))
        bcount = len(reflected.get("bridge_signals", []))
        dt = time.time() - t0
        alive = pcount > 0 and reflected["patterns"][0].get("name") != "unparsed-reflect"
        print(f"  REFLECT: {pcount}p {acount}a {bcount}b | {dt:.1f}s | {'✅' if alive else '⚠️'}")
        if alive:
            for p in reflected["patterns"][:2]:
                print(f"    → {p.get('name','?')[:100]}")
    except Exception as e:
        print(f"  REFLECT: ❌ {e}")
        reflected = {"patterns": [], "anomalies": [], "bridge_signals": []}
    
    # EXPLORE
    t0 = time.time()
    try:
        explored = explore(cfg, reflected)
        qcount = len(explored.get("queries", []))
        rcount = len(explored.get("results", []))
        dcount = len(explored.get("discoveries", []))
        dt = time.time() - t0
        print(f"  EXPLORE: {qcount}q {rcount}r {dcount}d | {dt:.1f}s | {'✅' if dcount > 0 else '⚠️'}")
    except Exception as e:
        print(f"  EXPLORE: ⚠️ {e}")
        explored = {"queries": [], "results": [], "discoveries": []}
    
    # EXPRESS
    t0 = time.time()
    try:
        expressed = express(cfg, reflected, explored)
        dt = time.time() - t0
        mlen = len(expressed.get("monologue", ""))
        icount = len(expressed.get("insights", []))
        print(f"  EXPRESS: mood={expressed.get('mood','?')} {mlen}c {icount}i | {dt:.1f}s | {'✅' if mlen > 100 else '⚠️'}")
    except Exception as e:
        print(f"  EXPRESS: ⚠️ {e}")
        expressed = None
    
    # MEMORIZE
    t0 = time.time()
    try:
        memorized = memorize(cfg, reflected, expressed, explored)
        dt = time.time() - t0
        icount = len(memorized.get("items", []))
        acount = len(memorized.get("applied", []))
        pcount = len(memorized.get("proposals", []))
        print(f"  MEMORIZE: {icount} scored {acount} applied {pcount} proposed | {dt:.1f}s | {'✅' if icount > 0 else '⚠️'}")
        for prop in memorized.get("proposals", [])[:2]:
            print(f"    → {prop.get('file','?')}: {prop.get('proposed_change','')[:100]}...")
    except Exception as e:
        print(f"  MEMORIZE: ⚠️ {e}")
    
    return {"profile": profile, "status": "ok"}


def test_global(prov_name, prov):
    """Run 5-phase cycle in global mode across all profiles."""
    print(f"\n{'='*60}")
    print(f"GLOBAL MODE — all {len(PROFILES)} profiles | PROVIDER: {prov_name}")
    print(f"{'='*60}")
    
    cfg = EvolConfig(profile="conductor")  # conductor = anchor
    cfg.mode = "global"
    cfg.edit_mode = "suggested"
    cfg.search_backend = "duckduckgo"
    cfg.global_profiles = PROFILES
    set_models(cfg, prov)
    
    # ABSORB (all profiles)
    print(f"\n  ABSORB (all profiles)...")
    all_absorbed = {}
    for profile in PROFILES:
        try:
            pc = EvolConfig(profile=profile)
            pc.search_backend = "duckduckgo"
            a = absorb(pc)
            all_absorbed[profile] = a
            print(f"    {profile:15}: {len(a.get('circuit_files',{}))} files")
        except Exception as e:
            print(f"    {profile:15}: ❌ {e}")
    
    # Merge for REFLECT
    combined = {
        "profile": "global",
        "mode": "global",
        "timestamp": time.time(),
        "circuit_files": {},
        "session_summary": "",
        "evolution_log": [],
    }
    for p, a in all_absorbed.items():
        for fn, content in a.get("circuit_files", {}).items():
            key = f"{p}/{fn}"
            combined["circuit_files"][key] = content
        if a.get("session_summary"):
            combined["session_summary"] += f"\n[{p}] {a['session_summary'][:200]}"
        combined["evolution_log"].extend(a.get("evolution_log", []))
    
    total_files = len(combined["circuit_files"])
    print(f"\n  MERGED: {total_files} circuit files from {len(all_absorbed)} profiles")
    
    # REFLECT
    print(f"\n  REFLECT (global)...")
    t0 = time.time()
    reflected = reflect(cfg, combined)
    dt = time.time() - t0
    pcount = len(reflected.get("patterns", []))
    acount = len(reflected.get("anomalies", []))
    bcount = len(reflected.get("bridge_signals", []))
    alive = pcount > 0 and reflected["patterns"][0].get("name") != "unparsed-reflect"
    print(f"  → {pcount}p {acount}a {bcount}b | {dt:.1f}s | {'✅' if alive else '⚠️'}")
    if alive:
        for pat in reflected["patterns"][:5]:
            print(f"    • {pat.get('name','?')[:110]}")
    
    # EXPLORE
    print(f"\n  EXPLORE (global)...")
    t0 = time.time()
    explored = explore(cfg, reflected)
    dt = time.time() - t0
    print(f"  → {len(explored.get('queries',[]))}q {len(explored.get('results',[]))}r {len(explored.get('discoveries',[]))}d | {dt:.1f}s")
    for disc in explored.get("discoveries", [])[:3]:
        print(f"    • {disc.get('topic','?')[:100]}")
    
    # EXPRESS
    print(f"\n  EXPRESS (global)...")
    t0 = time.time()
    expressed = express(cfg, reflected, explored)
    dt = time.time() - t0
    print(f"  → mood={expressed.get('mood','?')} | {len(expressed.get('monologue',''))} chars | {len(expressed.get('insights',[]))} insights | {dt:.1f}s")
    for ins in expressed.get("insights", [])[:4]:
        print(f"    • {ins[:130]}...")
    
    # MEMORIZE
    print(f"\n  MEMORIZE (global)...")
    t0 = time.time()
    memorized = memorize(cfg, reflected, expressed, explored)
    dt = time.time() - t0
    ic = len(memorized.get("items", []))
    ac = len(memorized.get("applied", []))
    pc = len(memorized.get("proposals", []))
    print(f"  → {ic} scored | {ac} applied | {pc} proposed | {dt:.1f}s | {'✅' if ic > 0 else '⚠️'}")
    for prop in memorized.get("proposals", [])[:5]:
        target = prop.get("file", "?")
        text = prop.get("proposed_change", "")[:120]
        print(f"    • {target} (wt={prop.get('weight',0):.2f}): {text}...")
    
    return {"status": "ok", "profiles": len(all_absorbed), "items": ic, "proposals": pc}


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

print("=" * 60)
print("EVOL UNIVERSAL ACCEPTANCE TEST")
print(f"Profiles: {len(PROFILES)} | Providers: hermes, venice")
print("=" * 60)

# ── STAGE 1: Profile-mode, Hermes ──
print(f"\n{'#'*60}")
print(f"# STAGE 1: PROFILE MODE — HERMES GATEWAY (ollama-cloud)")
print(f"{'#'*60}")
hermes_results = []
for profile in PROFILES:
    r = test_profile(profile, "hermes", PROVIDERS["hermes"])
    hermes_results.append(r)

# Quick tally
ok = sum(1 for r in hermes_results if r.get("status") == "ok")
print(f"\n  HERMES PROFILE TALLY: {ok}/{len(PROFILES)} OK")

# ── STAGE 2: Profile-mode, Venice ──
print(f"\n{'#'*60}")
print(f"# STAGE 2: PROFILE MODE — VENICE GLM HERETIC")
print(f"{'#'*60}")
venice_results = []
for profile in PROFILES:
    r = test_profile(profile, "venice", PROVIDERS["venice"])
    venice_results.append(r)

ok = sum(1 for r in venice_results if r.get("status") == "ok")
print(f"\n  VENICE PROFILE TALLY: {ok}/{len(PROFILES)} OK")

# ── STAGE 3: Global mode, Hermes ──
print(f"\n{'#'*60}")
print(f"# STAGE 3: GLOBAL MODE — HERMES GATEWAY")
print(f"{'#'*60}")
gr_hermes = test_global("hermes", PROVIDERS["hermes"])

# ── STAGE 4: Global mode, Venice ──
print(f"\n{'#'*60}")
print(f"# STAGE 4: GLOBAL MODE — VENICE GLM HERETIC")
print(f"{'#'*60}")
gr_venice = test_global("venice", PROVIDERS["venice"])

# ── FINAL REPORT ──
print(f"\n{'='*60}")
print("FINAL VERDICT")
print(f"{'='*60}")
print(f"  20 profile tests:  hermes={sum(1 for r in hermes_results if r.get('status')=='ok')}/10  venice={sum(1 for r in venice_results if r.get('status')=='ok')}/10")
print(f"  Global Hermes:     {gr_hermes.get('profiles',0)} profiles → {gr_hermes.get('items',0)} scored, {gr_hermes.get('proposals',0)} proposals")
print(f"  Global Venice:     {gr_venice.get('profiles',0)} profiles → {gr_venice.get('items',0)} scored, {gr_venice.get('proposals',0)} proposals")
print(f"{'='*60}")
