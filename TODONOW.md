# TODO NOW — exact remaining output failures and source ownership

Generated 2026-09-22 from the current promoted tree. This is a handoff for
the next agent. The generated C# tree is `final_out/`; do not edit it by hand.
The source of truth is the decompiler under `il2cpp/`. Fixture inputs are
`testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat` and
`testgame/GameAssembly.dll`.

## Baseline gates (known good; do not disturb)

- Strict rebuild: 114,458 bodies, 0 failures, 0 fallbacks.
- Brace audit: 0 unbalanced files.
- Full suite: 879 passed, 2 failures only: MethodDefs 67525 and 104428.
- `final_out/` is promoted output and must remain read-only.
- The fixture is private/licensed; never redistribute it.

## Exact fresh census of `final_out/`

All paths below are relative to `C:\Users\crax\Downloads\il2csharp`.
The count is occurrences/lines first and distinct `.cs` files second.

| category | current scan | supplied handoff figure | exact output root |
|---|---:|---:|---|
| shared-body marker `/*shared body, N candidates*/` | 18,995 / 2,304 | 19,013 / 2,304 | `final_out/**/*.cs` |
| `/*indirect*/` | 7,091 / 975 | 7,091 / 975 | `final_out/**/*.cs` |
| literal `unknown` | 12,084 / 1,383 | 16,044 / 1,382 | `final_out/**/*.cs` |
| raw `mem[N]` | 13,189 / 805 | ~13,189 / 805 | `final_out/**/*.cs` |
| `mem_<hex>` load twins | 324 / 70 | 234 / 69 | `final_out/**/*.cs` |
| `goto` | 8,707 / 903 | 8,705 / 901 | `final_out/**/*.cs` |
| `/* nothing */` | 63 / 1 | 63 / — | `final_out/**/*.cs` |
| `?addr` | 2 / 2 | 22 / 6 | `final_out/**/*.cs` |

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

## Work order for the fixing agent

1. Build a machine-readable per-file/per-method inventory from the commands
   above, then select representative native methods for each producer class.
2. Fix shared-body receiver resolution and indirect/interface dispatch as one
   proof-driven feature; run targeted lifts before any corpus rebuild.
3. Fix unknown values and raw memory through register/stack/aggregate
   provenance; add negative tests for ambiguous layouts and stale tiles.
4. Classify unbound temps only after the upstream fixes; otherwise the count
   is inflated by unknown producers.
5. Run compile/parse gates and the full suite. Preserve the exact two known
   failures (67525, 104428) unless native evidence proves a separate fix.
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
