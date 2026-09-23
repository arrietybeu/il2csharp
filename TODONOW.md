# TODO NOW — exact remaining output failures and source ownership

Generated 2026-09-22 from the current promoted tree. This is a handoff for
the next agent. The generated C# tree is `final_out/`; do not edit it by hand.
The source of truth is the decompiler under `il2cpp/`. Fixture inputs are
`testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat` and
`testgame/GameAssembly.dll`.

## Baseline gates (r4c promotion, 2026-09-23 — prior numbers archived below)

- Strict rebuild: 114,458 bodies, 0 failures, 0 fallbacks (matches).
- Brace audit: 0 unbalanced files. Parse gate: 0 bad / 0 ERROR / 0 MISSING.
- Full suite: 933 passed, 0 failed (first fully-green run; 67525
  regened to the signature-exact composite).
- `final_out/` is promoted output and must remain read-only.
- The fixture is private/licensed; never redistribute it.

## Exact fresh census of `final_out/`

All paths below are relative to `C:\Users\crax\Downloads\il2csharp`.
The count is occurrences/lines first and distinct `.cs` files second.

| category | promoted r4c scan | 2026-09-22 handoff figure | exact output root |
|---|---:|---:|---|
| shared-body marker `/*shared body, N candidates*/` | 18,884 / 2,278 | 19,013 / 2,304 | `final_out/**/*.cs` |
| `/*indirect*/` | 6,262 / 884 | 7,091 / 975 | `final_out/**/*.cs` |
| literal `unknown` | 15,655 / 1,361 | 16,044 / 1,382 | `final_out/**/*.cs` |
| raw `mem[N]` | 398 / 127 | ~13,189 / 805 | `final_out/**/*.cs` |
| `mem_<hex>` load twins | 359 / 95 strict (`mem_addr` params excluded) | 234 / 69 | `final_out/**/*.cs` |
| `goto` | 8,707 / 903 | 8,705 / 901 | `final_out/**/*.cs` |
| `/* nothing */` | 63 / 1 | 63 / — | `final_out/**/*.cs` |
| `?addr` | 1 / 1 | 22 / 6 | `final_out/**/*.cs` |

`?addr` follow-up (unpromoted): the last site (mi 65244) was our own
quarantine over-firing on a named `&s_1d0` home, so the declines were
narrowed to text-`?` bases and the store rescued -- then the rescue
was traced and disproved (rendered base aliases a reused home while
native uses a fresh address; address-of lost in write-barrier
conversion), and reverted byte-identically with the elision pinned by
a game test. `?addr` stays 1, honestly.

The differences are scanner-definition differences, not silently ignored
files: use the commands in the Census reproducibility section. In particular,
`unknown` can be counted as tokens, lines, or diagnostic hits; `?addr` can be
counted in historical reports rather than the promoted tree; and the shared
body/goto totals have changed by small formatting/regen deltas.

## 1. Runtime-broken — shared-body calls

### Exact files

Every affected file is under `final_out/` and matches the shared-body marker.
There are 2,304 distinct files. The exact complete inventory is reproducible
with the first command below; do not use a hand-curated sample as the scope.

### Source ownership

- Primary renderer: `il2cpp/lifter/calls.py:925` — emits
  `sub_%x/*shared body, %d candidates*/` when the native VA has multiple
  metadata owners.
- Shared-call pipeline and candidate/ABI logic: `il2cpp/lifter/calls.py`
  (especially the shared-call sections around lines 84, 1345, 1600, and
  1964–2051).
- Receiver/type lookup and shared target metadata: `il2cpp/runtime/core.py`,
  `il2cpp/runtime/registration.py`, `il2cpp/runtime/types.py`.
- Call-site analysis/indirect-tail handoff: `il2cpp/dec/analyze.py:180–205`.

### Why it is broken

The output names a native shared body but cannot select the concrete managed
MethodDef at the call site. It is therefore not a callable C# declaration;
the unresolved target throws at runtime. The honest spelling must remain for
ambiguous cases until receiver type, generic instantiation, ABI, and owner
proof all agree.

### Required fix direction

Implement receiver-type resolution at the call site, not a global VA rename.
Preserve all-candidate consensus rules, open-generic rejection, shared sret
rules, and the 15 conservative constructor leftovers documented in
`CLAUDE.md`. Add negative tests for ambiguous receivers and shared addresses.

## 2. Runtime-broken — indirect calls

### Exact files

975 files under `final_out/` contain 7,091 `/*indirect*/` occurrences.
Generate the complete path list with the second census command below.

### Source ownership

- Indirect call rendering: `il2cpp/lifter/calls.py:1139–1141` and
  `il2cpp/lifter/calls.py:1521`.
- Virtual/interface unresolved dispatch: `il2cpp/lifter/calls.py:1964–2051`.
- Indirect memory/control-flow classification: `il2cpp/lifter/insn.py:1231–1234`.
- CFG safety/unknown indirect control flow: `il2cpp/dec/build.py:25–44` and
  `il2cpp/dec/analyze.py:180–205`.
- Higher-level dispatch folding (must decline when proof is absent):
  `il2cpp/dec/flow.py:917–920` and `il2cpp/dec/sugar.py:328`.

### Required fix direction

Same fix family as shared bodies: infer the receiver/interface slot and exact
closed MethodDef from metadata plus native evidence. Do not resolve by helper
VA, class name, or majority candidate. Preserve `/*indirect*/` when proof is
missing.

## 3. Compile-broken — unknown values

### Exact files

Fresh token scan: 12,084 `unknown` tokens in 1,383 files under
`final_out/`. The historical handoff reports 16,044 hits/1,382 files because
its hit definition includes additional unknown-value diagnostics. Treat the
union of both scans as the investigation scope.

### Source ownership and producer families

- Unknown minting: `il2cpp/lifter/state.py:1131–1132` (`_fresh_unknowns`).
- Register/value propagation: `il2cpp/lifter/state.py`,
  `il2cpp/lifter/values.py`, `il2cpp/lifter/aggregates.py`.
- Unknown call results and ABI fallback: `il2cpp/lifter/calls.py:1185–1262`.
- Unknown memory operands: `il2cpp/lifter/insn.py:1675–1695`.
- Unknown cleanup/rendering: `il2cpp/dec/textpass.py:458–529` and
  `il2cpp/dec/textpass.py:599`.

### Known remainder classes

1. stale stack tiles surviving copies/merges;
2. SIMD/vector lanes not carried through spills, `UNPCK*`, or calls;
3. unknown results from unresolved shared/indirect calls;
4. genuine unknown branch conditions and pointer bases.

Fix producers and provenance; never replace `unknown` textually with zero,
`default`, or a guessed type.

## 4. Compile-broken — raw `mem[N]` stores and `mem_xx` loads

### Exact files

- `mem[N]`: 13,189 occurrences in 805 files under `final_out/`.
- `mem_<hex>`: 324 occurrences in 70 files by the current broad scan; the
  handoff's narrower load-twin census is 234/69.

### Exact source

- `il2cpp/lifter/insn.py:1345`: load fallback returns `Expr('mem_%x' % disp,
  None, 'ptr')` when the base register is untracked.
- `il2cpp/lifter/insn.py:1349`: `_mem_lvalue` begins raw-store generation.
- `il2cpp/lifter/insn.py:1379`: `if be is None: return 'mem[%d]' % sdisp(disp)`.
- Store consumers: `il2cpp/lifter/insn.py:1695–1787`.
- Raw-width/type tests and intended conservative behavior:
  `tests/test_review102_raw_store_widths.py:251–359`.

### Required fix direction

Recover the base register/aggregate provenance and declared pointee width
before emitting a named field or typed pointer. A raw store is currently an
undeclared C# identifier and therefore a compile error. Do not make up fields
from displacement alone; preserve raw output when ownership/layout is not
proved.

## 5. Compile-broken — unbound temps

### Exact files

Upper bound: up to 8,700 tokens across as many as 2,200 output files. This is
not a clean compiler count: it includes false positives such as multi-
declarations and identifiers introduced in a branch whose declaration is
outside the textual region. The exact candidate path inventory is produced by
the unbound-temp command below.

### Source ownership

- Register/stack seed and copy state: `il2cpp/lifter/state.py`,
  `il2cpp/lifter/values.py`, `il2cpp/lifter/aggregates.py`.
- Phi/merge materialization and copies: `il2cpp/dec/analyze.py:448–510`.
- Declaration/use binding and dead-local cleanup:
  `il2cpp/dec/dataflow.py`, `il2cpp/dec/emit.py`, `il2cpp/dec/textpass.py`.
- Final semantic names (must not invent type evidence):
  `il2cpp/dec/emit.py` / `_semantic_local_names` and the invariants in
  `CLAUDE.md`.

### Required fix direction

Trace each candidate to its native definition, stack home, phi edge, or call
result. Fix the producer/provenance and scope merge. Do not globally declare
all `objN` names or substitute `default`; that would hide missing native
values and create runtime corruption.

## 6–11. Resolved or harness artifacts — do not re-investigate

- Duplicate members: genuine intra-assembly duplicates were fixed by
  conversion-operator emission. Remaining CS0101/CS0111/CS0102 spikes are
  cross-assembly BCL twins caused by the single-assembly harness. See
  `il2cpp/emitter.py` and the Roslyn ledger in `nowtodo.md` Addenda 14–15.
- Enum/int edges: fixed by enum-aware `(E)v` casts, underlying declarations,
  parentheses, and `unchecked`; verify with Roslyn only. Do not reopen.
- Finalizers: fixed in `il2cpp/headers.py`/signature emission; exact `~X()`
  output is already covered. Do not reopen.
- Optional parameter order: fixed in parameter emission (`= default` for
  dropped trailing null rows; genuine mid-default rows stripped). Do not
  reorder parameters.
- CS0115 bad overrides: harness artifact; adding Mono.Security to the check
  scope reduces the reported 14 to zero.
- `_1<T>` qualifier remainder: harness artifact; declarations live in
  uncompiled Fusion directories.

## 12–15. Cosmetic/by-design — do not spend fix effort

- `goto`: current scan 8,707/903; compiles and represents unresolved
  unstructured control flow. Emitter/structured pipeline is under
  `il2cpp/dec/structure.py`, `flow.py`, and `emit.py`.
- `/* nothing */`: 63 occurrences in one file; intentional empty bodies.
- `__SharedBodyStubs`: throwing stubs are intentional behavior for unresolved
  runtime targets; see `il2cpp/emitter.py` stub generation.
- `?addr`: current promoted tree has only 2 occurrences in 2 files; nearly
  extinct and not a priority.

## Census reproducibility (PowerShell, from repository root)

```powershell
$out = 'final_out'
rg -n --glob '*.cs' 'sub_[0-9A-Fa-fx]+/\*shared body, [0-9]+ candidates\*/' $out
rg -n --glob '*.cs' '/\*indirect\*/' $out
rg -n --glob '*.cs' '\bunknown\b' $out
rg -n --glob '*.cs' '\bmem\[[^]]+\]' $out
rg -n --glob '*.cs' '\bmem_[A-Za-z0-9_]+' $out
rg -n --glob '*.cs' '\bgoto\b' $out
rg -n --glob '*.cs' '/\* nothing \*/' $out
rg -n --glob '*.cs' '\?addr' $out
```

To obtain exact distinct paths for any category, pipe a command's output
through this PowerShell expression (it preserves the `file:line:text` output
for follow-up inspection):

```powershell
$hits = rg -n --glob '*.cs' '/\*indirect\*/' final_out
$hits | ForEach-Object { ($_ -split ':',3)[0] } | Sort-Object -Unique
```

Replace the pattern with the other marker. For source ownership, use
`rg -n` against the exact files listed above; line numbers are current source
line anchors and must be rechecked after edits.

## Work order for the fixing agent (status as of r4c promotion)

1. Inventory: done (census table above, re-counted at promotion).
2. Shared-body receiver resolution + indirect/interface dispatch:
   landed as proof-driven slices (array receivers, twins pins,
   interface dispatch); hinted receivers and generic substitution
   disproved/deferred with evidence (see addenda).
3. Unknown values + raw memory: landed as provenance slices (RSP-copy
   homes, SIMD consumer-side tails + direct); general packed tracking
   stays declined.
4. Unbound temps: classified (55 distinct in 21 files, all params or
   checker FPs in fresh lifts) and fixed (rename barrier + param
   exclusion); actionable set ~zero.
5. Gates + suite: 932 passed / 0 failed (first fully-green run; the
   old 67525/104428 reds were regened after per-hunk review).
6. Never regenerate or promote `final_out/` without an explicit user call.

## Stop record — 2026-09-22, SIMD/stack provenance follow-up

The decompiler changes are in the primary repository package under
`il2cpp/`; the scripts under
`C:\Users\crax\AppData\Local\Temp\opencode` were tracing/patch helpers only
and are not imported by the project. `final_out/` was not edited, rebuilt, or
promoted.

### Source changes

- `il2cpp/lifter/insn.py`: scalar SSE arithmetic preserves untouched upper
  lanes when the input already carries proved packed provenance. General
  `SHUFPS` recovery was attempted, but reverted after MethodDef 80548 proved
  the same local shape can be integer/index bookkeeping; it remains a
  conservative no-op until stronger use-site proof exists.
- `il2cpp/lifter/aggregates.py`: an offset lane crosses a CFG phi only when
  every predecessor reconstructs the same typed value.
- `il2cpp/lifter/state.py`: use-binding keeps packed-phi provenance reachable
  after a `vN` expression is renamed to a `tN` temp.
- `il2cpp/lifter/values.py`: kill-on-write freezes packed lanes that read an
  overwritten location instead of discarding their provenance.
- `il2cpp/lifter/calls.py`: the early sret-return path now uses the existing
  Win64 positional-argument reconstruction and reconstructs by-value structs
  from stack homes, matching the ordinary resolved-call path.
- `tests/test_recovery_completion.py`: six portable regressions cover
  scalar-lane preservation, unanimous/disputed phi lanes, bind-time
  provenance, and safe/stale kill-on-write lanes.

### MethodDef 104428 (`GraphUpdateShape.GetBounds`)

The two emitted `unknown` arguments are gone. The final native call now has
all six declared parameters present and typed; its first two difference
vectors are reconstructed from the packed XMM/stack tiles, and the 5th+
Win64 arguments are read from the stack home area rather than a stale XMM
tail. The fresh body still differs from the frozen golden (including modern
static-field spelling and the newly recovered aggregate expressions), so
`tests/test_game_goldens.py` remains red for 104428 until that body is
reviewed and an explicit golden-regeneration call is made. Do not blindly
regenerate it.

### Validation at stop

- `python -m compileall -q il2cpp il2csharp.py`: pass.
- Source-format assertions for every touched `il2cpp/lifter/*.py`: CRLF,
  no BOM, pass.
- `git diff --check`: pass.
- Final portable suite: **757 passed, 130 deselected**.
- Focused new tests after that revert: **7 passed**; the only selected failure was the expected
  stale 104428 golden.
- Final full licensed suite: **885 passed / 2 failed**. The only failures are
  the documented stale snapshots for MethodDef 67525 and 104428; no new
  failures were introduced.

### Resume point

Review the fresh 104428 call arguments against the native stores at
`0x18072e410`–`0x18072e456`, then run a direct corpus sweep before considering
a golden update. MethodDef 67525 remains the
documented honest SIMD decline. The broad shared-body, indirect-call,
unknown/raw-memory, and unbound-temp inventories above remain open; this
follow-up fixes one producer family, not the whole census.

## Stop record — 2026-09-22, RSP-copy home round (unpromoted)

Subagent-proposed, human-implemented. Same rules: `final_out/`
untouched (its census above still stands), no snapshot regen, no
promotion, no rebuild. All `il2cpp/` edits via binary patches with
CRLF/no-BOM asserts; `tests/` edits LF (one pre-existing CRLF game
file kept byte-identical in endings).

### Source changes (`il2cpp/lifter/insn.py` only)

- `mov r64,rsp` now carries the frame offset (`_stack_offset` on a
  `?`-text ptr) instead of dropping to `None`, so `[copy+N]` keys slots
  by absolute address and aliases `[rsp+M]` of the same home. Wired
  through `_read_mem`, `_mem_lvalue`, and the `lea` address path;
  arithmetic/index/32-bit uses decline to the unknown-base shapes.
- RBP quarantine (stash-proven): the first cut tracked
  `lea rbp,[rsp-C]`-style frame offsets absolutely and split
  RBP-disp-keyed homes (80548 `int num2` became `object obj1` plus an
  unbound `num2`). RBP stays on the legacy frame paths byte-identically
  (MOV/LEA/load/store/indexed all skip RBP); `aggregates.py` reverted
  untouched. 80548 matches its golden again.
- `tests/test_recovery_completion.py` +4 portable (slot roundtrip +
  cross-delta alias, arithmetic/index/32-bit+RBP declines);
  `tests/test_game_frame_copy.py` new (+3 game: 117615 improvement,
  23900 same-typedef must-decline, both `?addr` extinctions);
  `tests/test_game_review83.py` sret pin evolved to the faithful
  spelling (old site-1 `(default,default,default)` was copy blindness;
  native passes three addresses at `0x182529283`–297).

### Method evidence (each `--mi` re-lifted, base-vs-new diffed)

- 117615 (`WriteInt32AtOffset`): `mem[8] = this;`/`mem_8`/raw twins
  become `this._offsetBits = offset;`/`this.WriteSlow(value, bits);`.
  One undeclared `obj6` phantom survives in the replayed finally tail
  (was three undeclared `mem[8]`/`mem_8`/`obj2`).
- 32837 (`Touchscreen.Reset`): golden holds 4 raw `mem[]` prologue
  spills (`mov rax,rsp` proven); actual drops them, renumber-only
  fallout. NEW red, consigned to regen.
- 108722 (sret): both native address-triples print; unobserved
  stand-downs stay pinned portably (unknown receiver/size).
- 104428: 11 raw `mem[]` spills removed (its golden holds `mem[8]`
  too); same already-red ID, still awaiting the gated-regen user call.
- 80548: quarantine restored the golden byte-identically.
- 82799/104380: the promoted tree's only two `?addr` hits
  (`store into untracked ?addr` in copy-heavy methods) render no
  `?addr` and no `mem[]` in fresh lifts; 82799's `return real2`
  residue is pre-existing (unbound in the old body too).

### Validation at stop

- `python -m compileall -q il2cpp il2csharp.py`: pass.
- Source-format assertions (`insn.py` CRLF/no-BOM): pass.
- `git diff --check`: pass.
- Portable suite: **765 passed** (761 + 4 new), 132 deselected.
- Game pins: `test_game_frame_copy.py` 3/3,
  `test_game_review83.py` 7/7 (with the evolved pin).
- Full licensed suite: **894 passed / 3 failed** — 67525 (honest SIMD
  decline) + 104428 (stale golden) were already red; 32837 is new but
  proved improvement (above). No other breaks.

### Resume point (superseded by r4c promotion — historical record follows)

Work order §4 was completed after this stop record: the unbound census
collapsed to 55 distinct tokens (all params/checker FPs in fresh
lifts) and the rename barrier + param exclusion fixed the producers.
Corpus was rebuilt + regened + promoted twice since (r4a, r4c);
`final_out/` census above is the r4c recount, not this stop record's
era. Remaining work is tracked in `docs/todo.md` Current work.

## Addendum — 2026-09-22, TODONOW #1 first slice (unpromoted)

Array receivers now resolve shared calls (subagent-mined mi 275/326/
4047: 9-candidate Clone fold → `System.Array.Clone` instance rendering;
mi 144 string twins pinned must-decline, 5 markers). Mechanism:
`Il2Cpp._system_array_td` + `Lifter._array_receiver_td` with a 2-line
fallback at all three chain-filter twins; sret/ctor/generic/unanimity
gates untouched. Portable + game pins green; full suite holds the
RSP-copy-round failure set byte-identically (32837/67525/104428 — none
of the four touched methods is in the golden set). Remaining #1 work:
slot/hint-typed receivers, indirect/interface dispatch, then
receiver-driven generic substitution (needs the synthetic table).

## Addendum — 2026-09-22, hinted receivers DISPROVED (reverted clean)

Side-table corroboration (`slot_types` vs per-pass `_type_hints`,
dual-agreement + closed-key) resolved `&raycastHit1`→`distance`
(25687) and `&taskAwaiter1`→`GetResult`/`IsCompleted` (24238) with
correct trims — then reverted with zero residue. Root cause, traced to
the instruction: resolving IsCompleted removed the ambiguous-shape
union-kill that used to clear the `s_50` home tile; the surviving tile
had been field-split by `_scalar_parts` (TaskAwaiter-typed RAX from the
already-resolved `GetAwaiter`), so the whole-struct reload projected
`.m_task` into the TaskAwaiter-typed `<>u__1` home — an ill-typed line
the suite cannot see (same IDs pass either way). Rule: hint-driven
resolution stays out until whole-struct reloads prefer whole tiles
(byte-range sidecar); the `_td_of`/array paths keep their pinned
behavior. Repro/diagnostic probes kept in Temp; post-revert lifts of
25687/24238 are byte-identical to the pre-hint baselines.

## Addendum — 2026-09-22, SIMD consumer-side recovery (unpromoted)

67525's constants died at: scalar-pool loads dropping bytes (vs the
PACKED128 `_bytes` attach) and `unpcklps` lane reads failing untyped,
then tail args reading `.text` only. Fix, tails-only: byte provenance
on scalar const loads + typed GPR-slot materialization at closed
all-float vector slots (house `(float2)(l0,l1)` for
Unity.Mathematics.float2; width-4 literal). 80548 stays intact
(PSRLDQ-popped/integer-tainted values carry no parts -- the guard).
Fresh: `clamp(x, (float2)(0.0f, 0.0f), (float2)(1.0f, 1.0f))`,
signature-exact where the golden scalars needed unprovable implicit
conversions -- golden regened (surgical, SHAs verified). Follow-up:
same gates wired into resolved direct calls via a shared helper
(67836 smoothstep renders composites, uncovered args stay unknown).
Suite 933/0. Open: per-arm Color, general packed tracking.

## Status — end of 2026-09-22 session (paused, tree clean)

Suite: **932 passed / 0 failed** (fully green; 67525 regened to the
signature-exact composite). Last source change: direct-call
float-lane materialization via shared helper (67836 renders
composites, uncovered args stay unknown). Reverted same day:
?-text tightening (rescued store miscompiled -- elision was honest,
now pinned by a game test).
`final_out/` holds the r4a tree (predates SIMD + direct-call);
next rebuild will carry them plus the ?addr-tightening revert
(net: SIMD/direct improvements only).
Open, hardest-first: field-provenance sidecar (designs + two
disproofs on file), general packed SIMD (80548-bounded), per-arm
Color (needs use→def), runtime-generated vtables (decline forever).
No blockers, no red tests, no uncommitted work.

## Addendum — 2026-09-22, unbound census + rename barrier (unpromoted)

Work-order §4 (classify before patching), done as a read-only text
tool (comment/string scrub, method regions, dominance = earlier line
at depth <= use): the ~8,700-token/~2,200-file upper bound collapses
to **55 distinct unbound tokens in 21 files**. Remainder by family:
lift-stage vN residuals (StreamBuffer v0-v7 et al.), tN oversize/bind
temps, SIMD type-position FPs (v128/v64/v256), and one obj-family case
fixed below. The census itself moves no gates.

The obj-family case (mi 124140 `AndroidJNI.IsSameObject`) forwarded
`(obj2, obj2)` for native `(obj1, obj2)`: `_seq` was correct and
`phi_alias` empty — `_rename_locals` had minted the dead spill as
`object obj1 = obj2`, shadowing the params, and `_copy_prop` merged
the argument. Fixed with `_semantic_local_names`' barrier (reserve
body identifiers + metadata params, bump until free). Portable + game
pins green; zero golden movement. The vN/tN residuals in the other 20
files are still open, now with exact file:line inventories.

## Addendum — 2026-09-22, param-exclusion rename (unpromoted)

The census vN family turned out to be renamed *parameters*:
StreamBuffer.WriteBytes(byte v0, byte v1) (mi 113041-113044)
rendered `this.buf[num2] = obj5` for native `v0` -- `_rename_locals`
rewrites vN tokens including metadata params while the emitter keeps
them, disconnecting every use. Rename targets now exclude every
metadata parameter spelling (a colliding lifter temp keeps its honest
lift-stage name instead of a silent capture). All four overloads
render fully bound; +1 portable / +4 game pins green; zero golden
movement (909 passed / same 3 IDs).

Follow-up: all remaining census residuals resolve as metadata
parameters (HashCode v1-v4, MeshVoxelizer, JValue, TimeSpan, Version,
JToken, TypeUtils, ExceptionBuilder, TMPro, GradientSettingsAtlas --
each verified bound in fresh lifts) except 5 SIMD type-position
checker FPs (v128/v64/v256 as types). The §5 actionable set is ~zero
in fresh lifts; +2 game pins (1935, 79519).

## Addendum — 2026-09-22, interface dispatch slice (unpromoted)

TODONOW #2 first blood, subagent-mined: `GameManager.CheckAllReady`
(mi 25368) carries three back-to-back interfaceOffsets searches that
resolve to GetEnumerator/MoveNext/get_Current exactly (the ground
truth `dec/flow.py` cites). They missed on three decline-preserving
defects, all fixed: slot-line decl prefixes at render stage, the
typeof-reference span ending at the slot instead of the call, and
`_N` display arity vs `` `N `` metadata names (exact-first, fallback
for generic displays only). Full body diff is resolutions + dead
scaffold DCE + one consistent rename; zero `/*indirect*/` remains in
the method. Portable + game pins green; full suite holds the failure
set byte-identically (same 3 IDs). Open #2 remainder: vtable occupants
on abstract bases (needs store provenance -- do not touch without it),
receiver-driven generic substitution (synthetic table).

## Addendum — 2026-09-22, generic slice closed without patch

Designed (extractor + hook + inflated-chain swap) then empirically
closed: 23762's homes already close via the MethodRef slot path,
closed-generic bases never reach `_field_expr` there (0 hits traced),
and corpus mining found zero hook-shaped sites (open result +
correctly-attributed closed receiver + pure-result fix) -- the 9
open-result sites need use→def consumers, 24679/109849 are
misattributed field lanes, the 187 family is already fine.
`selectable1`/`obj17`/`obj11` need sidecar/SIMD-lanes/use→def
respectively (documented). Deferred with the hinted round; no
invisible infra shipped.

## Addendum — 2026-09-22, boxed-bool fold (unpromoted)

The interface round left `object obj32 = obj5.MoveNext();
if (obj32 == null)` -- dead (boxed bools are never null) and wrong on
false (native `test al,al` breaks). `_name_interface_dispatch` now
records bool-returning resolutions; `_boxed_bool_null_fold` runs last
(single `object X = <call>` decl, all-uses-bool via `_bool_use_ok`, no
reassign/address-take, standalone heads; no inlining, no renames).
Folds in 8 methods (25368, 24059, 25132, 25872, 26880, 27213, 97399,
105906); unbox/`&` uses and ref-null tests decline. Portable + game
pins green; full suite holds the failure set byte-identically (same 3
IDs, zero golden movement).
