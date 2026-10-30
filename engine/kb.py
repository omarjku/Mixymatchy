"""Routing knowledge base (rulebook/kb/routing_knowledge_base.json) + slot map (rulebook/slot_map.json).

The KB is the medical team's single rulebook: slots, bundles, role aliases and modifiers, link rules,
drug classes, guideline register.  rulebook/slot_map.json (hand-written) says where each slot's facts
live in data/build/facts.json.  Neither file holds a patient fact.

Loaded and validated once at start-up.  Every ID that a bundle, role, rule, drug class, check, label
entry or validation row points to must exist; on any error the engine refuses to start and lists them
(KBError).  Problems that do not break routing (unconfirmed guidelines, free-text surfaces, codes
marked 'from memory') are warnings.

    python3 -m engine.kb          # print the validation report (exit 1 on errors)
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_PATH = os.environ.get("SECOND_LOOK_KB", os.path.join(ROOT, "rulebook", "kb", "routing_knowledge_base.json"))
SLOT_MAP_PATH = os.environ.get("SECOND_LOOK_SLOT_MAP", os.path.join(ROOT, "rulebook", "slot_map.json"))

PRIORITIES = ("P1", "P2", "P3")
# surfaces written as prose in the KB; they are handled in code, not looked up as slot IDs
SPECIAL_SURFACES = {"(all latest_value slots)": "R21 staleness, applied in fill",
                    "(the shown medication slot) + label panel": "R22 label panel, applied in screen"}
SELECTOR_KEYS = {"categories", "ips_sections", "icd10", "atc", "match", "match_all", "exclude", "status_in",
                 "assertion_in", "assertion_not_in", "role", "drug_classes", "attr_present", "side_required"}
COMPUTES = {"current_list", "latest_value", "trend", "event_history", "status_check", "checklist", "plan",
            "laterality_finding", "list_all", "age_sex", "med_changes"}


class KBError(RuntimeError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("knowledge base invalid (%d error(s)):\n  %s" % (len(self.errors), "\n  ".join(self.errors)))


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def source_ids(text):
    """'G02,G03,G07' / 'G18 (to source)' / 'L10 (production), L02-L09 (prototype)' -> ['G02', ...]."""
    out = []
    for a, b in re.findall(r"\b([GL]\d{2})(?:\s*-\s*([GL]\d{2}))?", text or ""):
        if b and a[0] == b[0]:
            out += ["%s%02d" % (a[0], n) for n in range(int(a[1:]), int(b[1:]) + 1)]
        else:
            out.append(a)
    return out


def expand_codes(codes):
    """['E10-E14', 'I65', 'H34.0'] -> prefixes ['E10', 'E11', ..., 'I65', 'H34.0']."""
    out = []
    for c in codes or []:
        c = c.strip().upper()
        m = re.match(r"^([A-Z])(\d{2})-([A-Z])?(\d{2})$", c)
        if m and (m.group(3) in (None, m.group(1))):
            out += ["%s%02d" % (m.group(1), n) for n in range(int(m.group(2)), int(m.group(4)) + 1)]
        elif c:
            out.append(c)
    return out


def _class_terms(dc):
    """Generic and brand names of one drug class -> lowercase match terms (no '(many brands)' placeholders)."""
    terms = []
    for field in ("generics", "brands_examples"):
        txt = dc.get(field) or ""
        if txt.strip().startswith("("):
            continue
        for part in txt.split(","):
            part = part.strip()
            for alt in [re.sub(r"\(.*?\)", "", part)] + re.findall(r"\((.*?)\)", part):
                alt = alt.strip().lower()
                if alt.startswith("all "):  # "all insulins and analogues" -> "insulin"
                    alt = alt.split()[1].rstrip("s")
                if alt and not alt.startswith("("):
                    terms.append(alt)
    return sorted(set(terms))


class KB:
    def __init__(self, data, slot_map):
        self.data, self.slot_map = data, slot_map
        self.version = data.get("version")
        self.slots = data.get("slots") or []
        self.slot_by_id = {s["id"]: s for s in self.slots}
        self.slot_order = {s["id"]: i for i, s in enumerate(self.slots)}
        self.bundles = data.get("bundles") or []
        self.bundle_by_id = {b["id"]: b for b in self.bundles}
        self.roles = data.get("roles") or []
        self.role_by_id = {r["id"]: r for r in self.roles}
        self.rules = data.get("rules") or []
        self.rule_by_id = {r["id"]: r for r in self.rules}
        self.guideline_by_id = {g["id"]: g for g in data.get("guidelines") or []}
        self.label_by_id = {g["id"]: g for g in data.get("label_sources") or []}
        self.drug_classes = data.get("drug_classes") or []
        self.class_by_id = {d["id"]: d for d in self.drug_classes}
        self.class_terms = {d["id"]: _class_terms(d) for d in self.drug_classes}
        self.checks = data.get("consistency_checks") or []
        self.contraindications = data.get("drug_contraindications") or []
        self.slot_notes = data.get("slot_notes") or {}
        self.status_vocabulary = data.get("status_vocabulary") or []
        self.fallback_bundle = next((b["id"] for b in self.bundles if "fallback" in (b.get("key") or "")
                                     or "fallback" in (b.get("title") or "").lower()), None)
        self.errors, self.warnings = [], []

    # ------------------------------------------------------------------ lookups
    def slot_spec(self, slot_id):
        return (self.slot_map.get("slots") or {}).get(slot_id) or {}

    def classes_for_slot(self, slot_id):
        return [d["id"] for d in self.drug_classes if slot_id in (d.get("feeds_slots") or [])]

    def sources(self, ids):
        """Guideline/label IDs -> [{id, title, verification}] (unconfirmed guidelines are not cited)."""
        out, seen = [], set()
        for sid in ids:
            if sid in seen:
                continue
            seen.add(sid)
            g = self.guideline_by_id.get(sid) or self.label_by_id.get(sid)
            if not g or g.get("verification") == "unconfirmed":
                continue
            out.append({"id": sid, "title": g.get("title") or g.get("document") or sid,
                        "verification": g.get("verification") or "", "url": g.get("url") or ""})
        return out

    # ------------------------------------------------------------------ validation
    def validate(self):
        E, W = self.errors, self.warnings
        E.clear()
        W.clear()
        slots, bundles, roles = self.slot_by_id, self.bundle_by_id, self.role_by_id
        guides, labels, rules = self.guideline_by_id, self.label_by_id, self.rule_by_id
        shapes = self.data.get("shapes") or {}

        def dupes(items, what):
            seen = set()
            for x in items:
                if x.get("id") in seen:
                    E.append("duplicate %s id %s" % (what, x.get("id")))
                seen.add(x.get("id"))
        for items, what in ((self.slots, "slot"), (self.bundles, "bundle"), (self.roles, "role"),
                            (self.rules, "rule"), (self.drug_classes, "drug class"),
                            (self.data.get("guidelines") or [], "guideline"),
                            (self.data.get("label_sources") or [], "label source")):
            dupes(items, what)

        for s in self.slots:
            if s.get("shape") not in shapes:
                E.append("slot %s: unknown shape %r" % (s["id"], s.get("shape")))
        for b in self.bundles:
            where = "bundle %s" % b["id"]
            seen = {}
            for pr, ids in (b.get("slots") or {}).items():
                if pr not in PRIORITIES:
                    E.append("%s: unknown priority %s" % (where, pr))
                for x in ids:
                    if x not in slots:
                        E.append("%s %s: unknown slot %s" % (where, pr, x))
                    if x in seen:
                        W.append("%s: slot %s listed in both %s and %s" % (where, x, seen[x], pr))
                    seen[x] = pr
            for x in b.get("implies") or []:
                if x not in bundles:
                    E.append("%s implies unknown bundle %s" % (where, x))
            for x in b.get("rules") or []:
                if x not in rules:
                    E.append("%s: unknown rule %s" % (where, x))
            for x in b.get("sources") or []:
                if x not in guides:
                    E.append("%s: unknown guideline %s" % (where, x))
                elif guides[x].get("verification") == "unconfirmed":
                    W.append("%s cites unconfirmed guideline %s (not shown on screen)" % (where, x))
            for x in b.get("expected_but_may_be_missing") or []:
                if x not in slots:
                    E.append("%s expected_but_may_be_missing: unknown slot %s" % (where, x))
                elif x not in seen:
                    W.append("%s expected_but_may_be_missing: slot %s is not in the bundle's slot lists" % (where, x))
            for x in b.get("why_overrides") or {}:
                if x not in slots:
                    E.append("%s why_overrides: unknown slot %s" % (where, x))
                elif x not in seen:
                    W.append("%s why_overrides: slot %s is not in the bundle" % (where, x))
        for r in self.roles:
            where = "role %s" % r["id"]
            for x in r.get("default_bundles") or []:
                if x not in bundles:
                    E.append("%s: unknown default bundle %s" % (where, x))
            for m in r.get("modifiers") or []:
                if m.get("slot") not in slots:
                    E.append("%s modifier: unknown slot %s" % (where, m.get("slot")))
                if m.get("priority") not in PRIORITIES:
                    E.append("%s modifier %s: unknown priority %s" % (where, m.get("slot"), m.get("priority")))
            for x in r.get("sources") or []:
                if x not in guides:
                    E.append("%s: unknown guideline %s" % (where, x))
            if not (r.get("aliases_en") or r.get("aliases_de")):
                E.append("%s: no aliases" % where)
        alias_owner = {}
        for r in self.roles:
            for a in (r.get("aliases_en") or []) + (r.get("aliases_de") or []):
                k = a.lower()
                if k in alias_owner and alias_owner[k] != r["id"]:
                    W.append("alias %r belongs to roles %s and %s" % (a, alias_owner[k], r["id"]))
                alias_owner.setdefault(k, r["id"])
        tag_owner = {}
        for b in self.bundles:
            for t in (b.get("tags_en") or []) + (b.get("tags_de") or []):
                if t.startswith("("):
                    continue
                k = t.lower()
                if k in tag_owner and tag_owner[k] != b["id"]:
                    W.append("tag %r belongs to bundles %s and %s" % (t, tag_owner[k], b["id"]))
                tag_owner.setdefault(k, b["id"])
                if k in alias_owner:
                    W.append("tag %r of %s is also an alias of role %s" % (t, b["id"], alias_owner[k]))
        for r in self.rules:
            where = "rule %s" % r["id"]
            for x in r.get("surface") or []:
                if x in SPECIAL_SURFACES:
                    continue
                if x not in slots:
                    E.append("%s surfaces unknown slot %s" % (where, x))
            src = r.get("sources") or ""
            ids = source_ids(src)
            for x in ids:
                if x not in guides and x not in labels:
                    E.append("%s: unknown source %s" % (where, x))
                elif x in guides and guides[x].get("verification") == "unconfirmed":
                    W.append("%s cites unconfirmed guideline %s" % (where, x))
            if "to source" in src:
                W.append("%s: source still to be found (%r)" % (where, src))
            if not ids and src:
                W.append("%s: no guideline cited (%r)" % (where, src))
        for d in self.drug_classes:
            for x in d.get("feeds_slots") or []:
                if x not in slots:
                    E.append("drug class %s feeds unknown slot %s" % (d["id"], x))
            if "check" in (d.get("brands_examples") or ""):
                W.append("drug class %s: brands not yet checked (%r)" % (d["id"], d.get("brands_examples")))
        for c in self.checks:
            for x in c.get("slots") or []:
                if x not in slots:
                    W.append("consistency check %s: slot entry %r is not a slot ID" % (c["id"], x))
        for x in self.slot_notes:
            if x not in slots:
                E.append("slot_notes: unknown slot %s" % x)
        for x, v in (self.data.get("slot_codes") or {}).items():
            if x not in slots:
                E.append("slot_codes: unknown slot %s" % x)
            elif "from memory" in (v.get("note") or ""):
                W.append("slot_codes %s: codes marked 'from memory' (unverified): %s %s"
                         % (x, v.get("icd10") or "", v.get("atc") or ""))
        for rc in self.data.get("role_code_interests") or []:
            if rc.get("role") not in roles:
                E.append("role_code_interests: unknown role %s" % rc.get("role"))
        for dci in self.contraindications:
            where = "drug_contraindications %s" % dci.get("id")
            if dci.get("drug_class") not in self.class_by_id:
                E.append("%s: unknown drug class %s" % (where, dci.get("drug_class")))
            for x in dci.get("label_sources") or []:
                if x not in labels:
                    E.append("%s: unknown label source %s" % (where, x))
            for item in (dci.get("listed_contraindications") or []) + (dci.get("label_warnings") or []):
                for x in item.get("related_slots") or []:
                    if x not in slots:
                        E.append("%s: unknown related slot %s" % (where, x))
                if item.get("shown_when_bundle") and item["shown_when_bundle"] not in bundles:
                    E.append("%s: unknown bundle %s" % (where, item["shown_when_bundle"]))
                for x in item.get("label_sources") or []:
                    if x not in labels:
                        E.append("%s: unknown label source %s" % (where, x))
            if "check" in (dci.get("atc") or ""):
                W.append("%s: ATC %s not verified" % (where, dci.get("atc")))
        for g in self.data.get("guidelines") or []:
            if g.get("verification") == "unconfirmed":
                W.append("guideline %s unconfirmed: %s" % (g["id"], g.get("title")))
        for row in (self.data.get("validation") or {}).get("demo_coverage") or []:
            for x in row.get("slots") or []:
                if x not in slots:
                    E.append("validation %s: unknown slot %s" % (row.get("question"), x))
            m = re.match(r"(B\d+)\s+(P\d)", row.get("where") or "")
            if not m:
                E.append("validation %s: unreadable 'where' %r" % (row.get("question"), row.get("where")))
            elif m.group(1) not in bundles:
                E.append("validation %s: unknown bundle %s" % (row.get("question"), m.group(1)))
            else:
                for x in row.get("slots") or []:
                    if x not in ((bundles[m.group(1)].get("slots") or {}).get(m.group(2)) or []):
                        E.append("validation %s: slot %s is not at %s %s" % (row.get("question"), x, m.group(1), m.group(2)))
        if not self.fallback_bundle:
            E.append("no fallback bundle (key containing 'fallback')")
        self._validate_slot_map()
        return E, W

    def _validate_slot_map(self):
        E, W = self.errors, self.warnings
        smap = self.slot_map.get("slots") or {}
        for sid in self.slot_by_id:
            if sid not in smap:
                E.append("slot_map: no entry for slot %s" % sid)
        for sid, spec in smap.items():
            if sid not in self.slot_by_id:
                E.append("slot_map: unknown slot %s" % sid)
                continue
            if spec.get("compute") and spec["compute"] not in COMPUTES:
                E.append("slot_map %s: unknown compute %s" % (sid, spec["compute"]))
            sels = spec.get("select") or []
            for sel in sels:
                bad = set(sel) - SELECTOR_KEYS
                if bad:
                    E.append("slot_map %s: unknown selector key(s) %s" % (sid, sorted(bad)))
                for x in sel.get("drug_classes") or []:
                    if x != "*" and x not in self.class_by_id:
                        E.append("slot_map %s: unknown drug class %s" % (sid, x))
                for k in ("match", "exclude"):
                    if sel.get(k):
                        try:
                            re.compile(sel[k])
                        except re.error as e:
                            E.append("slot_map %s: bad regex %s: %s" % (sid, k, e))
            for chk in spec.get("checks") or []:
                for sel in [chk.get("evidence") or {}]:
                    bad = set(sel) - SELECTOR_KEYS
                    if bad:
                        E.append("slot_map %s check %s: unknown selector key(s) %s" % (sid, chk.get("label"), sorted(bad)))
            if not sels and not spec.get("always_not_documented") and spec.get("compute") != "age_sex":
                W.append("slot_map %s: no selector and not marked always_not_documented" % sid)


_KB = None


def load(kb_path=KB_PATH, slot_map_path=SLOT_MAP_PATH, strict=True):
    """Load + validate; raise KBError (listing every problem) if anything is wrong."""
    k = KB(_load(kb_path), _load(slot_map_path))
    errors, _warnings = k.validate()
    if errors and strict:
        raise KBError(errors)
    return k


def kb():
    global _KB
    if _KB is None:
        _KB = load()
    return _KB


def main():
    k = load(strict=False)
    print("KB %s: %d slots, %d bundles, %d roles, %d rules, %d guidelines; slot map %d entries"
          % (k.version, len(k.slots), len(k.bundles), len(k.roles), len(k.rules), len(k.guideline_by_id),
             len(k.slot_map.get("slots") or {})))
    print("errors (%d):" % len(k.errors))
    for e in k.errors:
        print("  E " + e)
    print("warnings (%d):" % len(k.warnings))
    for w in k.warnings:
        print("  W " + w)
    return 1 if k.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
