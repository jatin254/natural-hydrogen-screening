"""Classify GSI rock names into the classes in configs/lithology_classes.yaml.

classify("SANDSTONE, SHALE WITH COAL") ->
    {"main": "SST", "present": ["SST", "SH", "COAL"], "parts": [...], "unmatched": []}
"""
import re
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RULES = ROOT / "configs" / "lithology_classes.yaml"

# separators between rock names inside one GSI description
SPLIT = re.compile(r"[,/&;+±()\[\]]|\.(?=\s)|\bAND\b|\bWITH\b|\bOR\b|\bIN\b|\bINTER\w*\b|\bASSOCIATED\b|\bMINOR\b|\bOCCASS?IONAL\b"
                   r"|\bBANDS?\b|\bLENSES\b|\bLENS\b|\bVEINS? OF\b|\bTO\b")


@lru_cache(maxsize=1)
def load_rules(path=RULES):
    cfg = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rules = []
    for c in cfg["classes"]:
        rx = re.compile(r"(?<![A-Z])(?:" + "|".join(c["patterns"]) + r")(?![A-Z])")
        rules.append((c["code"], rx))
    return rules


def part_class(part, rules=None):
    for code, rx in rules or load_rules():
        if rx.search(part):
            return code
    return None


def classify(name):
    text = re.sub(r"\s+", " ", str(name or "").upper().replace("-", " - ")).replace(" - ", "-")
    text = text.replace("UNDIFF.", "UNDIFFERENTIATED ")
    rules = load_rules()
    parts = [p.strip(" .-") for p in SPLIT.split(text) if p and p.strip(" .-")]
    present, unmatched, labelled = [], [], []
    for p in parts:
        c = part_class(p, rules)
        labelled.append((p, c))
        if c is None:
            unmatched.append(p)
        elif c not in present:
            present.append(c)
    if not present and text.strip():
        c = part_class(text, rules)      # whole-name fallback for names the split broke up
        if c:
            present = [c]
    main = present[0] if present else "UNK"
    return {"main": main, "present": present, "parts": labelled, "unmatched": unmatched}
