#!/usr/bin/env python3
"""The README's skill flowcharts must stay structurally sound, paired, and honest about the hook.

    python Tools/Debug/test_readme_charts.py

⛔ WHY THIS EXISTS. Since 0.70.3 README.md carries a mermaid flowchart for each of the three
skills, once in the Traditional Chinese half and once in the English half. They are a SECOND
description of what the hook does - and the audit of 2026-10-06 found six sentences in this
repository that had silently gone older than the code they described. A chart drifts the same
way, and nobody reads a chart closely enough to notice. This check cannot tell whether a box is
TRUE (that needs PROTOCOL.md §3 and a reader); it makes the drift that CAN be measured fail loudly:

1. Each half has one chart per skill - dispatch-protocol, unattended-work, cowork - found by the
   legend line right above the fence, and nothing else.
2. Every chart: each node has an edge; no node id is a mermaid reserved word or starts with `o` /
   `x` (`--o` / `--x` are edge types); every id in the `class ... gate` line is a node.
3. THE COLOUR RULE (0.70.4): a box is red exactly when its label names the hook or the gate.
   That sentence is what the hook refuses, notes or carries out. A red box without one overclaims;
   a white box with one hides a check.
4. The zh and en chart of each skill have identical node ids, edges, edge kinds and red set: a
   translation must not change the flow.

NOT checked here: that mermaid renders the charts (that needs a browser - the render harness used
for 0.70.3/0.70.4 is in Memory/tasks/20261006-133755-readme-skill-diagrams/scratch/01-render/),
and whether each label is true.

Mutation self-check: the same functions must REJECT three planted defects (an English edge
dropped, the hook word removed from a red label, a reserved id) before the real README is judged -
so a checker that accepts everything cannot pass.
No literal backslash outside a raw string in this file.
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
README = os.path.join(REPO, "README.md")
NL = chr(10)
CR = chr(13)

SKILLS = ("dispatch-protocol", "unattended-work", "cowork")
EN_HEADING = "# dispatch-guard (English)"
RESERVED = {"end", "default", "style", "linkStyle", "classDef", "class", "call", "href",
            "click", "interpolate", "subgraph", "graph", "flowchart"}
FENCE = re.compile(r"```mermaid\n(.*?)\n```", re.S)
QUOTED = re.compile(r'"[^"]*"')
EDGE = re.compile(r'^(\w+)(?:\[""\]|\{""\})?\s*(-->|-\.->)\s*(?:\|""\|\s*)?(\w+)')
NODE = re.compile(r'\b([A-Za-z]\w*)(?=[\[\{]"")')
LABEL = re.compile(r'\b([A-Za-z]\w*)[\[\{]"([^"]*)"[\]\}]')
HOOKWORD = re.compile(r"\b(hook|gate)\b", re.I)


def charts(half):
    """{skill: mermaid source} for one half of the README, keyed by the legend line above."""
    found = {}
    for m in FENCE.finditer(half):
        before = [l for l in half[:m.start()].split(NL) if l.strip()]
        legend = before[-1] if before else ""
        named = [s for s in SKILLS if "`%s`" % s in legend]
        if len(named) != 1:
            raise ValueError("a mermaid chart whose legend names %d skills: %r" % (len(named), legend[:80]))
        if named[0] in found:
            raise ValueError("two charts for %s in one half" % named[0])
        found[named[0]] = m.group(1)
    return found


def shape(src):
    """(node ids, edges, red ids, {id: label}). Labels are blanked before ids are read."""
    ids, edges, red = set(), [], set()
    for line in src.split(NL):
        s = QUOTED.sub('""', line.strip())
        if s.startswith("class ") and not s.startswith("classDef"):
            red |= set(s.split()[1].split(","))
            continue
        if not s or s.startswith(("classDef", "flowchart")):
            continue
        m = EDGE.match(s)
        if m:
            edges.append((m.group(1), m.group(2), m.group(3)))
            ids.update((m.group(1), m.group(3)))
        ids.update(NODE.findall(s))
    return ids, edges, red, dict(LABEL.findall(src))


def problems(text):
    """Every structural defect in the README text, as a list of strings ([] = sound)."""
    text = text.replace(CR + NL, NL)
    if text.count(EN_HEADING) != 1:
        return ["the English half's heading %r is not there exactly once" % EN_HEADING]
    zh_text, en_text = text.split(EN_HEADING, 1)
    out = []
    try:
        halves = {"zh": charts(zh_text), "en": charts(en_text)}
    except ValueError as exc:
        return [str(exc)]
    for lang, got in halves.items():
        missing = [s for s in SKILLS if s not in got]
        if missing:
            out.append("%s half: no chart for %s" % (lang, ", ".join(missing)))
    for skill in SKILLS:
        shapes = {}
        for lang in ("zh", "en"):
            if skill not in halves[lang]:
                continue
            ids, edges, red, labels = shape(halves[lang][skill])
            shapes[lang] = (ids, edges, red)
            where = "%s/%s" % (lang, skill)
            touched = {a for a, _k, _b in edges} | {b for _a, _k, b in edges}
            for nid in sorted(ids - touched):
                out.append("%s: node %s has no edge" % (where, nid))
            for nid in sorted(ids):
                if nid in RESERVED or nid[0] in "ox":
                    out.append("%s: node id %r is reserved or starts with o/x" % (where, nid))
            for nid in sorted(red - ids):
                out.append("%s: red id %s is not a node" % (where, nid))
            hooked = {n for n, lab in labels.items() if HOOKWORD.search(lab)}
            for nid in sorted(red - hooked):
                out.append("%s: %s is red but its label names neither the hook nor the gate" % (where, nid))
            for nid in sorted(hooked - red):
                out.append("%s: %s names the hook or the gate but is not red" % (where, nid))
        if len(shapes) == 2:
            (zi, ze, zr), (ei, ee, er) = shapes["zh"], shapes["en"]
            if zi != ei:
                out.append("%s: zh/en node ids differ: only zh %s, only en %s"
                           % (skill, sorted(zi - ei), sorted(ei - zi)))
            if sorted(ze) != sorted(ee):
                out.append("%s: zh/en edges differ: only zh %s, only en %s"
                           % (skill, sorted(set(ze) - set(ee)), sorted(set(ee) - set(ze))))
            if zr != er:
                out.append("%s: zh/en red sets differ: only zh %s, only en %s"
                           % (skill, sorted(zr - er), sorted(er - zr)))
    return out


def mutate(text, old, new, nth_after=None):
    """Replace the first `old` after the marker `nth_after` (or anywhere), exactly once."""
    start = text.index(nth_after) if nth_after else 0
    i = text.index(old, start)
    return text[:i] + new + text[i + len(old):]


def main():
    with io.open(README, "rb") as fh:
        text = fh.read().decode("utf-8").replace(CR + NL, NL)
    # ⛔ Mutation self-check first: three planted defects, each must be named.
    en_cowork = "How `cowork` runs"
    edge = re.search(r"\n(  \w+ -->\|\"[^\"]*\"\| \w+)\n", text[text.index(en_cowork):]).group(1)
    first_red = re.search(r"class (\w+)", text[text.index(EN_HEADING):]).group(1)
    red_label = re.search(r"\b%s\[\"([^\"]*)\"" % first_red, text[text.index(EN_HEADING):]).group(1)
    planted = [
        ("an English edge dropped", mutate(text, edge + NL, "", en_cowork), "edges differ"),
        ("the hook word removed from a red label",
         mutate(text, red_label, HOOKWORD.sub("it", red_label), EN_HEADING),
         "names neither the hook nor the gate"),
        ("a reserved node id", text.replace("needAgent", "end"), "reserved"),
    ]
    for what, bad, expect in planted:
        found = problems(bad)
        if not any(expect in p for p in found):
            print("MUTATION SURVIVED: %s was not reported (got %r)" % (what, found[:3]))
            return 1
        print("mutation killed: %s" % what)
    found = problems(text)
    for p in found:
        print("FAIL  " + p)
    zh, en = text.split(EN_HEADING, 1)
    print("%d chart(s) in the zh half, %d in the en half, %d problem(s)"
          % (len(FENCE.findall(zh)), len(FENCE.findall(en)), len(found)))
    return 1 if found else 0


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    sys.exit(main())
