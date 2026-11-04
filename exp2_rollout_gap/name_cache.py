"""Shared cache of concept names (CLAUDE.md: never pay to name a concept twice from the same kind of text; G63).

notes/name_cache.json maps concept id -> list of entries, each with the name and where it came from:
    {"name", "text": "dolma" | "pile" | "rollout", "windows", "model" (generator, rollout names only), "source"}
build() fills it from the paid runs so far; add() records new names as they arrive. Names only, no window text.
"""
import json
from pathlib import Path

import settings  # first: puts Exp 1 on the path and sets HF_HOME
import config

PATH = Path(__file__).resolve().parent.parent / "notes" / "name_cache.json"
DOLMA_ORDER = ["T1 all sources", "T1 common_crawl", "T2 all sources", "V all sources"]  # G63


def _entry(name, text, windows, source, model=None):
    return {"name": name, "text": text, "windows": windows, "model": model, "source": source}


def build():
    """Names already paid for: Exp 1 F run and pilot, Exp 2 G47."""
    cache = {}

    def put(c, entry):
        if entry["name"]:
            cache.setdefault(str(c), []).append(entry)

    labels = config.DATA / "full" / "labels"
    for c, v in json.loads((labels / "faith" / "names.json").read_text()).items():
        put(c, _entry(v.get("dolma"), "dolma", "T1 common_crawl", "exp1 F run (faith)"))
        put(c, _entry(v.get("pile"), "pile", "Pile-CC", "exp1 F run (faith)"))
    for c, v in json.loads((labels / "pilot" / "names.json").read_text()).items():
        for subset, o in v.items():
            if o.get("status") == "ok":
                put(c, _entry(o.get("explanation"), "dolma", f"{subset} all sources", "exp1 pilot (N11)"))
    moved = settings.DATA / "full_post"
    set_of = {str(v["concept"]): v["set"] for v in json.loads((moved / "moved" / "concepts.json").read_text())}
    for c, v in json.loads((moved / "labels" / "moved" / "names.json").read_text()).items():
        put(c, _entry(v.get("dolma"), "dolma", "V all sources", "exp2 moved (G47)"))
        put(c, _entry(v.get("rollout"), "rollout", f"rollouts {set_of[c]}", "exp2 moved (G47)", set_of[c]))
    PATH.write_text(json.dumps(cache, indent=0, ensure_ascii=False, sort_keys=True))
    return cache


def load():
    """The cache, built on first use."""
    return json.loads(PATH.read_text()) if PATH.exists() else build()


def add(entries):
    """entries: (concept, name, text, windows, source, model). Skips what is already there, so a rerun adds nothing."""
    cache = load()
    for c, name, text, windows, source, model in entries:
        have = cache.setdefault(str(c), [])
        if name and not any(e["name"] == name and e["source"] == source for e in have):
            have.append(_entry(name, text, windows, source, model))
    PATH.write_text(json.dumps(cache, indent=0, ensure_ascii=False, sort_keys=True))


def dolma(cache, c):
    """The Dolma entry to reuse for concept c (DOLMA_ORDER), or None."""
    mine = [e for e in cache.get(str(c), []) if e["text"] == "dolma"]
    return min(mine, key=lambda e: DOLMA_ORDER.index(e["windows"])) if mine else None


def rollout(cache, c, model):
    """A rollout name of concept c from this model's rollouts, or None."""
    return next((e for e in cache.get(str(c), []) if e["text"] == "rollout" and e["model"] == model), None)
