# CLAUDE.md

## Current source and validation authority — follow-up promoted tree

The working source contains fixes 114 (method dispatch flags, generic
constructor names), 115 (unsafe on pointer-signature methods/ctors), 116
(unsafe on pointer-typed fields/properties; CS0214 fully zero), 117
(generic `_N` reference spellings matching declarations, incl. explicit
interface qualifiers; CS0115 fully zero), 118 (tuple-based explicit
qualifiers + structure-aware qualifier sanitize; CS9334 fully zero), 119
(namespace-qualified spellings feeding `using` generation), 120 (nested
owner paths via `nested_types`), 121 (mirror-nested own-suffix +
owner-first distribution), 122 (receiver-proven stub temps take the
unique owner's type with a caller-proven cast), and 123
(collision-aware using-strip with full-depth generic arguments; CS0246
fully zero), plus three unnumbered follow-ups: shortest round-trip float32
literals with fixed-point tie-break, entry stack-parameter names/types
surviving the pass wipe with slot reloads restoring the recorded kind, and
exact runtime type on klass-equality cmov select. 795 tests pass. The
follow-ups completed the full gate — strict rebuild 11,181 files /
114,458 bodies with 0 failures, parser 0 bad files, direct sweep 116,178
methods / 0 crashes, 6 reviewed golden changes — and were promoted
2026-09-19: `final_out/` holds `work/promote_out` (11,274 files, aggregate
`db468523…050c36105`). The `bckups/` copies of prior promoted
trees were deleted 2026-09-19 per user call — GitHub is now the history
authority; any prior tree rebuilds from git history. See `docs/todo.md` for exact evidence and the
remaining compiler backlog.

Read `docs/reviews/REVIEW84.md`–`REVIEW87.md`, `docs/todo.md`'s Current work section, and
`docs/archive/reviews-log.md` section 0bf first. `final_out/` is the complete strict-built
follow-up output promoted 2026-09-19 (11,274 files, aggregate `db468523…050c36105`),
not the Review 84 file set alone, b42/b76, or a partial candidate. Historical paragraphs below retain
the reasoning behind older changes; their old "current" labels are not release authority.
`validation_reports/review84/summary.json` (baseline) plus `validation_reports/followups_sweep.json`,
`followups_parse.json`, and `followups_promotion_verification.json`
are authoritative for the promoted tree. Fix-114 evidence lives in
`validation_reports/review114_*`; fix-115 gates, probe, and promotion record
in `validation_reports/review115_*`; fix-116 in `validation_reports/review116_*`;
fix-117 in `validation_reports/review117_*`;
fix-118 in `validation_reports/review118_*`;
fix-119 in `validation_reports/review119_*`;
fix-120 in `validation_reports/review120_*`;
fix-121 in `validation_reports/review121_*`;
fix-122 in `validation_reports/review122_*`;
fix-123 in `validation_reports/review123_*`.

**Current invariants:**
- `base_chain_tds` maps IL2CPP_TYPE_OBJECT only through one unique
  `System.Object` TypeDef and stops cycles without repeating a TypeDef. The
  broad shared-receiver heuristic must use `_legacy_shared_receiver_chain` so a
  newly visible Object tail cannot steal unrelated derived-receiver calls.
- `_chain_cache` and `_bases_cache` are per `Il2Cpp` instance. TypeDef indices
  are binary-local; never restore class-level cache sharing across loaded
  fixtures or workspaces.
- `_shared_parameterless_ctor_target` is an exact constructor proof, not normal
  shared-call resolution. Require typed current-constructor `this` or exact
  fresh `_alloc` provenance, a reference-type inheritance match, zero declared
  parameters, instance/void ABI, and exactly one concrete closed MethodDef.
  Generic candidates, multiple eligible ancestors, unknown/byref/value-type
  receivers, and malformed candidates must decline.
- `_constructor_initializer_kind` may emit the internal `this..ctor` /
  `base..ctor` pseudo form only while lifting the matching nonstatic `.ctor`.
  Same-type targets mean `this`; ancestor targets mean `base`. The emitter owns
  promotion to the C# initializer and no raw pseudo call may remain in output.
- `_alloc` belongs to the exact `il2cpp_object_new` expression and must survive
  copies/binding until one constructor consumes it. Complete an unbound
  allocation directly or patch exactly one matching declaration. Never fold by
  type-name similarity, globally deduplicate `new`, or emit a second discarded
  `new T(args)` statement.
- Preserve the 15 conservative constructor-sweep leftovers (12 ambiguous
  `sub_180506120` sites and three complex legacy `this.ctor` sites) until new
  receiver/generic proof exists; do not force them for cosmetic cleanliness.
- `shared_return_type` is an all-candidate proof for an address with more than
  one metadata owner. Every candidate must be readable, fully closed,
  structurally identical, and supported by `_return_abi_is_known`; one failure
  declines the address. Never use a majority, the first candidate, or printed
  type-name equality.
- Root MethodSpec `VAR`/`MVAR` returns may inflate from exact class/method
  instantiations. An open generic at any nested depth declines. Preserve byref
  from the return signature, not the type argument.
- Return consensus does not resolve method identity. Keep the honest
  `sub_<va>/*shared body, N candidates*/` rendering and do not apply
  method-name/receiver/property transformations that require one owner.
- A consensus value type folds sret only when the individual call's first
  argument is an observed address. Require a known exact nonzero value-type
  size; generic value types, source-level ref returns, and unsupported opaque
  ABI classes remain unknown.
- Ambiguous arity trimming happens before sret folding and uses the inflated
  consensus type for the hidden-buffer slot. A typed shared call binds at its
  call instruction so type evidence cannot reorder it across visible effects.
- A partitioned sweep can expose pre-existing state/order-sensitive render
  hashes. Use fixed-order isolated old/new source parity before attributing hash
  changes: Review 83 proves 4,322 genuine changed bodies and classifies 2,029
  initial comparison deltas as partition-state-only.
- `_semantic_local_names` is a final-render-boundary readability pass. Never move
  it before copy/dead-local/control-flow/interface-dispatch processing: those
  passes intentionally consume the num/flag/real/obj vocabulary.
- A type-derived local name is allowed only when the emitted declaration type is
  already concrete. `object objN` is the honesty marker for unresolved native
  values and must remain `objN`; prettier names are not type evidence.
- Semantic names are method-wide unique, collision-checked against every body
  identifier and every metadata parameter name (even unused parameters), and
  replaced outside string/character literals and line/block comments only.
- `_refine_explicit_object_locals` may strengthen `object` only for a
  single-definition array creation, string literal, or exact `typeof` RHS with
  no later write or ref/out/in/address escape. Do not add `new T()` without
  proving reference type and boxing identity. Array rank counts top-level
  dimension commas only; uncertain generic/comparison dimensions stay object.
- Declaration matching requires an assignment distinct from `==` and excludes
  control heads. Keep the `return obj1 == 36` regression: it must not block
  `char character1`.
- A first-use bare assignment declares its temp from the same tracked-type
  lookup as `var` lines, with scope-aware re-declaration in sibling blocks.
  A zero-literal RHS becomes `= default` only for zero-valued numerics under
  a type it cannot spell; nonzero literals keep their faithful value.
- `_strip_dangling_default` keeps any `: default` governed by a live `?`
  mark at an open paren depth. A call's parens or commas inside the true
  arm (`c ? Foo(a, b) : default`) are not region boundaries; `??`/`?.`/
  nullable `?` never open an arm. Do not restore the flat reset: it
  orphaned 26 false arms into unparseable `? call() ;` (fix 97e).
- The unregistered native sqrt/domain wrapper is accepted only as one unique
  structurally matching unknown target: bounded executable extent, XMM0 double
  spill/reload, `SQRTSD`, RIP-relative `"sqrt"`, and `RET`. Never hardcode its
  address or infer it from a managed method name.
- Packed conversion/root/narrowing instructions scalarize only at IPs recorded
  by `_sqrt_low_lane_sites` after the exact `UCOMISD; JA helper; SQRTPD` diamond
  is proved. The helper arm's scalar XMM0 ABI is the high-lane-dead proof;
  unpaired packed SIMD remains conservative.
- `_return_value_register` is the shared Win64 return rule: by-value R4/R8 use
  XMM0; integer/object/pointer/generic and byref R4/R8 use RAX. Keep structured
  RET, flat fallback, direct-call results, and indirect tails consistent.
- A natural-loop header with statements, or with both successors inside the
  loop, is executed through `_seq` inside `while (true)`. Never move its reads,
  calls, copies, or branch before the loop: the header runs on entry and every
  back edge. `_enter_stop`, `_active_loop_header`, and suppressed-start-label
  controls are narrow internal mechanisms for exactly that one header visit.
- `_memory_rhs_needs_loop_guard` guards unresolved/potential indirect control
  flow, not modeled direct back edges. Do not reintroduce the frozen ReadSpan
  fallback. Cyclic array allocation remains separately guarded until dominance,
  per-iteration identity, and alias lifetime are proved.
- `_loop_shared_entry_gate` may fold only the exact single-predecessor,
  statement-free gate with one shared in-loop target, one exit, no edge phi
  copies, and no pad/SEH boundary. Otherwise retain conservative CFG output.
- `_replay_consumed_linear_to_stop` proves the entire consumed acyclic,
  single-successor path to the current exact stop before emitting any duplicate.
  Do not turn this into speculative region cloning or allow entry/pad/SEH
  crossings; failure must remain atomic.
- The corpus still has 8,071 into-block gotos in 2,048 methods. Net reductions
  do not erase the 83 method-level increases recorded in
  `validation_reports/review80/structural_delta_summary.json`.
- `_shared_sret_receiver_target` proves a common two-pointer Win64 ABI across
  every candidate and matches RDX's exact pointee. RCX is the output buffer,
  never receiver evidence. Unknown sizes/generics/mixed layouts stay unresolved.
- `_array_allocation` creates one typed identity per instruction only when the
  CFG proves the required acyclic lifetime. String-array LEAs retain their
  element address so local plain-store/GC-barrier twins collapse; never replace
  this with global textual deduplication.
- SQRTSS narrows Math.Sqrt to float; SQRTSD remains double. The proved packed
  low-lane/helper family follows the stricter Review 81 rules above; general
  packed SIMD/vector tracking remains open. Generated projects allow unsafe.
- Resolved direct calls/tails rebuild Win64 positions, ignore stale GPR/XMM
  noise, recover contiguous stack args, and preserve fixed-frame `rsp` slot
  identity. Broader shared/virtual/indirect ABI recovery remains open.
- Preserve Review 78's Boolean-byte stores, old-value aliases, array type hints,
  and exact all-candidate static-conversion gate.
- `_decl_type_of` may close an open-generic tracked hint (structural VAR/MVAR
  proof) over the same line's closed `new` RHS only for the same generic
  definition (same short base, same arity) with argument-position openness
  agreement — qualified names like `TMPro.X` are closed, never params.
- `_drop_dead_locals` re-runs on post-`_render` lines (fix 99): `_render`
  drops empty pure-cond `if`s and orphans their pure loads, so the second run
  is load-bearing. Never remove it as "redundant" with the pre-render run.
- A `mov r64,rsp` frame copy carries the frame offset (`_stack_offset` on a
  `?`-text ptr) instead of dropping to `None`, so `[copy+N]` keys slots by
  absolute address and aliases `[rsp+M]` of the same home; arithmetic, indexed,
  and 32-bit uses decline to the unknown-base shapes. RBP never takes a copy
  offset (`mov rbp,rsp` keeps the unreadable frame idiom): the frame path owns
  its disp keys, and absolute tracking there splits homes (stash-proven on
  80548) — RBP behavior is byte-identical with or without copies live.
- Same-typedef shared-body twins (e.g. Transform get_parent triple) keep the
  honest marker: no receiver proof can split one declaring typedef, and
  consensus typing never resolves identity.
- Array-typed receivers resolve through the System.Array typedef
  (`_system_array_td`, unique-or-decline like `_system_object_td`):
  arrays have no subclasses and Array owns their instance dispatch, so
  rank/element openness cannot change Clone/CopyTo identity. Byref
  markers and missing/ambiguous Array rows decline; the sret-clear,
  ctor, generic, and `len(hits)==1` gates run unchanged at all three
  chain-filter twins.
- `_rename_locals` never mints an obj/num/flag/real name already used in
  the lines or declared as a metadata parameter (124140: s_8/v4 became
  obj1/obj2, shadowing the params, and `_copy_prop` merged the dropped
  argument). Reserve-then-bump, mirroring `_semantic_local_names`.
- `_rename_locals` never renames a token matching a metadata parameter
  name (113041: body params v0/v1 became unbound obj5/obj6 while the
  emitter kept v0/v1). Parameters already declare their names; a lifter
  temp sharing the spelling keeps its honest lift-stage name.
- Textual interface dispatch names a call only when the slot-address
  assignment, a span-referenced `typeof()` decl, an exact single
  in-range metadata method, and a shaped receiver all agree
  (25368: GetEnumerator/MoveNext/Current). `_N` display arity falls
  back to `` `N `` metadata names only after the exact key misses.
- A boxed bool from a proved-bool dispatch folds its null test
  (`object X = call; if (X == null)` to `bool X; if (!X)`), recorded
  at naming time and folded post-semantic-names with all-uses-bool,
  single-decl, and standalone-head gates; anything else keeps the
  boxed shape.

All package sources under `il2cpp/` are CRLF with no BOM; the root
`il2csharp.py` launcher is CRLF and retains its UTF-8 BOM. A regression test
(`tests/test_source_format.py`) enforces this contract. **509 tests pass** (391 portable + 118 game;
358 at the Review 84 baseline).
`goldens_review77.json`, `goldens_review79.json`,
`goldens_review80.json`, `goldens_review82.json`, and `goldens_review83.json` are
archived unchanged. Current `goldens_review84.json` uses the same 64 MethodDefs:
56 bodies are unchanged from Review 83 and eight reviewed bodies recover exact
constructor/allocation behavior (Reviews 85–89 regenerate with only name-only deltas,
fix 97 with declaration-only deltas, fix 97e with 0 body changes, fix 99 with 6 reviewed
dead-typeof removals: see `docs/todo.md` Current work).

Use `tools/csharp_smoke.py` for the .NET 8 compiled-pattern checks, including the
actual loop emitter. They passed for Review 80 but were not rerun for Reviews
81–97 (or the package split, which `work/split/rebuild_verify.py` proves byte-identical)
because this environment has no .NET SDK; they are never a build of the
complete recovered game. The supplied game fixtures are tracked via Git LFS
while this repo stays private; they were added at the user's request —
never make the repo public without removing them first.

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`il2csharp` is a from-scratch IL2CPP → C# decompiler: `global-metadata.dat` +
`GameAssembly.dll`/`libil2cpp.so` in, a real source tree out, with every
method body lifted from native x64 code (not just signatures). The code lives
in the `il2cpp/` package (split out of the former `il2csharp.py` +
`decompiler.py` monoliths on 2026-09-12, with byte-identical output):

- `il2cpp/metadata.py`, `binary.py` — `global-metadata.dat` and PE/ELF frontends
- `il2cpp/runtime/` — the `Il2Cpp` registration/usage-slot/EH4 decoder,
  composed from `registration`, `types`, `fields`, `eh` mixins (`core.py`
  holds the class; `meta.py` holds import-free leaf helpers)
- `il2cpp/lifter/` — the `Lifter` (symbolic x64 execution over `iced-x86`),
  composed from `state`, `values`, `insn`, `calls`, `render` mixins
- `il2cpp/dec/` — CFG construction and the structured `Decompiler`:
  control-flow recovery, the SEH region stack, and the ~20-stage statement
  post-processing pipeline, composed from ten mixins (`build`, `analyze`,
  `structure`, `sugar`, `seh`, `flow`, `dataflow`, `highlevel`, `textpass`,
  `emit`)
- `il2cpp/emitter.py`, `headers.py`, `cli.py` — output assembly and the CLI;
  `arm64.py`/`arm64_dec.py` hold the ARM64 scaffold

Every public name is re-exported from `il2cpp/__init__.py`, so
`from il2cpp import Lifter, Decompiler, Il2Cpp` works.
`README.md` documents, in detail, what native constructs recover as what C#
— read it before assuming a construct is unhandled.

## Repo layout (2026-09-08 consolidation)

Project root is `il2csharp/` itself. The old parent folder held a sibling
`work/` (20 files, now merged into `work/`), five loose scripts (now in
`tools/`: `compare_content.py`, `compare_outputs.py`, `count_diffs.py`,
`test_import.py`, `test_import2.py`), and the game folder (now
`testgame/`, tracked via Git LFS in this private repo). Pre-consolidation history in `docs/archive/`
still refers to `../work/`, `il2csharp/final_out/`, sibling `bXX_out1`
trees, and `Shift At Midnight` at the old root — read those as `work/`,
`final_out/`, reaped batch trees, and `testgame/`. Backup zips live in the
parent folder, not in this repo.

## Commands

There is no build step — the decompiler itself is the `il2cpp/` package plus
scratch/validation scripts (`il2csharp.py` is a thin launcher), run directly. There IS a test suite now:
`tests/` (portable unit tests plus optional game-backed goldens, see
`docs/reviews/REVIEW84.md` and `docs/todo.md`), run with `PYTHONHASHSEED=0 python -m pytest -m "not game"`
(portable only) or `PYTHONHASHSEED=0 python -m pytest` with
`IL2CSHARP_METADATA`/`IL2CSHARP_BINARY` pointing at `testgame/`.
Dependencies are pinned in `requirements.txt` / `requirements-dev.txt`
(`requirements-arm64.txt` for the ARM64 scaffold).

```
python il2csharp.py <game-dir-or-metadata> -o <outdir> [options]   # or: python -m il2cpp
  --only NAMES     comma-separated assembly filters (substring), e.g. Assembly-CSharp
  --decls-only     signatures only, skip body lifting
  --max-methods N  cap lifted bodies (debug)
  --probe          diagnostics: registrations + modules, no output files
```

Requires `iced-x86` (`pip install iced-x86`). Syntax-check a change with
`python -c "import compileall,sys; sys.exit(0 if compileall.compile_dir('il2cpp', quiet=1) else 1)"`
before running anything — it's instant and catches typos before a
multi-minute rebuild does. `python -c "import il2cpp"` additionally catches
import cycles, which the package layout can reintroduce.

**All source files under `il2cpp/` are CRLF with no BOM; the root `il2csharp.py` launcher is CRLF+BOM.**
A read-text/write-text edit in Python silently rewrites the whole file to LF — a ~6,000-line phantom diff that
buries the real change. **`sed -i` does exactly the same thing** (batch
50), as will any tool that rewrites the file wholesale. Edit them with
binary read/write (`work/patches/patch_*.py` are the pattern) and check
`d.count(b'\r\n')` against `d.count(b'\n')` afterwards — after *any*
touch, including a one-word comment change. The `.md` files here are LF;
don't cross the two.
**Rewrite scripts must never open the target for writing until every
assertion has passed on the fully-built content** — `open(p, 'wb')
.write(f())` evaluates `open` first, so a raising `f()` leaves a
zero-byte file behind (batch 72's A/B lost decompiler.py exactly this
way; see `docs/archive/batches-c.md` §0ap's incident record). Build in memory, assert,
then write once; make backups once and never re-derive them from the
live file.

**The real target for validation** is a licensed Windows build of *Shift At
Midnight* (Kwalee), metadata v31, x64, kept in `testgame/`
(tracked via Git LFS; private repo only — never publicly redistributed
and never make the repo public without removing the fixtures). A Unity 2022 sample
(`Simple_2022_3_35`) under `temptools/Cpp2IL/TestFiles/` is a second,
smaller data point when that external checkout is present (it is not
bundled with this repo). There's no synthetic/bundled test fixture — every claim
about output correctness in this codebase's own commit history was checked
against one of these two real binaries, not asserted from reading code.

### Validating a change

1. A **direct re-lift** of one method is the fast loop — see
   `work/` (now grouped into `lib/`, `runners/`, etc.; routing table in `work/README.md`;
   the old sibling `../work/` was merged into this repo on 2026-09-08) for the pattern: load
   `Metadata`/`Il2Cpp`/`Lifter`/`Decompiler`, find a method by VA in
   `meta.methods`, call `dec.lift_method(m, td)`, print. No file I/O.
1b. **Golden snapshot tests** (batch 38, backlog #6): `PYTHONHASHSEED=0
   pytest work/lib/test_goldens.py` re-lifts ~50 frozen bodies (every
   batch-writeup ground-truth VA + a deterministic spread) and diffs
   them against `work/goldens.json` — ~13s including the metadata
   load, and it sees wrong-but-parseable output the gates can't.
   Regenerate with `work/lib/make_goldens.py` ONLY after a gated build,
   and read the diff before accepting it; the goldens pin whatever the
   current source produces, bugs included. Goldens key on the
   MethodDef row (`mi`), never the VA — shared-body VAs are ambiguous.
   Historical b76 suite: 50/50 at the gated `work/artifacts/ts_gate_b76_out1.txt` build (regenerated at b75;
   batches 75-76 moved none of the 50 -- 75's 8 phi renumberings were
   read then frozen, 76's classinst shapes are unsampled; pinned by
   `work/batches/b76_test.py` 16/16 instead). Do NOT regenerate
   off unbuilt source.
   SAMPLE-SIZE CAVEAT (batch 42): the suite is 50 bodies — a
   structural pass change touching ~6k methods (5% of the corpus)
   moved only 5/50 of them. For statement-pass soundness changes, the
   golden suite finds the SHAPE of a wrong transformation, the
   full-corpus sweep (item 3) sizes it — run both before a build.
2. A **tree-sitter parse gate** (`work/lib/ts_gate.py` in this repo, pip:
   `tree-sitter tree-sitter-c-sharp`) is the gate that sees what brace
   counting can't (bare `do {}`, NUL/`...` in statements, missing call
   parens, illegal identifiers, unlexable literals). Historical corpus:
   `b74_out1` — **0 bad files / 0 ERROR / 0 MISSING** (held since batch
   53, `docs/archive/batches-d.md` §0ag; batch 75 has no build yet, so there is nothing
   newer to gate). The legacy-TMP pair that had been the ONLY two bad
   files for ~35 batches was never a decompiler defect: both methods
   exceeded the 1500-block CFG cap and fell to the linear flat lift,
   which bypasses `_final_text`. Raising the cap to 3000 (batch 53's
   fix 63b — exactly three methods corpus-wide sit between the two)
   cleared both. Historical trajectory: 2/2,206/4 at batch 52,
   2/4,864/4 at batch 42, 2/7,919/2 at batch 36, 2/7,924/2 at batch
   35, 2/8,125/2 at batches 32-34, 13/8,148/4 at batch 28, 16/15/2 at
   batch 22, 183/118/193 at batch 19, 302/427/210 at batch 18,
   708/2,261/487 pre-batch-17.
   A clean gate raises the stakes on the OTHER checks rather than
   lowering them: a parse gate at zero can only tell you a change made
   something unparseable, never that it made something wrong. The
   goldens, the sweep and reading real output carry the rest.
   NOTE: `ts_gate.py` prints to stdout — redirect to a file (the
   repo's `work/` keeps the saved `ts_gate_*.txt` reports) if you want
   a report to diff. Current gate numbers live in `docs/reviews/REVIEW80.md` and
   validation_reports/review80/; older numbers here are history. Always bucket by row text — whole file-span rows (L1
   headers, `internal sealed partial class`) inflate counts, and ONE
   unparseable line can cascade over a whole file (batch 19 hit 81
   ERROR nodes in Timer.cs off a single bad condition), so a big
   per-file count usually means one defect, not many. When the bad-file
   set is unchanged between two gates, every ERROR delta is confined to
   those files — that IS the per-file diff (used this way at batch 35).
   `work/lib/gate_diff.py A.txt B.txt` diffs two saved
   reports per file (newly-bad / cleared / worse / better) — always run
   it when you have saved reports, the summary line alone hides a
   regression under a bigger win.
   Note: `_final_text`'s line-local transforms are mirrored in
   `work/lib/sim_rewrite.py` — a built tree + ~2 min sim re-gate is the
   fast full-corpus loop for `?`/`unknown`/`default`/select-family
   changes, but a REAL rebuild (~7-9 min, a `work/runners/run_build_*.py` into
   `<out>`) is the only truth for Lifter-side changes. Two traps in
   that loop, both paid for in batch 19:
   - **A sim tree may only be compared against another sim tree.**
     `sim_rewrite.py` does not mirror `_fix_select`, so it strips
     `: default` that the real pipeline re-synthesizes; a sim-vs-built
     diff shows ~80 phantom regressions. `work/lib/make_sim_base.py`
     generates the old-rules control to diff against.
   - **Measure a rule's hazards against what ENTERS the pass, not the
     tree it already produced.** A built tree has the old rule's output
     baked in, so a shape the old rule collapsed reads as "0 sites"
     right up until the new rule stops collapsing it.
3. A **full-corpus in-memory sweep** (iterate every method with native
   code, wrap `lift_method` in try/except, no file writes) catches
   crashes/regressions across all ~116k bodies in a couple of minutes —
   much faster than a file-writing rebuild, and it's how the two most
   subtle bugs found in this codebase's history were actually caught
   (a silently-crashing regex, and a brace-balance regression neither the
   crash count nor the per-file audit below could see on its own).
   `work/lib/sweep_audit.py <tag>` is the driver: per-method literal-aware
   counts of `brace`, `dangling` (goto with no label), `into_block`
   (goto into a nested block), `empty_arg` (`f(a, , b)`), `follower`, and
   crashes — batch 15's gates. Known baseline at b74_out1: 0 / 0 /
   13,505 / 0 / 0 / 0 (sites/methods for into_block: 13,505/2,978;
   driver now `work/lib/sweep_1a_audit.py`). into_block history: 21,326 (batch 20) ->
   21,464 (batch 21, explained uptick) -> 17,718 (the shared-tail
   hoist pass, batches 12-15 era baseline through b41) -> 32,094
   (batch 42: the funnel applied to classic hoists un-did ~14.4k
   hoists proven unsound by disassembly — the deliberate, documented
   honesty cost, `docs/archive/batches-e.md` §0v; recovery paths sized as todo leads 1a/2)
   -> 15,419 (batch 43's tail duplication) -> 12,950 at b63_out1
   -> 13,815/2,960 (batch 54's second-table recovery) -> 13,505/2,978
   (batch 55's bound/group-table fixes, held through b74) ->
   13,518/2,979 (batch 75, `work/sweep_b75b.log` with the fold
   active: +13/+1 off b74, +63,252 lines net of phi materialization
   and fold collapse).
   **Crashes are 0 as of batch 53** (`docs/archive/batches-d.md` §0ag): the two
   long-standing cfg-too-large caps in
   TextMeshPro/TextMeshProUGUI.GenerateTextMesh cleared when fix 63b
   raised the block cap 1500 -> 3000, so ANY crash in a sweep from now
   on is one you introduced.
4. A **full rebuild + brace audit** (`python il2csharp.py <target> -o
   <outdir>`, then `python work/lib/tree_brace_audit.py <outdir>`) is the
   final gate before promoting a build to the baseline. Note its blind
   spot: it sums `{`/`}` counts per **file**, so a `try { } else { }`
   (individually balanced brace pairs, invalid C#) or two compensating
   errors in the same file both read as 0. Prefer the full-corpus
   sweep's **per-method** count when chasing structural bugs
   specifically — and that count MUST be literal-aware:
   `work/lib/sweep_trybrace.py`'s `brace_delta()` skips braces inside
   string/char literals and `/* */` comments, because a naive
   `l.count('{') - l.count('}')` counts `"BitVector32{"`-style literals
   as imbalance (all 24 "imbalanced" methods in batch 13 were that false
   positive; literal-aware count is 0). The `try { } else { }`
   malformation class itself is now 0 sites tree-wide (was 389 pre-batch
   12); the one surviving try-structure artifact is a switch-reached
   +3-open region in CustomAttributeTypedArgument.ToString,
   byte-identical across prev12/prev13 — see `docs/reference.md` §6 (Known
   artifacts).
5. **Baselines.** The current release baseline is Review 84 `final_out/`,
   documented in `docs/archive/reviews-log.md` §0bb and `docs/todo.md`'s head. The following promotion
   chronology is historical, not an instruction to use the older trees. `final_out/` **was
   promoted to `b42_out1` on 2026-08-22** (batch 42, gated 2/4,864/4 —
   the documented TMP pair only; byte-verified copy); the gated
    candidate is now **`b76_out1` (batches 43-76, gate 0/0/0)**;
    `b74_out1`/`b75_out1` are superseded (`b75_out1` gate 0/0/0 --
    do not regenerate goldens off unbuilt source). Review 77 (`docs/reviews/REVIEW.md`,
    2026-09-08) advanced the SOURCE past b76 (tail-arg recovery,
    renderer ordering, CLI + instrumentation, portable validator kit;
    validation table 11,107 / 115,658 / 0 failed, gate 0/0/0) WITHOUT
    promoting -- b76_out1 is still the gated candidate, promotion is a
    human call. The 2026-09-08 `final_out/` disk tree is a PARTIAL
    aborted rebuild (6 assemblies, Review-77 source -- `docs/archive/batches-c.md` §0au),
    not a candidate and not a baseline.
   The promotion
   pass reaped the batch trees one level up (`b37_out1`-`b42_out1`)
   and the work-dir archaeology tied to reaped trees (old build logs,
   gate reports, site dumps, one-shot `run_build_*` scripts, the
   frozen batch-21 source snapshots, `__pycache__`/`.pytest_cache`);
   the provenance records (`patch_*.py`, `fix_*.py`, probes,
   censuses, tests, the current build log and gate report) were kept.
   The previous promotion (b36_out2, 2026-08-21) had already deleted
   the `b18_noreind`-through-`b36_out1` chain and the
   `final_out_prev18/` archive — nothing is kept for A/B below
   `final_out/`. To isolate one change's *own* effect,
   re-run the build against a copy of the source with just that change
   reverted, then diff.
6. `PYTHONHASHSEED` nondeterminism is a known, historical class of bug in
   this codebase (dict/set iteration ordering leaking into generated temp
   names) — if a diff looks unrelated to your change, check whether it
   reproduces with a fixed hash seed before assuming you caused it.

Read `docs/todo.md` (open work only) before starting nontrivial work, and
`docs/` for the state record — `docs/todo.md` holds current work, `docs/reference.md`
the working-loop rules (§4), baselines/promotion/known artifacts (§6) and
gotchas (§7), and `docs/archive/` the review log, batch writeups (§0b–§0r),
archived numbers (§1), backlog trail (§3) and compressed history (§8); every
`§NN` cross-reference in the repo resolves against those files (map in
`docs/README.md`). They record what was just tried, including reverted attempts and *why*
they were reverted, which matters as much as what shipped.

## Architecture

**Pipeline**: `Metadata` (parses `global-metadata.dat` tables) +
`load_binary` (PE/ELF, locates `Il2CppCodeRegistration`/
`Il2CppMetadataRegistration` by structural validation, not a version
lookup) → `Il2Cpp` (joins them: method addressing, usage-slot decoding,
vtables, EH tables, generic instantiation) → `Lifter` (per-method: decode
the real instruction extent — not a linear byte prefix — build a CFG,
symbolically execute twice: a dry pass to discover phi-merge locations,
then a real pass that emits statements with types carried through). Method
values are `Expr` (text + il2cpp type tuple + a coarse kind like `obj`/
`int`/`ptr`); the register file is a dict subclass that counts *renderings*
per expression object so a value used twice gets bound to a named temp at
its definition instead of re-printing its whole expression text at each use
(`_bind`), and a store invalidates the text of every live expression that
reads the stored location (`_kill_stale`) so re-rendered text can't
silently pick up a post-store value.

**`Decompiler`** (in `il2cpp/dec/`, mixin `dec/structure.py` + `flow.py` + `dataflow.py` + …) takes the Lifter's per-block output
and structures it: dominator/postdominator analysis, natural-loop
detection, `_seq` — a recursive-descent walk that emits `if`/`else`/`while`/
`switch`/`goto` directly rather than building an intermediate AST — followed
by roughly twenty-five statement-list passes (`_structure`) that fold sugar:
`for`, `foreach`, ternary, null-conditional, `lock`, `using`, string
interpolation, compound assignment, dead-code elimination, local renaming,
plus `_switch_synth` (flat `==`-chains -> `switch`), `_drop_dead_lastdef`
and, last, `_delegate_cache_fold` (`CACHE ?? (CACHE = new ...)`).
Passes run in a fixed order and several depend on an earlier one having
already run (e.g. dead-phi-copy removal has to precede `&&`/`||` folding;
the delegate-cache fold runs after `_drop_dead_lastdef` so no later pass
eats its `??`);
check the call sequence at the end of `_structure` before reordering
anything. `_seq`'s jcc handler emits a join-edge phi copy at the END OF
THE TEST BLOCK before the `if` head when that edge IS the join and its
arm reaches the join (fix 75 `pre_edge`); otherwise it keeps the old
after-fork emission. One pass — `_hoist_shared_tails` (after the second
`_resolve_labels`) — eliminates `goto`-into-nested-block sites: it moves a
label's tail out past its construct when every into-goto provably falls
through to the hoist point (no code between, no loop/switch/SEH level
crossed) and every sibling `else` arm ends in flow-break (the funnel
rule). Its soundness predicates are replicated by `work/lib/classify_into2.py`
(per-label census; SOUND = 0 tree-wide after batch 15); treat the
`_falls_to` switch-level rejection and the nested-label guard as load-
bearing — both were root-caused against real wrong output, not taste.

**SEH (`__CxxFrameHandler4`)** is its own subsystem, decoded from ground
truth: `ehdata4_export.h` is a real Microsoft header (not public, but
shipped with any MSVC install — `VC/Tools/MSVC/*/include/`), and this
codebase's EH4 parsing was rewritten against it rather than reverse-engineered
from disassembly. `Il2Cpp._eh4_parse`/`_eh4_ipstates`/`_eh4_try_ranges`/
`_eh4_regions` decode the compressed try/catch/finally tables, including
exact per-try IP ranges where they resolve to one contiguous span (most do;
switch/goto-reached trys with several disjoint spans don't, and use a
structural fallback instead — bridging disjoint spans was tried and
reverted, it can misattribute a sibling try's code). `Decompiler` tracks
**multiple** independent try regions per method as
`self._seh_regions` (a list, outer-to-inner ordered) rather than one — every
consumption point in `_seq` opens/closes *all* matching regions, not one.
This area's one surviving artifact is a switch-reached +3-open region in
CustomAttributeTypedArgument.ToString (byte-identical across
prev12/prev13; the `try { } else { }` class itself is 0 sites tree-wide
now) — see `docs/reference.md` §6 (Known artifacts) before touching region open/close
logic.

**Shared-body call resolution**: MSVC folds byte-identical method bodies
and IL2CPP shares one compiled body across generic instantiations, so a
call's target address can have dozens to thousands of true owners.
`Il2Cpp.addr_candidates` keeps all of them (`addr_to_method` keeps only the
first, for callers that don't care which). Disambiguation walks the
receiver's declaring type up its **base chain** (`Il2Cpp.base_chain_tds`) —
important because a `: base()` constructor's receiver is always the
*derived* type, never the base that actually declares the shared
constructor — or matches a shared generic call's hidden instantiation
argument against a decoded metadata usage slot. When neither settles it,
the honest `sub_x/*shared body, N candidates*/` marker prints instead of a
guess; don't try to make that case "prettier" without a way to actually
prove the target — the alternative is a confidently wrong name (this was
a real, shipped bug before batch 11: `Guid.cs` calling `ReadOnlySpan<Obi.
BurstCollisionMaterial>`). Even the genuinely-ambiguous case isn't fully
unrecoverable, though: every candidate names a call into the literal same
compiled machine code, so they consume the same argument registers no
matter which metadata identity is true (batch 21, fix 21j) — the argument
list is trimmed to the largest declared arity among all candidates
(sound, not a guess at which one is right) instead of keeping every GPR
slot plus whatever stale float-register value survived from earlier in
the method as a bogus extra "argument". Untrimmed, this was read-before-
def's single biggest contributor tree-wide (-6.8% of the whole corpus's
temp count from this one fix) — the `Update()`-is-300-lines-of-`objN`
complaints trace substantially back to it.

**Reference checkouts under `temptools/`** (Cpp2IL, ReforgeIL — external,
not bundled) are *not*
dependencies — nothing here imports from them. They're read for ground
truth on version-gated metadata formats and design patterns (ReforgeIL's
`docs/` in particular documents its own deliberately-unsolved problems,
e.g. RGCTX resolution — useful for knowing what's genuinely hard versus
what's just unattempted before spending time on it).
