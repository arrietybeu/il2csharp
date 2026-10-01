"""Structural declaration diff for the Cpp2IL cross-check gate (side A).

Compares a metadata dump (tools/dump_decls.py) against an emitted-tree
extraction (tools/extract_decls.py). Comparison is structural: type
existence + kind, base/interface short outer names, member existence +
name + staticness + generic arity + parameter count. Full type
spellings are recorded in the dump for human review and side B, but
are not compared here (emitted text shortens through usings; resolving
that is side-B work). Exit 0 on match, 1 on any difference, 2 on
usage errors. Constructor spellings normalize (.ctor/.cctor).
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from il2cpp.names import sanitize, safe_ident, sanitize_qualifier
from il2cpp.text import MANGLED_IDENT_RX


def _mangle(s):
    return MANGLED_IDENT_RX.sub(
        lambda m: m.group(0).replace("<", "_").replace(">", "_")
        .replace(".", "_").replace("|", "_"), s)


def canon_owner(path):
    """Owner path to emitted spelling: nesting dots, render + file rules."""
    s = (path or "").replace("+", ".")
    return _mangle(safe_ident(sanitize(s)))


def canon_member(name):
    """Member name to emitted spelling (.ctor family passes through)."""
    if name.startswith("."):
        return name
    if "." in name:
        head, _, tail = name.rpartition(".")
        return _mangle(sanitize_qualifier(head) + "." + safe_ident(tail))
    return _mangle(safe_ident(sanitize(name)))


def _strip_genargs(s):
    out = []
    depth = 0
    for ch in s:
        if ch == "<":
            depth += 1
            continue
        if ch == ">":
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            out.append(ch)
    return "".join(out)


def canon_short(s):
    s = (s or "").strip()
    if s.startswith("global::"):
        s = s[len("global::"):]
    s = re.sub(r"\s+", "", s)
    if not s or s == "-":
        return None
    s = _mangle(s.replace("+", "."))
    m = re.match(r"^([A-Za-z_][\w.]*)", s)
    seg = m.group(1) if m else s
    segs = seg.split(".")
    short = segs[-1] if segs else s
    short = _strip_genargs(short)
    # emitter renders generic arity `` `N `` as `_N` (safe_ident/sanitize),
    # while metadata-side spellings drop it at the backtick; strip a
    # trailing _N so both meet (literal trailing-_N names conflate --
    # accepted, vanishingly rare in base/qualifier position).
    return re.sub(r"_\d+$", "", short)


def parse_dump(lines):
    types = {}
    cur = None
    _cur_raw = None
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith("A "):
            continue
        if ln.startswith("T "):
            m = re.match(r"^T (\S+) kind=(\S+) base=(.*) ebase=(\S+) ifaces=(.*)$", ln)
            if not m:
                raise ValueError("bad T line: %r" % ln)
            path, kind, base, ebase, ifaces = m.groups()
            base = base.strip()
            ifaces = ifaces.strip()
            _cur_raw = path
            cur = {"kind": kind, "base": base, "ebase": ebase, "ifaces": ifaces,
                   "members": []}
            types[path] = cur
        elif ln[0] in ("M", "F", "P", "E") and cur is not None:
            if ln.startswith("M "):
                m = re.match(r"^M (.*) s=(\d+) g=(\d+)(.*)$", ln)
                if not m:
                    raise ValueError("bad member line: %r" % ln)
                dotted, s, g, _rest = m.groups()
                if not dotted.startswith(_cur_raw + "."):
                    raise ValueError("bad member line: %r" % ln)
                name = dotted[len(_cur_raw) + 1:]
                kind = "M"
                pm = re.search(r"\((.*)\)->", _rest)
                if pm and pm.group(1).strip():
                    nargs = len([x for x in _top_commas(pm.group(1))
                                 if x.strip()])
                else:
                    nargs = 0
                cur["members"].append((kind, name, int(s), int(g), nargs))
            elif ln.startswith("P "):
                m = re.match(r"^P (.*) s=(\d+) get=(\d+) set=(\d+) (.*)$", ln)
                if not m:
                    raise ValueError("bad member line: %r" % ln)
                dotted, s, g, st, _ty = m.groups()
                if not dotted.startswith(_cur_raw + "."):
                    raise ValueError("bad member line: %r" % ln)
                name = dotted[len(_cur_raw) + 1:]
                cur["members"].append(
                    ("P", name, int(s), 0, int(g) + 2 * int(st)))
            elif ln.startswith("E "):
                m = re.match(r"^E (.*) s=(\d+) add=(\d+) rem=(\d+) (.*)$", ln)
                if not m:
                    raise ValueError("bad member line: %r" % ln)
                dotted, s, a, r, _ty = m.groups()
                if not dotted.startswith(_cur_raw + "."):
                    raise ValueError("bad member line: %r" % ln)
                name = dotted[len(_cur_raw) + 1:]
                cur["members"].append(
                    ("E", name, int(s), 0, int(a) + 2 * int(r)))
            else:
                m = re.match(r"^F\s+(.+?)\s+s=(\d+)\s+(.+)$", ln)
                if not m:
                    raise ValueError("bad member line: %r" % ln)
                dotted, s, fty = m.groups()
                if _cur_raw is None or not dotted.startswith(_cur_raw + "."):
                    raise ValueError("bad member line: %r" % ln)
                name = dotted[len(_cur_raw) + 1:]
                cur["members"].append(("F", name, int(s), 0, 0))
    return types


def _top_commas(s):
    """Split on top-level commas (nested <>[]() don't split)."""
    parts, depth, cur = [], 0, []
    pairs = {"<": ">", "[": "]", "(": ")"}
    closers = set(">]})")
    stack = []
    for ch in s:
        if ch in pairs:
            stack.append(pairs[ch])
            depth += 1
            cur.append(ch)
        elif stack and ch == stack[-1]:
            stack.pop()
            depth = max(0, depth - 1)
            cur.append(ch)
        elif ch == "," and not stack:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def parse_extracted(lines):
    types = {}
    cur = None
    _cur_raw = None
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        if ln.startswith("A "):
            continue
        if ln.startswith("T "):
            m = re.match(r"^T (\S+) kind=(\S+) base=(.*) ebase=(\S+) ifaces=(.*)$", ln)
            if not m:
                raise ValueError("bad T line: %r" % ln)
            path, kind, base, ebase, ifaces = m.groups()
            base = base.strip()
            ifaces = ifaces.strip()
            _cur_raw = path
            cur = {"kind": kind, "base": base, "ebase": ebase, "ifaces": ifaces,
                   "members": []}
            types[path] = cur
        elif ln[0] in ("M", "F", "P", "E") and cur is not None:
            m = re.match(r"^(M|F|P|E) (.*) s=(\d+) g=(\d+) n=(\d+)$", ln)
            if not m:
                raise ValueError("bad member line: %r" % ln)
            kind, dotted, s, g, n = m.groups()
            if _cur_raw is None or not dotted.startswith(_cur_raw + "."):
                raise ValueError("bad member line: %r" % ln)
            name = dotted[len(_cur_raw) + 1:]
            cur["members"].append((kind, name, int(s), int(g), int(n)))
    return types


def norm_types(types, from_dump):
    norm = {}
    for path, r in types.items():
        cpath = canon_owner(path)
        if from_dump:
            base = r["base"]
            base = None if base in (None, "-", "?") else canon_short(base)
            if r["ifaces"] in ("-", ""):
                ifaces = []
            else:
                ifaces = [x for x in
                          (canon_short(y) for y in r["ifaces"].split(","))
                          if x]
        else:
            base = r["base"]
            base = None if base in (None, "-") else canon_short(base)
            if r["ifaces"] in ("-", ""):
                ifaces = []
            else:
                ifaces = [x for x in
                          (canon_short(y) for y in r["ifaces"].split(","))
                          if x]
        # first-interface-as-base: the emitter renders the first interface
        # in the base slot when no class parent is spelled (mirror hdr).
        ordered = ([base] if base is not None else []) + list(ifaces)
        first = ordered[0] if ordered else None
        rest = set(ordered[1:])
        eb = r.get("ebase")
        eb = None if eb in (None, "-") else eb.strip()
        mems = []
        for k, n, s, g, a in r["members"]:
            cn = canon_member(n)
            if "." in cn and not cn.startswith("."):
                q, _, t = cn.rpartition(".")
                qs = canon_short(q)
            else:
                t, qs = cn, None
            mems.append((k, t, qs, s, g, a))
        norm[cpath] = (r["kind"], first, eb, rest, tuple(sorted(mems, key=_mkey)))
    return norm


def _mkey(x):
    return (x[0], x[1], x[2] or "", x[3], x[4], x[5])


def _match_members(dm, em, path, problems):
    """Two-pass member match: exact, then tail+qualifier-compatible.

    Explicit implementations render bare or short-qualified when the
    emitter can de-explicitize (public signature satisfies the slot),
    and fully qualified otherwise; both spellings name the same slot.
    Tails must match; qualifiers must match when both sides spell one.
    Multiset semantics throughout: duplicate shapes match pairwise,
    so count changes never hide inside set collapse.
    """
    dlist = sorted(dm, key=_mkey)
    elist = sorted(em, key=_mkey)
    if dlist == elist:
        return
    used_e = [False] * len(elist)
    still_d = []
    for d in dlist:
        hit = None
        for j, e in enumerate(elist):
            if not used_e[j] and e == d:
                hit = j
                break
        if hit is not None:
            used_e[hit] = True
            continue
        for j, e in enumerate(elist):
            if used_e[j] or e[0] != d[0] or e[1] != d[1] \
                    or e[3] != d[3] or e[4] != d[4] or e[5] != d[5]:
                continue
            if d[2] is not None and e[2] is not None and e[2] != d[2]:
                problems.append("qualifier mismatch %s: %r vs %r" % (path, d, e))
                used_e[j] = True
                hit = j
                break
            if d[2] is None or e[2] is None or e[2] == d[2]:
                hit = j
                break
        if hit is not None:
            used_e[hit] = True
            continue
        still_d.append(d)
    still_e = sorted([e for j, e in enumerate(elist) if not used_e[j]],
                     key=_mkey)
    for x in still_d[:10]:
        problems.append("missing emitted member %s: %r" % (path, x))
    for x in still_e[:10]:
        problems.append("extra emitted member %s: %r" % (path, x))
    if len(still_d) > 10 or len(still_e) > 10:
        problems.append("... +%d more member diffs in %s" %
                        (len(still_d) + len(still_e) - 20, path))


def diff_dump_extracted(dump_lines, ext_lines):
    d = norm_types(parse_dump(dump_lines), True)
    e = norm_types(parse_extracted(ext_lines), False)
    problems = []
    for path in sorted(set(d) | set(e)):
        if path not in d:
            problems.append("extra emitted type: %s" % path)
            continue
        if path not in e:
            problems.append("missing emitted type: %s" % path)
            continue
        dk, db, de, di, dm = d[path]
        ek, eb, ee, ei, em = e[path]
        if dk != ek:
            problems.append("kind mismatch %s: %s vs %s" % (path, dk, ek))
        if db != eb:
            problems.append("base mismatch %s: %s vs %s" % (path, db, eb))
        if de != ee:
            problems.append("ebase mismatch %s: %s vs %s" % (path, de, ee))
        if set(di) != set(ei):
            problems.append("ifaces mismatch %s: %s vs %s" %
                            (path, sorted(di), sorted(ei)))
        _match_members(dm, em, path, problems)
    return problems


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dump", required=True)
    ap.add_argument("--extracted", required=True)
    args = ap.parse_args()
    with open(args.dump, encoding="utf-8") as f:
        dump_lines = f.read().splitlines()
    with open(args.extracted, encoding="utf-8") as f:
        ext_lines = f.read().splitlines()
    problems = diff_dump_extracted(dump_lines, ext_lines)
    for p in problems:
        print(p)
    print("%d problem(s)" % len(problems))
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
