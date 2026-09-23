#!/usr/bin/env python3
"""Every shipped skills/*/SKILL.md must have frontmatter a skill loader can parse.

⛔ WHY THIS EXISTS. 0.64.0 shipped `skills/cowork/SKILL.md` with the description
`The trigger is the SITUATION, never the wording: use it ...`. A colon followed by a space
inside an unquoted YAML scalar is a mapping indicator, so the frontmatter was invalid YAML -
and Claude Code DROPPED THE SKILL SILENTLY: measured 2026-09-23, a nested session listed 127
skills with `dispatch-guard:dispatch-protocol` and `dispatch-guard:unattended-work` but no
`dispatch-guard:cowork`, and `plugin_warnings` was null. Every check that release ran
(zh/en counts, control characters, identifiers, the whole test suite) passed, because none
of them read the file the way the loader does.

Checks, per skill: the file opens with a `---` frontmatter block that closes; it parses as
YAML to a mapping; `name` equals the directory name; `description` is a non-empty string.
Uses PyYAML when present; without it, a strict fallback refuses the known-bad shapes (a
plain scalar containing ": " or " #", or starting with an indicator character).

Positive control: the exact 0.64.0 line must be REJECTED, and its fixed form ACCEPTED, by
the same function - so a checker that accepts everything cannot pass.
No literal backslash in this file.
"""
import io, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))

try:
    import yaml  # type: ignore
except ImportError:  # pragma: no cover - exercised on machines without PyYAML
    yaml = None

INDICATORS = "-?:,[]{}#&*!|>'\"%@`"


def _fallback_parse(fm):
    """Minimal, STRICT top-level `key: value` reader. Raises ValueError on doubt."""
    out = {}
    for raw in fm.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if raw[:1] in (" ", "\t"):
            raise ValueError("nested or continued value - install PyYAML to check it: %r" % raw[:60])
        m = re.match(r"([A-Za-z0-9_-]+):(?: (.*))?$", raw)
        if not m:
            raise ValueError("not a key: value line: %r" % raw[:60])
        key, val = m.group(1), (m.group(2) or "").strip()
        quoted = len(val) >= 2 and val[0] == val[-1] and val[0] in "'\""
        if not quoted:
            if val and val[0] in INDICATORS:
                raise ValueError("%s: plain scalar starts with an indicator %r" % (key, val[0]))
            if ": " in val or " #" in val:
                raise ValueError("%s: plain scalar contains ': ' or ' #'" % key)
        else:
            val = val[1:-1]
        out[key] = val
    return out


def parse_frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("no opening --- on line 1")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("frontmatter never closes")
    fm = "\n".join(lines[1:end])
    if yaml is not None:
        try:
            data = yaml.safe_load(fm)
        except yaml.YAMLError as exc:
            raise ValueError(str(exc).splitlines()[0])
    else:
        data = _fallback_parse(fm)
    if not isinstance(data, dict):
        raise ValueError("frontmatter is not a mapping")
    return data


def check_skill(path):
    name = os.path.basename(os.path.dirname(path))
    data = parse_frontmatter(io.open(path, encoding="utf-8").read())
    if data.get("name") != name:
        raise ValueError("name %r != directory %r" % (data.get("name"), name))
    desc = data.get("description")
    if not isinstance(desc, str) or not desc.strip():
        raise ValueError("description missing or empty")
    return len(desc)


def main():
    bad_064 = ("---\nname: cowork\ndescription: The trigger is the SITUATION, never the "
               "wording: use it whenever more than one party is involved\n---\n")
    fixed = bad_064.replace("wording: use", "wording. Use")
    try:
        parse_frontmatter(bad_064)
        print("POSITIVE CONTROL FAILED: the 0.64.0 description was accepted")
        return 1
    except ValueError:
        pass
    parse_frontmatter(fixed)                              # must not raise
    print("positive control: 0.64.0 line rejected, fixed line accepted (%s)"
          % ("PyYAML" if yaml else "fallback"))

    skills_dir = os.path.join(REPO, "skills")
    found = sorted(os.path.join(skills_dir, d, "SKILL.md") for d in os.listdir(skills_dir)
                   if os.path.isfile(os.path.join(skills_dir, d, "SKILL.md")))
    if not found:
        print("no skills found under %s - the check did not run" % skills_dir)
        return 1
    failed = 0
    for p in found:
        rel = os.path.relpath(p, REPO)
        try:
            n = check_skill(p)
            print("OK    %-40s description %d chars" % (rel, n))
        except ValueError as exc:
            failed += 1
            print("FAIL  %-40s %s" % (rel, exc))
    print("%d skill(s) checked, %d failed" % (len(found), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
