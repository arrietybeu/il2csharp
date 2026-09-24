# AGENTS.md — new-session tutorial

`il2csharp` is an IL2CPP → C# decompiler: `global-metadata.dat` +
`GameAssembly.dll` in, a C# tree out, every body lifted from native x64.
This file orients a new session. Normative rules live in `CLAUDE.md`;
start there, then `docs/todo.md` (Current work section).

## First reads (in order)

1. `CLAUDE.md` — architecture, mandatory guardrails, validation gates.
2. `docs/todo.md` — current work (top section is live), what's done,
   what's deferred with evidence.
3. `nowtodo.md` — the 2026-09-19 stop record + addendum; mostly
   historical, still the task checklist.
4. `docs/README.md` — map of every doc and `§NN` cross-reference.
5. Root `README.md` — what native constructs recover as what C#.

## Code map

- `il2csharp.py` — thin CLI launcher (CRLF **with** BOM).
- `il2cpp/` — the package (all CRLF, no BOM). Public names re-exported
  from `il2cpp/__init__.py`:
  - `metadata.py`, `binary.py` — `global-metadata.dat`, PE/ELF frontends.
  - `runtime/` — `Il2Cpp`: registrations, usage slots, EH4 (`core.py`
    holds the class; `registration`/`types`/`fields`/`eh` mixins).
  - `lifter/` — symbolic x64 over iced-x86 (`state`, `values`, `insn`,
    `calls`, `render` mixins; `aggregates.py` = stack-tile/struct
    provenance; `expr.py` = `Expr` values).
  - `dec/` — CFG + structured decompiler: `build` (blocks, site scans),
    `analyze` (dry/real exec, merges, phi copies), `structure`
    (the ~25-stage statement pipeline — pass order matters, read it
    before reordering), `flow`/`highlevel` (sugar passes incl.
    `_switch_synth`, `_hash_string_switch`), `textpass` (final
    `*(E+N)` → `((byte*)E+N)[0]` rendering), `emit`, others.
  - `emitter.py`, `headers.py`, `cli.py`, `arm64.py` scaffold.
- `tests/` — portable unit tests (LF) + game goldens
  (`test_game_goldens.py`, `tests/goldens_review84.json` — frozen).
- `tools/` — `inspect_methods.py` (`--mi` exact MethodDef rows),
  `corpus_common.py` (fixture loader). Add `tools/` to `PYTHONPATH`.
- `work/` — scratch runners (`work/lib/`: `sweep_audit.py`,
  `tree_brace_audit.py`, `ts_gate.py`; routing in `work/README.md`).
- `testgame/` — licensed fixtures via Git LFS (private repo; never
  redistribute, never go public without removing them).
- `final_out/` — last promoted tree (2026-09-19). Read-only reference.
  Never edit, never rebuild into.
- `validation_reports/` — frozen gate evidence. Don't touch.
- Temp scratch: `C:\Users\crax\AppData\Local\Temp\opencode` (outside repo).

## Session setup (PowerShell)

```powershell
$env:PYTHONHASHSEED = '0'
$env:IL2CSHARP_METADATA = (Resolve-Path 'testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat').Path
$env:IL2CSHARP_BINARY = (Resolve-Path 'testgame/GameAssembly.dll').Path
$env:PYTHONPATH = '<repo>;tools'
```

## Common tasks

**Lift one method** (the fast loop — no file I/O):
`tools/inspect_methods.py --metadata ... --binary ... --mi 25293`.
Goldens key on MethodDef row (`mi`), never VA (shared bodies alias).

**Portable tests:** `python -m pytest -q -m "not game" --disable-warnings`
(836 pass). **Full suite:** `python -m pytest -q` (~3.5 min, needs fixture
env above; suite is fully green — any failure is yours).

**Rebuild a tree:** `python il2csharp.py testgame -o <name_out1> [--only
Assembly-CSharp]`. Name output `*_out1/` (git-ignored). Gate with
`python work/lib/tree_brace_audit.py <dir>` (must print 0 unbalanced).

**Land a source fix:** repro first (probe script in temp dir, never in
repo), binary-safe patch (below), compileall, portable suite, targeted
`--mi` re-lifts, full-suite recount (failure SET must be byte-identical
to the triaged list), docs, commit, push. Decline-by-default: every
unproven shape keeps today's spelling; raw is always honest.

## Iron contracts (violations cause phantom diffs / flaky output)

- `il2cpp/*.py` are CRLF no-BOM: edit via binary read/write scripts,
  assert `d.count(b'\r\n') == d.count(b'\n')` after every touch.
  Read-text/write-text, `sed -i`, and heredocs silently rewrite to LF.
  `tests/*.py` and `*.md` are LF.
- Never open the target for writing until assertions pass (build in
  memory, assert, write once); never re-derive backups from live files.
- PowerShell 5.1: no `head`/`tail`/`grep`/`rm`/`||`/`&&`; no `>` redirect
  (writes UTF-16); quote paths with spaces. `PYTHONHASHSEED=0` always —
  set iteration order leaks into temp names otherwise.
- GitHub is the history authority (old backup trees were reaped). Never
  commit secrets/fixtures churn; never regen snapshots or promote output
  without an explicit user call. Stash-prove-clean before attributing a
  break to your change.

## Current state (2026-09-24, `main` clean)

Landed since: identical-render shared collapse (70 sites), shared-stub
native disassembly comments, noreturn-shared forwarder returns (63
Neon `/* nothing */` -> `return Target(args)`), r8 Assembly-CSharp
promotion (ComputeStringHash x3 + stub comments; rest of tree at r7).
Full suite: 1013 passed / 0 failed (836 portable + 177 game). Open, by
payoff: same-name multi-owner receiver pick (~1.5k sites: GetResult /
get_IsCompleted / floatN get_Item), ToString/op_Implicit static+arity
(865 sites, 1 VA, spray caveats need a probe), constant-zero fold (239
sites, 2 VAs).
