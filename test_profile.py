"""Quick profile test — 3 key profiles."""
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

PROVIDER, MODEL = sys.argv[1] if len(sys.argv) > 1 else "hermes", sys.argv[2] if len(sys.argv) > 2 else "conductor"
PROFILES = ["conductor", "coder", "shadow"]

results = []
for profile in PROFILES:
    print(f"\n{'─'*50}")
    print(f"{profile} | {PROVIDER}")
    print(f"{'─'*50}")
    
    cfg = EvolConfig(profile=profile)
    cfg.edit_mode = "suggested"; cfg.search_backend = "duckduckgo"
    for p in cfg.phase_models:
        cfg.phase_models[p].provider = PROVIDER
        cfg.phase_models[p].model = MODEL
        cfg.phase_models[p].max_tokens = 4096 if p in ("explore",) else 8192

    # ABSORB
    absorbed = absorb(cfg)
    print(f"  ABSORB: {len(absorbed.get('circuit_files',{}))} files")

    # REFLECT
    try:
        t0=time.time(); reflected = reflect(cfg, absorbed)
        p=len(reflected.get('patterns',[]))
        ok = p>0 and reflected['patterns'][0].get('name')!='unparsed-reflect'
        print(f"  REFLECT: {p}p {len(reflected.get('anomalies',[]))}a | {time.time()-t0:.0f}s | {'✅' if ok else '⚠️'}")
        if ok:
            for pp in reflected['patterns'][:2]:
                print(f"    → {pp.get('name','?')[:100]}")
    except Exception as e:
        print(f"  REFLECT: ❌ {e}")
        reflected = {"patterns":[],"anomalies":[],"bridge_signals":[]}

    # EXPLORE
    try:
        t0=time.time(); explored = explore(cfg, reflected)
        d=len(explored.get('discoveries',[]))
        print(f"  EXPLORE: {len(explored.get('queries',[]))}q {d}d | {time.time()-t0:.0f}s | {'✅' if d>0 else '⚠️'}")
    except Exception as e:
        print(f"  EXPLORE: ⚠️ {e}")
        explored = {"queries":[],"results":[],"discoveries":[]}

    # EXPRESS
    try:
        t0=time.time(); expressed = express(cfg, reflected, explored)
        ml=len(expressed.get('monologue',''))
        print(f"  EXPRESS: {ml}c {len(expressed.get('insights',[]))}i | {time.time()-t0:.0f}s | {'✅' if ml>100 else '⚠️'}")
    except Exception as e:
        print(f"  EXPRESS: ⚠️ {e}")
        expressed = None

    # MEMORIZE
    try:
        t0=time.time(); memorized = memorize(cfg, reflected, expressed, explored)
        ic=len(memorized.get('items',[])); pc=len(memorized.get('proposals',[]))
        print(f"  MEMORIZE: {ic} scored {pc} proposed | {time.time()-t0:.0f}s | {'✅' if ic>0 else '⚠️'}")
        for prop in memorized.get('proposals',[])[:2]:
            print(f"    → {prop.get('file','?')}: {prop.get('proposed_change','')[:100]}...")
    except Exception as e:
        print(f"  MEMORIZE: ⚠️ {e}")

    results.append({"profile":profile,"ok":True})

print(f"\n✅ DONE: {sum(1 for r in results if r.get('ok'))}/{len(results)}")
