"""EVOL acceptance test — focused 4-scenario suite."""
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

RESULTS = []

def run_one(profile, prov_name, prov, search="duckduckgo"):
    """Full 5-phase cycle on one profile/provider combo."""
    label = f"{profile}/{prov_name}"
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    r = {"label": label, "profile": profile, "provider": prov_name}
    t_start = time.time()

    try:
        cfg = EvolConfig(profile=profile)
    except Exception as e:
        r["error"] = str(e); RESULTS.append(r); return r

    cfg.edit_mode = "suggested"
    cfg.search_backend = search
    for p in cfg.phase_models:
        cfg.phase_models[p].provider = prov["provider"]
        cfg.phase_models[p].model = prov["model"]
        cfg.phase_models[p].max_tokens = 4096 if p == "explore" else 8192

    # ABSORB
    absorbed = absorb(cfg)
    r["absorb_files"] = len(absorbed.get("circuit_files", {}))

    # REFLECT
    t0 = time.time()
    reflected = reflect(cfg, absorbed)
    r["reflect_s"] = round(time.time()-t0, 1)
    r["reflect_patterns"] = len(reflected.get("patterns",[]))
    r["reflect_anomalies"] = len(reflected.get("anomalies",[]))
    r["reflect_bridge"] = len(reflected.get("bridge_signals",[]))
    alive = r["reflect_patterns"] > 0 and reflected["patterns"][0].get("name") != "unparsed-reflect"
    r["reflect_alive"] = alive
    print(f"  REFLECT: {r['reflect_patterns']}p {r['reflect_anomalies']}a {r['reflect_bridge']}b ({r['reflect_s']}s) {'✅' if alive else '❌'}")

    # EXPLORE
    t0 = time.time()
    explored = explore(cfg, reflected)
    r["explore_s"] = round(time.time()-t0, 1)
    r["explore_queries"] = len(explored.get("queries",[]))
    r["explore_results"] = len(explored.get("results",[]))
    r["explore_discoveries"] = len(explored.get("discoveries",[]))
    print(f"  EXPLORE: {r['explore_queries']}q {r['explore_results']}r {r['explore_discoveries']}d ({r['explore_s']}s)")

    # EXPRESS
    t0 = time.time()
    expressed = express(cfg, reflected, explored)
    r["express_s"] = round(time.time()-t0, 1)
    r["express_chars"] = len(expressed.get("monologue",""))
    r["express_insights"] = len(expressed.get("insights",[]))
    print(f"  EXPRESS: mood={expressed.get('mood','?')} {r['express_chars']}c {r['express_insights']}i ({r['express_s']}s)")

    # MEMORIZE
    t0 = time.time()
    memorized = memorize(cfg, reflected, expressed, explored)
    r["memo_s"] = round(time.time()-t0, 1)
    r["memo_scored"] = len(memorized.get("items",[]))
    r["memo_applied"] = len(memorized.get("applied",[]))
    r["memo_proposed"] = len(memorized.get("proposals",[]))
    print(f"  MEMORIZE: {r['memo_scored']} scored {r['memo_applied']} applied {r['memo_proposed']} proposed ({r['memo_s']}s)")

    r["total_s"] = round(time.time()-t_start, 1)
    print(f"  TOTAL: {r['total_s']}s")
    RESULTS.append(r)
    return r


def run_global(prov_name, prov):
    """Global mode: absorb all profiles, unified cycle."""
    label = f"GLOBAL/{prov_name}"
    print(f"\n{'='*60}\n{label}\n{'='*60}")
    r = {"label": label, "profile": "global", "provider": prov_name}
    t_start = time.time()

    cfg = EvolConfig(profile="conductor")
    cfg.mode = "global"
    cfg.edit_mode = "suggested"
    cfg.search_backend = "duckduckgo"
    cfg.global_profiles = ["analyst","architect","coder","conductor","operative",
                           "orchestrator","researcher","reviewer","shadow","valmet"]
    for p in cfg.phase_models:
        cfg.phase_models[p].provider = prov["provider"]
        cfg.phase_models[p].model = prov["model"]
        cfg.phase_models[p].max_tokens = 4096 if p == "explore" else 8192

    # Absorb all profiles
    all_abs = {}
    for prof in cfg.global_profiles:
        try:
            pc = EvolConfig(profile=prof)
            all_abs[prof] = absorb(pc)
        except Exception as e:
            all_abs[prof] = {"error": str(e)}

    r["absorb_profiles"] = len(all_abs)
    r["absorb_total_files"] = sum(len(a.get("circuit_files",{})) for a in all_abs.values())

    # Merge
    combined = {"profile":"global","mode":"global","timestamp":time.time(),
                "circuit_files":{},"session_summary":"","evolution_log":[]}
    for pn, a in all_abs.items():
        for fn, c in a.get("circuit_files",{}).items():
            combined["circuit_files"][f"{pn}/{fn}"] = c

    # REFLECT
    t0 = time.time()
    reflected = reflect(cfg, combined)
    r["reflect_s"] = round(time.time()-t0, 1)
    r["reflect_patterns"] = len(reflected.get("patterns",[]))
    r["reflect_anomalies"] = len(reflected.get("anomalies",[]))
    r["reflect_bridge"] = len(reflected.get("bridge_signals",[]))
    alive = r["reflect_patterns"] > 0 and reflected["patterns"][0].get("name") != "unparsed-reflect"
    r["reflect_alive"] = alive
    print(f"  REFLECT: {r['reflect_patterns']}p {r['reflect_anomalies']}a {r['reflect_bridge']}b ({r['reflect_s']}s) {'✅' if alive else '❌'}")

    # EXPLORE
    t0 = time.time()
    explored = explore(cfg, reflected)
    r["explore_s"] = round(time.time()-t0, 1)
    r["explore_queries"] = len(explored.get("queries",[]))
    r["explore_results"] = len(explored.get("results",[]))
    r["explore_discoveries"] = len(explored.get("discoveries",[]))
    print(f"  EXPLORE: {r['explore_queries']}q {r['explore_results']}r {r['explore_discoveries']}d ({r['explore_s']}s)")

    # EXPRESS
    t0 = time.time()
    expressed = express(cfg, reflected, explored)
    r["express_s"] = round(time.time()-t0, 1)
    r["express_chars"] = len(expressed.get("monologue",""))
    r["express_insights"] = len(expressed.get("insights",[]))
    print(f"  EXPRESS: mood={expressed.get('mood','?')} {r['express_chars']}c {r['express_insights']}i ({r['express_s']}s)")

    # MEMORIZE
    t0 = time.time()
    memorized = memorize(cfg, reflected, expressed, explored)
    r["memo_s"] = round(time.time()-t0, 1)
    r["memo_scored"] = len(memorized.get("items",[]))
    r["memo_applied"] = len(memorized.get("applied",[]))
    r["memo_proposed"] = len(memorized.get("proposals",[]))
    print(f"  MEMORIZE: {r['memo_scored']} scored {r['memo_applied']} applied {r['memo_proposed']} proposed ({r['memo_s']}s)")

    r["total_s"] = round(time.time()-t_start, 1)
    print(f"  TOTAL: {r['total_s']}s")
    RESULTS.append(r)
    return r


# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

HERMES = {"provider": "hermes", "model": "conductor"}
VENICE = {"provider": "venice", "model": "olafangensan-glm-4.7-flash-heretic"}

print("EVOL ACCEPTANCE SUITE — 4 scenarios\n")

# 1. Conductor via Hermes Gateway
run_one("conductor", "hermes", HERMES)

# 2. Conductor via Venice GLM Heretic
run_one("conductor", "venice", VENICE)

# 3. Shadow via Venice (dark profile, different perspective)
run_one("shadow", "venice", VENICE)

# 4. Global mode via Hermes (all 10 profiles)
run_global("hermes", HERMES)

# ── REPORT ──
print("\n" + "="*60)
print("RESULTS SUMMARY")
print("="*60)
for r in RESULTS:
    print(f"\n{r['label']} — {r['total_s']}s")
    print(f"  REFLECT:  {r.get('reflect_patterns',0)}p {r.get('reflect_anomalies',0)}a {r.get('reflect_bridge',0)}b {'✅' if r.get('reflect_alive') else '❌'}")
    print(f"  EXPLORE:  {r.get('explore_queries',0)}q {r.get('explore_results',0)}r {r.get('explore_discoveries',0)}d")
    print(f"  EXPRESS:  {r.get('express_chars',0)}c {r.get('express_insights',0)}i")
    print(f"  MEMORIZE: {r.get('memo_scored',0)} scored {r.get('memo_applied',0)} applied {r.get('memo_proposed',0)} proposed")

# Save to /tmp for easy reading
with open('/tmp/evol_test_suite.json', 'w') as f:
    json.dump(RESULTS, f, indent=2)
print(f"\nResults saved to /tmp/evol_test_suite.json")
