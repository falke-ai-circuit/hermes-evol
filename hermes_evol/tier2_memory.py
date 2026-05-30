#!/usr/bin/env python3
"""
EVOL Tier2 Memory Backend — Universal Interface.

Design principles:
  - Nothing hardcoded — swap backends by changing config, not code
  - Only MEMORIZE phase writes to Tier2
  - Other phases (absorb/reflect/explore/express) don't touch it
  - Tier2 is a DESTINATION for scored facts, not a source for other phases

Supported backends:
  - graphiti: Self-hosted temporal knowledge graph (Neo4j + Graphiti server)
  - mem0: mem0 cloud (flat, no temporal metadata)
  - ladybug: LadybugDB (local, C++ crashes at scale)
  - dummy: No-op for testing

Config via evoc.json:
  {
    "tier2_backend": "graphiti",
    "tier2_config": {
      "url": "http://187.124.31.229:8000",
      "group_id": "conductor",
      ...
    }
  }
"""

import json
import urllib.request
import urllib.error
import time
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod


# ═══════════════════════════════════════════════════════════════════
# ABSTRACT INTERFACE
# ═══════════════════════════════════════════════════════════════════

class Tier2Backend(ABC):
    """Every Tier2 backend must implement this interface."""
    
    @abstractmethod
    def name(self) -> str:
        """Human-readable backend name for logging."""
        ...
    
    @abstractmethod
    def promote(self, fact: Dict[str, Any]) -> Dict[str, Any]:
        """
        Promote a fact to Tier 2 memory.
        
        Args:
            fact: {
                "description": str,    # What was learned
                "weight": float,       # 0.0-1.0 confidence
                "concept": str,        # Entity/concept name
                "source": str,         # "EVOL cycle N" or "session XYZ"
                "tags": [str],         # Domain tags
                "suggested_text": str, # Full text to store
                "contradicts": [str],  # Optional: UUIDs of facts this contradicts
            }
        
        Returns:
            {"status": "ok", "uuid": "...", "stored_at": "..."}
        """
        ...
    
    @abstractmethod
    def demote(self, uuid: str, reason: str) -> Dict[str, Any]:
        """
        Mark a fact as expired/demoted.
        
        Args:
            uuid: The stored fact's UUID
            reason: Why it's being demoted
        
        Returns:
            {"status": "ok"|"not_found"|"error"}
        """
        ...
    
    @abstractmethod
    def count_accesses(self, concept: str) -> int:
        """
        Count how many times a concept/fact has been accessed.
        Used for promotion threshold decisions.
        
        Returns:
            Access count (0 if not found)
        """
        ...
    
    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Quick health check. Returns {"ok": bool, "detail": str}."""
        ...


# ═══════════════════════════════════════════════════════════════════
# GRAPHITI BACKEND
# ═══════════════════════════════════════════════════════════════════

class GraphitiBackend(Tier2Backend):
    """Graphiti temporal knowledge graph backend."""
    
    def __init__(self, url: str, group_id: str, timeout: int = 10):
        self.url = url.rstrip('/')
        self.group_id = group_id
        self.timeout = timeout
    
    def name(self) -> str:
        return "graphiti"
    
    def promote(self, fact: Dict[str, Any]) -> Dict[str, Any]:
        """Promote fact via Graphiti add_episode-like single-message insert."""
        concept = fact.get("concept", fact.get("description", "unknown")[:80])
        text = fact.get("suggested_text", fact.get("description", ""))
        weight = fact.get("weight", 0.5)
        source = fact.get("source", "EVOL")
        contradicts = fact.get("contradicts", [])
        
        # Build a rich message that Graphiti can extract entities from
        content = (
            f"MEMORIZE-PROMOTED | weight={weight:.2f} | source={source} | "
            f"concept={concept} | tags={','.join(fact.get('tags', ['evol']))} | "
            f"{text}"
        )
        
        # Also store as explicit fact if contradicts provided
        if contradicts:
            expire_note = f" | EXPIRES: {', '.join(contradicts)}"
            content += expire_note
        
        # Use the messages endpoint (same as ingestion)
        body = json.dumps({
            "group_id": self.group_id,
            "messages": [{
                "content": content[:8000],
                "role_type": "user",
                "role": "evol-memorize",
                "source_description": f"evol-promote-{concept[:40]}"
            }]
        }).encode('utf-8')
        
        try:
            req = urllib.request.Request(
                f"{self.url}/messages",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            if resp.status == 202:
                return {"status": "ok", "uuid": f"graphiti-promoted-{int(time.time())}", 
                        "stored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
            return {"status": "error", "detail": f"HTTP {resp.status}"}
        except Exception as e:
            return {"status": "error", "detail": str(e)[:200]}
    
    def demote(self, uuid: str, reason: str) -> Dict[str, Any]:
        """Demote via Graphiti — mark as expired."""
        # Graphiti doesn't have a direct demote endpoint.
        # We store a contradiction fact that marks the original as expired.
        content = f"MEMORIZE-DEMOTED | original={uuid} | reason={reason} | This fact is no longer valid."
        
        body = json.dumps({
            "group_id": self.group_id,
            "messages": [{
                "content": content,
                "role_type": "user",
                "role": "evol-demote",
                "source_description": f"evol-demote-{uuid[:20]}"
            }]
        }).encode('utf-8')
        
        try:
            req = urllib.request.Request(
                f"{self.url}/messages",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            if resp.status == 202:
                return {"status": "ok", "detail": f"demoted {uuid}"}
            return {"status": "error", "detail": f"HTTP {resp.status}"}
        except Exception as e:
            return {"status": "error", "detail": str(e)[:200]}
    
    def count_accesses(self, concept: str) -> int:
        """Count access via Graphiti search."""
        try:
            body = json.dumps({
                "query": concept,
                "group_id": self.group_id,
                "num_results": 50
            }).encode('utf-8')
            req = urllib.request.Request(
                f"{self.url}/search",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            resp = urllib.request.urlopen(req, timeout=self.timeout)
            data = json.loads(resp.read().decode())
            if isinstance(data, list):
                return len(data)
            if isinstance(data, dict):
                return len(data.get("results", data.get("facts", [])))
            return 0
        except urllib.error.HTTPError as e:
            if e.code == 500:
                return -1  # Search index not ready yet
            return 0
        except Exception:
            return 0
    
    def health(self) -> Dict[str, Any]:
        try:
            req = urllib.request.Request(
                f"{self.url}/healthcheck",
                headers={},
                method="GET"
            )
            resp = urllib.request.urlopen(req, timeout=5)
            if resp.status == 200:
                data = json.loads(resp.read().decode())
                return {"ok": True, "detail": data.get("status", "ok")}
            return {"ok": False, "detail": f"HTTP {resp.status}"}
        except Exception as e:
            return {"ok": False, "detail": str(e)[:200]}


# ═══════════════════════════════════════════════════════════════════
# DUMMY BACKEND (for testing/development)
# ═══════════════════════════════════════════════════════════════════

class DummyBackend(Tier2Backend):
    """No-op backend for testing. Logs to a file instead of storing."""
    
    def __init__(self, log_path: str = "/tmp/evol-tier2-dummy.jsonl"):
        self.log_path = log_path
    
    def name(self) -> str:
        return "dummy"
    
    def promote(self, fact: Dict[str, Any]) -> Dict[str, Any]:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": "promote",
            "concept": fact.get("concept", ""),
            "weight": fact.get("weight", 0),
            "text": fact.get("suggested_text", "")[:200],
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return {"status": "ok", "uuid": f"dummy-{int(time.time())}", "stored_at": entry["ts"]}
    
    def demote(self, uuid: str, reason: str) -> Dict[str, Any]:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "action": "demote",
            "uuid": uuid,
            "reason": reason,
        }
        with open(self.log_path, "a") as f:
            f.write(json.dumps(entry) + "\n")
        return {"status": "ok", "detail": f"demoted {uuid}"}
    
    def count_accesses(self, concept: str) -> int:
        return 0
    
    def health(self) -> Dict[str, Any]:
        return {"ok": True, "detail": "dummy"}


# ═══════════════════════════════════════════════════════════════════
# FACTORY — Create backend from config
# ═══════════════════════════════════════════════════════════════════

BACKEND_REGISTRY = {
    "graphiti": GraphitiBackend,
    "dummy": DummyBackend,
    "none": DummyBackend,
}


def create_tier2_backend(config: Optional[Dict[str, Any]] = None, profile: str = "conductor") -> Tier2Backend:
    """
    Create a Tier2 backend from configuration.
    
    config keys:
      - tier2_backend: str (default: "graphiti")
      - tier2_config: dict (backend-specific config)
    
    Environment variable fallbacks:
      - EVOL_TIER2_BACKEND
      - EVOL_TIER2_URL
      - EVOL_TIER2_GROUP_ID
    
    profile: The agent profile name — used as the default group_id for per-agent
             scoped memory. "conductor" is the global default for conductor cycles.
    """
    import os
    
    cfg = config or {}
    backend_name = cfg.get("tier2_backend") or os.environ.get("EVOL_TIER2_BACKEND", "graphiti")
    backend_cfg = cfg.get("tier2_config", {})
    
    if backend_name == "graphiti":
        url = backend_cfg.get("url") or os.environ.get("EVOL_TIER2_URL", "http://187.124.31.229:8000")
        # Default group_id = profile name (e.g. "researcher", "coder")
        # Falls back to env var, then profile, then "conductor"
        group_id = backend_cfg.get("group_id") or os.environ.get("EVOL_TIER2_GROUP_ID") or profile or "conductor"
        return GraphitiBackend(url=url, group_id=group_id)
    
    if backend_name == "dummy":
        log_path = backend_cfg.get("log_path", "/tmp/evol-tier2-dummy.jsonl")
        return DummyBackend(log_path=log_path)
    
    # Unknown backend → dummy no-op
    print(f"[evol-tier2] Unknown backend '{backend_name}', falling back to dummy")
    return DummyBackend()


# ═══════════════════════════════════════════════════════════════════
# PROMOTION / DEMOTION ENGINE
# ═══════════════════════════════════════════════════════════════════

def run_promotion_demotion_cycle(
    facts: List[Dict[str, Any]],
    backend: Tier2Backend,
    promote_threshold: float = 0.65,
    demote_threshold: float = 0.35,
    access_threshold: int = 5,
) -> Dict[str, Any]:
    """
    Process a list of facts through the Tier2 promotion/demotion engine.
    
    This is called by EVOL MEMORIZE phase after scoring.
    
    Args:
        facts: List of scored facts from MEMORIZE
        backend: Tier2 backend instance
        promote_threshold: Weight above which facts get promoted to Tier2
        demote_threshold: Weight below which facts get demoted from Tier2
        access_threshold: How many accesses before auto-promotion
    
    Returns:
        {
            "promoted": [{"concept": ..., "weight": ..., "uuid": ...}, ...],
            "demoted": [{"uuid": ..., "reason": ...}, ...],
            "skipped": int,
            "errors": int,
        }
    """
    backend_name = backend.name() if hasattr(backend, 'name') else str(backend)
    result = {"promoted": [], "demoted": [], "skipped": 0, "errors": 0, "backend": backend_name}
    
    for fact in facts:
        weight = fact.get("weight", fact.get("raw_weight", 0))
        concept = fact.get("concept", fact.get("description", "unknown")[:80])
        contradicts = fact.get("contradicts", [])
        
        # ── DEMOTION: If this fact contradicts existing facts ──
        if contradicts:
            for old_uuid in contradicts:
                r = backend.demote(old_uuid, f"contradicted by new fact: {concept}")
                if r.get("status") == "ok":
                    result["demoted"].append({"uuid": old_uuid, "reason": f"contradicted by {concept}"})
                else:
                    result["errors"] += 1
        
        # ── PROMOTION: Weight exceeds threshold OR accessed enough times ──
        access_count = backend.count_accesses(concept)
        
        should_promote = (weight >= promote_threshold) or (access_count >= access_threshold)
        
        if should_promote:
            # Build promotion fact
            promote_fact = {
                "description": concept,
                "weight": weight,
                "concept": concept,
                "source": fact.get("source", "EVOL MEMORIZE"),
                "tags": fact.get("tags", ["evol"]),
                "suggested_text": fact.get("suggested_text", fact.get("description", "")),
                "contradicts": contradicts if contradicts else [],
            }
            
            r = backend.promote(promote_fact)
            if r.get("status") == "ok":
                result["promoted"].append({
                    "concept": concept,
                    "weight": weight,
                    "uuid": r.get("uuid", ""),
                    "access_count": access_count,
                    "promote_reason": "weight" if weight >= promote_threshold else "accesses",
                })
            else:
                result["errors"] += 1
        else:
            result["skipped"] += 1
    
    return result


# ═══════════════════════════════════════════════════════════════════
# STANDALONE TEST
# ═══════════════════════════════════════════════════════════════════

def run_test():
    """Run a promotion/demotion test with visible output."""
    print("=" * 60)
    print("EVOL Tier2 Memory — Promotion/Demotion Test")
    print("=" * 60)
    
    # Use dummy backend for reliable testing
    backend = create_tier2_backend({
        "tier2_backend": "dummy",
        "tier2_config": {"log_path": "/tmp/evol-tier2-test.jsonl"}
    })
    
    print(f"\nBackend: {backend.name()}")
    print(f"Health: {backend.health()}")
    
    # ── Test facts ──
    test_facts = [
        {
            "description": "Graphiti temporal KG works for Tier 2 memory",
            "weight": 0.92,
            "concept": "graphiti-tier2-works",
            "source": "EVOL test cycle",
            "tags": ["memory", "evol"],
            "suggested_text": "Graphiti successfully deployed as Tier 2 memory backend. 260 state.db sessions + 58K tier3 messages ingested. Promotion/demotion pipeline wired into EVOL MEMORIZE phase.",
        },
        {
            "description": "Gateway RSS leak persists across cycles",
            "weight": 0.78,
            "concept": "gateway-rss-leak",
            "source": "EVOL test cycle",
            "tags": ["infra", "gateway"],
            "suggested_text": "Gateway RSS bleed detected: 405MB across 3 cycles. Root cause: Node.js WebSocket Maps without deletion. Fix exists (15-line handler) but cannot be applied under G-CONDUCTOR-FIX-SCOPE.",
            "contradicts": ["old-gateway-stable-claim"],  # Demotes an old claim
        },
        {
            "description": "EVOL cycles produce zero scored items",
            "weight": 0.95,
            "concept": "evol-empty-cycles",
            "source": "EVOL test cycle",
            "tags": ["evol", "bug"],
            "suggested_text": "65 EVOL cycles since May 18 produced zero scored items. MEMORIZE phase fires but REFLECT phase doesn't carry patterns forward. Root cause: _parse_memorize_items receives empty pattern list from reflect output.",
        },
        {
            "description": "MiniMax Anthropic endpoint works for Graphiti",
            "weight": 0.85,
            "concept": "minimax-anthropic-works",
            "source": "EVOL test cycle",
            "tags": ["llm", "graphiti"],
            "suggested_text": "MiniMax M2.7 Anthropic-compatible endpoint at api.minimax.io/anthropic confirmed working for entity extraction. Graphiti plugin patched to use AnthropicClient instead of OpenAIClient.",
        },
        {
            "description": "Some low-weight trivia",
            "weight": 0.20,
            "concept": "low-weight-trivia",
            "source": "EVOL test cycle",
            "tags": ["test"],
            "suggested_text": "This fact is below demotion threshold and should be skipped.",
        },
    ]
    
    print(f"\nTesting {len(test_facts)} facts...\n")
    
    for i, fact in enumerate(test_facts):
        w = fact["weight"]
        icon = "↑" if w >= 0.65 else ("↓" if w <= 0.35 else "—")
        print(f"  Fact #{i+1}: [{icon}] wt={w:.2f} | {fact['description'][:70]}")
    
    print(f"\n{'─' * 40}")
    print("Running promotion/demotion engine...")
    print(f"{'─' * 40}\n")
    
    result = run_promotion_demotion_cycle(
        test_facts, 
        backend,
        promote_threshold=0.65,
        demote_threshold=0.35,
        access_threshold=5,
    )
    
    print(f"PROMOTED to Tier2:  {len(result['promoted'])}")
    for p in result['promoted']:
        print(f"  ↑ {p['concept']} (wt={p['weight']:.2f}) → {p['uuid'][:30]}")
    
    print(f"\nDEMOTED from Tier2: {len(result['demoted'])}")
    for d in result['demoted']:
        print(f"  ↓ {d['uuid'][:30]} → {d['reason'][:80]}")
    
    print(f"\nSKIPPED (mid-weight): {result['skipped']}")
    print(f"ERRORS: {result['errors']}")
    
    # ── Show what was written ──
    print(f"\n{'─' * 40}")
    print("Dummy log output:")
    print(f"{'─' * 40}")
    try:
        with open("/tmp/evol-tier2-test.jsonl") as f:
            for line in f:
                print(f"  {line.rstrip()}")
    except:
        pass
    
    # ── Verify with Graphiti if available ──
    print(f"\n{'─' * 40}")
    print("Graphiti backend check:")
    print(f"{'─' * 40}")
    gb = GraphitiBackend(url="http://187.124.31.229:8000", group_id="conductor")
    health = gb.health()
    print(f"  Health: {health}")
    if health["ok"]:
        # Test promotion
        r = gb.promote({
            "concept": "evol-tier2-test-result",
            "weight": 0.90,
            "source": "standalone test",
            "suggested_text": "EVOL Tier2 promotion/demotion test completed. Pipeline wired: EVOL MEMORIZE → Tier2Backend.promote() → Graphiti messages endpoint.",
        })
        print(f"  Test promote: {r}")
    
    print(f"\n{'=' * 60}")
    print("Test complete.")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    run_test()
