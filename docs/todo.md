# il2csharp — TODO (open work and historical triage)

## Package split (2026-09-12, no behaviour change)

`il2csharp.py` (10,061 lines) and `decompiler.py` (8,407 lines) were split into
the `il2cpp/` package (42 modules). Lines were moved by binary CRLF slicing,
never retyped, under coverage and line-preservation asserts; the splitter is
`work/split/split_pkg.py` and the import smoke is `work/split/smoke.py`.

- Big classes are composed from mixins, one file per mixin: `Il2Cpp`
  (`runtime/`: registration, types, fields, eh), `Lifter` (`lifter/`: state,
  values, insn, calls, render), `Decompiler` (`dec/`: build, analyze,
  structure, sugar, seh, flow, dataflow, highlevel, textpass, emit).
  Pass order inside `_structure`/`_final_text` is untouched.
- Cycle-free by construction: leaf helpers live in `il2cpp/names.py` and
  `il2cpp/runtime/meta.py`, `runtime/__init__.py` is deliberately import-free,
  and `dec/sugar.py` + `stmt_text.py` reach `Decompiler` through a late-bound
  proxy. `python -c "import il2cpp"` is the cycle regression check.
- `il2csharp.py` is now a launcher (CRLF + UTF-8 BOM retained), so
  `python il2csharp.py <target> -o <out>` still works; `python -m il2cpp` too.
  `decompiler.py` is gone (`bckups/presplit_20260912/` holds both originals).
- Consumers moved to real imports (no re-export shims): 271 import lines in
  154 files across `tests/`, `tools/`, `work/`. Historical monolith snapshots
  under `bckups/`, `final_out/`, and `work/review8*` were deliberately
  left untouched.
- Contract test `tests/test_source_format.py` now asserts CRLF + no BOM across
  `il2cpp/**/*.py` and CRLF + BOM on the launcher. `source_sha256` in
  `tools/validate_corpus.py` / `tools/make_goldens.py` now pins every package
  file via `corpus_common.source_fingerprints()`.
- `tests/test_diagnostics.py` imports `il2cpp.cli` (not the facade) because
  `main()` resolves `Emitter`/`Metadata`/`is_arm64_binary` in that module.
- Gates: 436 tests pass (317 portable + 64 snapshots + 54 native, plus the
  extra source-format case); byte-identity rebuild vs `final_out/` recorded in
  `validation_reports/split_rebuild_verification.json`.
- Root cleanup: `scan_stale.py` -> `tools/scan_stale.py`, `SHA256SUMS.txt` ->
  `validation_reports/SHA256SUMS.txt` (`tools/verify_release.py` looks there
  first, then the tree root).
- `work/` reorg (2026-09-12, moves only, no renames): the flat tree is now
  grouped into `artifacts/`, `batches/`, `census/`, `experiments/`, `lib/`,
  `logs/`, `patches/`, `probes/`, `review81/`-`review89/`, `runners/`, and
  `split/` (routing table in `work/README.md`; `review83/`, `review84/`, and
  the `reviewNN_out/` trees predate the reorg and were left as-is). The 176
  root-deriving scripts were depth-rewritten in the same pass
  (`parents[1]` -> `parents[2]`, one more `dirname(...)`);
  `work/split/verify_reorg.py` proves every root expression still resolves
  (167 expressions across 162 files).
- Release manifest refreshed after the split + reorg:
  `validation_reports/SHA256SUMS.txt` 12,597 -> 12,638 entries (406
  relocated, 11,391 rehashed — the old manifest still pinned the Review 84
  tree while `final_out/` holds the promoted Review 89 tree, as proved by
  `work/split/probe_manifest_era.py`: 400/400 sampled `final_out/` digests
  match `bckups/final_out_r84`, 0 match the current tree — 1 dropped
  `decompiler.py`, 42 added `il2cpp/` files; the pre-split manifest is
  archived at `validation_reports/SHA256SUMS.presplit_20260912.txt`).
  `tools/verify_release.py` passes with 0 failures.
- Post-verification cleanup: `work/split/rebuild_out/` (the 11,200-file,
  ~138MB byte-identical rebuild used once for the split proof) deleted; the
  proof stands in `validation_reports/split_rebuild_verification.json` and
  `work/split/rebuild.log`. Small evidence logs kept (`rebuild.log`,
  `fulltest.log` with the 436-pass run).

## Current work — fix 111 (C# keyword escaping, gated 2026-09-18)

The Roslyn whole-tree compile probe (new methodology: `dotnet
build` over all 11,184 files as one project, `__SharedBodyStubs`
deduplicated probe-only) showed 10,778 errors collapsing to root
breaks in just 48 files — 44 of them one class: reserved words as
identifiers (`.namespace` ×194, `.in` ×5, `.interface` ×3, field
`string interface`), which tree-sitter parses but Roslyn rejects
(CS1001 + cascades). The fix routes every metadata-name declaration
(type headers, enum members, methods incl. explicit-`IFoo.Bar`,
fields, events, ctors, properties) through the existing
`safe_ident` (trailing-underscore convention, already used for
params), and adds `_escape_keywords` (dec text pass after the stub
casts): a reserved word after `.`/`->` is never a keyword use, so
masked-line rewriting is exact; strings/comments never match and
already-escaped names never re-match. `nameof()` emission tracks the
escaped spelling. Metadata census: 6 keyword fields, 1,283
keyword params (all `object`/`method`-style delegate plumbing,
already consistent), zero keyword typedefs/methods/namespaces.
Gates: **668 tests (550 portable incl. 6 new in
`tests/test_review111_keywords.py` + 118 game); direct sweep
116,178 methods / 0 crashes / 0 structural changes vs fix 110 (81
bodies changed, all line-neutral); strict build 11,184 files /
115,658 bodies / 0 failures or fallbacks (`work/review111_out`);
parser 0 bad files**. Reports: `validation_reports/review111_sweep.json`,
`review111_vs110.json` (81 changed, 0 structural),
`review111_parse.json`; built tree `work/review111_out`. The 64
goldens are untouched (0 overlapping MIs, no regen needed). NOT
promoted — `final_out/` still holds the fix-99 tree pending a human
promotion call.

- [x] Fix 111: residual `(\.|->)keyword` census is ZERO tree-wide
  (masked scan, 11,184 files); decl/uses agree exactly
  (`private bool async;` + all 8 `this.async_` uses verified in
  FileStream.cs).
- [x] Recompile probe: **10,778 → 40 error instances, 48 → 2
  files**. Everything keyword-related is gone; the survivors are
  the `new X[N](args)` / `new X[N][i]` mistranslation family
  (ZipEntry.cs, SqlDecimal.cs) — fix 112.
- [x] Also proven by probe: into-block `goto` is CS0159-hard-illegal
  (labels are block-scoped for goto; fails with no decls and into
  `try` alike) — no cleverness at the goto level, only
  tail-duplication/hoisting work counts toward compilation.

### Next priorities (fix 111 follow-ups)

1. **Fix 112: `new X[N][i]` 2D-index mistranslation** (751 lines,
   e.g. `new char[1][0x0] = 32`) **and `new X[N](args)`**
   indirect-call misrender (30 lines). Precise lifter shapes.
2. **Semantic layer** (surfaced by the probe once parse falls):
   definite assignment, conversions, duplicate locals — measure
   after fix 112; the goto program (8,071 sites) feeds
   CS0165-class errors.
3. **Project wiring**: per-assembly `.csproj` files exist but
   carry no cross-assembly references (the probe sidestepped this
   with one project).
4. Receiver-driven instance twins, call/indexer `==` operands,
   duplication residue, 447 shared tails — all stand.

## Previous work — fix 110 (unanimous == / != shared calls fold to operators, gated 2026-09-18)

Six shared addresses (~2,726 uses) carry only static 2-parameter bool
`op_Equality` candidates (`Equals` twins allowed) or unanimous
`op_Inequality` (census: `0x181af7520` String 2,282,
`0x18061a510` 17-cand != 201, plus four small ones; the 252-cand
mixed `0x1807ee180` and 1,806-cand `0x18063ac90` decline by
non-unanimity). Address-sharing proves one machine code, so the
operator spelling is behavior-exact with no owner attribution — but
each operand must still prove the exact same operand type for some
candidate, or `a == b` could bind a different overload (notably
`object.==`/ReferenceEquals for object-typed temps). `_eq_addr_info`
(new in `il2cpp/dec/highlevel.py`, cached) proves unanimity (all
`method` candidates, static, 2 params, bool return, GPR-safe param
kinds per matched pair — floats ride XMM, structs carry ABI risk);
`_eq_operand_spelling` proves operand types (string/int literals,
uniquely-declared temps via `_stub_assign_types`, `this`/temp/
`typeof` member paths through metadata fields with
instance/static/literal discipline); `_shared_equality_ops` (wired
between the fence pass and the stub casts, so no `(bool)` cast is
ever synthesized for a rewritten site) folds proven-bool positions
only (whole if/while/do-while tests, top-level &&/|| operands,
`!`-chains, `bool` decl RHS, bool returns; ternary arms, call
arguments, bare statements, and non-bool decls decline). Integer
literals self-type by C# literal rules. Along the way the legacy
bare-`typeof(` check was found to also match `typeof(X).Get()`
(zero corpus sites, closed with `_fence_bare_typeof` in fix 109).
Gates: **662 tests (544 portable incl. ~29 new in
`tests/test_review110_equality_ops.py` + 118 game, 64 goldens
verified live against fixtures); direct sweep 116,178 methods / 0
crashes / 0 structural changes vs fix 109 (312 bodies changed, all
line-neutral); strict build 11,184 files / 115,658 bodies / 0
failures or fallbacks (`work/review110_out`); parser 0 bad files**.
Reports: `validation_reports/review110_sweep.json`,
`review110_vs109.json` (312 changed, 0 structural),
`review110_parse.json`; built tree `work/review110_out`. The 64
goldens were regenerated after individual review of the single
overlapping diff (mi 15013 `set_columnName`: the `!((bool)sub_…)`
condition becomes `this.m_ColumnName != value` — private string
field plus setter string param, exact). NOT promoted — `final_out/`
still holds the fix-99 tree pending a human promotion call.

- [x] Fix 110: ~846 new `==`/`!=` lines (per-method normalized
  multiset audit: the ONLY added lines tree-wide are operators plus
  3 `using System.Threading;`; every removed line is a
  shared-equality call, a dead copy/decl cascade, a dropped stub
  entry, or brace realignment). Ground truth: 3-level field paths
  rewrite (`this.playerInput.m_CurrentActionMap.m_Name ==
  "Interrogation"`) while property twins stay
  (`this.playerInput.currentControlScheme` — getters are calls).
- [x] Residue, all verified declined by design: property/call/
  indexer operands (expression typing open), object-vs-string mixed
  pairs (would bind ReferenceEquals), non-bool positions,
  `0x180434690`-class unregistered dispatch blobs (8,046 uses —
  decoded: jmp thunk onto an unregistered virtual-dispatch
  routine; `0x180002210/380` are interface search loops into the
  `0x18043DC60` slow path — no honest name exists for any of
  them, shapes recorded, `sub_` rendering stays).
- [x] Bugs found by tests while building: an operator-precedence
  slip in the region guard, a trim-based operand matcher that ate
  the call's own close paren, an unreachable typeof branch, and a
  head-gate rejecting `!`/parens before the operand path ran.

### Next priorities (fix 110 follow-ups)

1. **Call/indexer operands for ==** (`ToLower()`,
   `playerIds[i]`): needs expression return-type/element-type
   proof — the general expression-typing problem (fix-105 item 1).
2. **Receiver-driven instance twins** (`TaskAwaiter.GetResult`
   vs `ConfiguredTaskAwaiter.GetResult`, 529 uses; 367
   multi-owner-instance addresses, 3,579 uses): exact receiver
   type proof at lifter level, never a guess.
3. **Unregistered dispatch blobs** (above): naming needs a
   registered/exported identity that does not exist; revisit only
   with new ground truth.
4. **Duplication residue** (~2.7k both-sides-unknown branches),
   **447 remaining shared tails**, **8,067 into-block gotos**,
   Review 87 lists — all stand.

## Previous work — fix 109 (single-level typeof-member fence args, gated 2026-09-18)

Of 151 remaining fence sites, 127 have only plain or
`typeof(X).Member` arguments (census over the fix-108 tree: all 140
typeof-member args are single-level static accesses on hot framework
types — Encoding, TraceInternal, Socket, Uri, Xml*, RegistryKey…).
`_fence_trivial_arg` (in `il2cpp/dec/highlevel.py`) now accepts
exactly `typeof(X).Member` via `_fence_typeof_member` (balanced-paren
scan in `_fence_typeof_end`, one dotted name, checked on masked text
so quoted text can never shape-match). Soundness: no null dereference
is possible (static access only — strictly fewer load effects than
the already-shipped `obj.f` chains), no calls/indexers/further
levels; the tempering precedent is fix 72d's `_PURE_LOAD_RX`, which
already defines typeof-member chains as pure loads for DCE (fix 109
stays on the conservative single-level subset: zero multi-level sites
observed). Along the way the legacy bare-`typeof(`-prefix check was
tightened to whole-string balanced (`_fence_bare_typeof`): it also
matched `typeof(X).Get()`, silently dropping a call (zero corpus
sites ever matched that shape — verified over the pre-fence tree —
but the hole was real; regression-tested). Gates: **639 tests (521
portable incl. 16 new in `tests/test_review109_typeof_args.py` — one
fix-107 expectation corrected for the tightened check — + 118 game);
direct sweep 116,178 methods / 0 crashes / 0 structural changes vs
fix 108 (76 bodies changed, net -335 lines); strict build 11,184
files / 115,658 bodies / 0 failures or fallbacks
(`work/review109_out`); parser 0 bad files**. Reports:
`validation_reports/review109_sweep.json`,
`review109_vs108.json` (76 changed, 0 structural),
`review109_parse.json`; built tree `work/review109_out`. The 64
goldens are untouched (0 overlapping MIs, no regen needed). NOT
promoted — `final_out/` still holds the fix-99 tree pending a human
promotion call.

- [x] Fix 109: ~131 new `Thread.MemoryBarrier()` lines (per-method
  normalized multiset audit: the ONLY added lines tree-wide are
  barriers + 3 `using System.Threading;`; every removed line is a
  fence decl, a dead copy/decl cascade, a dropped
  `0x1804355f0` stub entry, a pure-load decl
  (`getClass()`/`typeof`, per `_PURE_LOAD_RX` doctrine), or brace
  realignment). `sub_1804355f0` falls 159 → 25 lines.
- [x] Residue, all verified declined by design (17 decls + 8 stub
  defs): pointer arithmetic/deref (`(p + 0x88)`,
  `((byte*)obj7 + 0x0)[0]` — 9 sites), integer arithmetic
  (`*`, `>>`, `+` — 5 sites; temp-name typing is not purity
  proof), call args (`obj.getClass()` — pure per doctrine but
  call-shaped; needs a `_PURE_LOAD_RX`-consistent arg rule),
  live-temp plain/zero-arg sites.

### Next priorities (fix 109 follow-ups)

1. **Call-shaped pure args** (`obj.getClass()` and friends):
   align `_fence_trivial_arg` with `_PURE_LOAD_RX` (member chains,
   no calls/Indexers) — the doctrine already exists, needs its own
   gate.
2. **Other top unregistered VAs** (thunk finals,
   interface-dispatch twins from the fix-104 list): native
   structural proof on the fence precedent, never a name guess.
3. **Duplication residue with degraded conditions** (~2.7k
   both-sides-unknown branches, fix-106 list), **447 remaining
   shared tails**, **8,067 into-block gotos**, Review 87 lists —
   all stand.

## Previous work — fix 108 (scope-aware deadness for fence-called temps, gated 2026-09-17)

Fix 107's method-wide liveness treated every same-name mention as a
read, so one colliding scratch temp (sibling scopes re-declare: fix
97c) pinned all of them. `_fence_temp_dead_scoped` (new in
`il2cpp/dec/highlevel.py`, OR-ed with the fix-107 check so nothing it
rewrote can regress) walks forward from the fence declaration at brace
depth d0 over masked lines: a same-block `T nm = ...` rebinds the temp
away outright, a nested declaration or foreach/catch binder shadows its
subtree (depths from `_fence_line_depths`, pruned as blocks close),
outer-scope declarations are different variables, and outer mentions,
unplaceable brace-mixed mentions, initializers reading an outer `nm`,
and any depth anomaly decline exactly as before. `_fence_redecl_of`
reuses `_STUB_DECL_RX` (with the `_STUB_KEYWORDS` guard, so
`return x = ...` never counts) plus the foreach/catch binder regexes.
Gates: **633 tests (515 portable incl. 15 new — 14 in
`tests/test_review108_scoped_fence.py`, one split out of the flipped
fix-107 dup-temp expectation — + 118 game); direct sweep 116,178
methods / 0 crashes / 0 structural changes vs fix 107 (8 bodies
changed, net -96 lines); strict build 11,184 files / 115,658 bodies /
0 failures or fallbacks (`work/review108_out`); parser 0 bad files**.
Reports: `validation_reports/review108_sweep.json`,
`review108_vs107.json` (8 changed, 0 structural),
`review108_parse.json`; built tree `work/review108_out`. The 64
goldens are untouched (0 overlapping MIs, no regen needed). NOT
promoted — `final_out/` still holds the fix-99 tree pending a human
promotion call.

- [x] Fix 108: 23 new `Thread.MemoryBarrier()` lines;
  `sub_1804355f0` falls 185 → 159 lines (8 stub defs + 151 decls
  remain). Of 8 changed methods 6 are line-neutral, 2 shrink
  (`Task.Dispose` -13, `ReaderWriterLockSlim.
  TryEnterUpgradeableReadLockCore` -83) through the same honest DCE
  cascade as fix 107 (orphaned copy chains, one `using static`
  per newly-unreferenced assembly). Ground truth: the
  `FusionNetworkManager` colliding-`obj13` sites rewrite; the
  `ReaderWriterLockSlim` `if`-arm fence rewrites while its
  genuinely-live `else`-arm twin stays.
- [x] Refinement found by probe (single-method re-lift of mi
  103865): an outer-scope re-declaration is a different variable and
  no longer declines the site; decided by reading all five `obj84`
  decls' fates, with a dedicated regression test.
- [x] Residue, all verified declined by design: genuinely-read
  temps, effectful-argument sites (out of scope — the pass never
  touched argument rules), `using`-var/`is`-pattern rebinds,
  mid-line-brace placements.

### Next priorities (fix 108 follow-ups)

1. **Effectful-argument fence sites** (`sub_1804355f0(Foo(), ...)`
   with dead temps): needs call-effect analysis, never blind
   dropping.
2. **Other top unregistered VAs** (thunk finals,
   interface-dispatch twins from the fix-104 list): native
   structural proof on the fence precedent, never a name guess.
3. **Duplication residue with degraded conditions** (~2.7k
   both-sides-unknown branches, fix-106 list), **447 remaining
   shared tails**, **8,067 into-block gotos**, Review 87 lists —
   all stand.

## Previous work — fix 107 (proved fence-thunk calls render Thread.MemoryBarrier(), gated 2026-09-17)

`lock or dword ptr [rsp],0; ret` is the full barrier MSVC emits where the
source calls `Thread.MemoryBarrier`, reached directly or through a short
`jmp` thunk (`0x1804355f0`, the fix-104 follow-up membarrier suspect —
1,465 sites). `_is_fence_body` (new in `il2cpp/lifter/state.py`) proves
exactly that shape: locked `OR`, RSP base, zero displacement, dword
width, zero immediate (both `0x83` and `0x81` encodings), `ret`
terminating the extent; registered/exported/non-exec/unreadable targets
decline. `_fence_target` follows the thunk (itself or <=3 jmp hops),
memoized, never a hardcoded address. `_fence_void_calls` (new in
`il2cpp/dec/highlevel.py`, wired in `il2cpp/dec/structure.py` after the
delegate fold, before the stub casts) rewrites only positions that need
no value: bare statements, void `; return;` tails (split in two), and
declarations whose temp is dead method-wide. Every argument must be
side-effect-free (plain temps/fields, literals, typeof, strings);
conditions, value returns, live temps, and `Thread.MemoryBarrier` itself
keep today's rendering. Gates: **618 tests (500 portable incl. 12 new
in `tests/test_review107_fence_calls.py` + 118 game); direct sweep
116,178 methods / 0 crashes / 0 structural changes vs fix 106b (544
bodies changed, net -2,202 lines); strict build 11,184 files / 115,658
bodies / 0 failures or fallbacks (`work/review107_out`); parser 0 bad
files**. Reports: `validation_reports/review107_sweep.json`,
`review107_vs106b.json` (544 changed, 0 structural),
`review107_parse.json`; built tree `work/review107_out`. The 64
goldens are untouched (0 overlapping MIs, no regen needed). NOT
promoted — `final_out/` still holds the fix-99 tree pending a human
promotion call.

- [x] Fix 107: 1,279 `Thread.MemoryBarrier()` lines (3 pre-existing
  resolved calls + 1,276 rewrites); `sub_1804355f0` falls 1,465 → 185
  lines. Of 544 changed methods 386 are line-neutral, 157 shrink
  (dead-decl plus the honest DCE cascade its orphaned copies allow),
  1 grows by design (bare `...; return;` splits in two:
  `Socket.Connect`). Ground truth: `Thread.MemoryBarrier`'s own body
  (RVA 0x1D1F380) is one call to `0x1804429c0` and is deliberately NOT
  rewritten (self-guard); `Fusion.AtomicInt`'s seven members drop
  their dead `object objN = sub_1804355f0(...)` decls and the
  now-unused `using static __SharedBodyStubs;`.
- [x] Residue, all verified declined by design: 174 decls whose temp
  is live or textually collides with a reused scratch temp later in
  the method (safe-miss direction — e.g. `FusionNetworkManager`
  `obj13` reused as `_StartGame_d__58`), 9 `__SharedBodyStubs`
  definitions that must stay, effectful-arg and value-position sites.
- [x] into_block gotos identical 8,071 (both sweeps), parse re-gated
  on the built tree.

### Next priorities (fix 107 follow-ups)

1. **Remaining `sub_1804355f0` residue above** (live-temp value
   positions): needs value-proof the fence returns nothing at the
   call site, never deletion of a live temp.
2. **Other top unregistered VAs** (thunk finals, interface-dispatch
   twins from the fix-104 list): each needs native structural proof
   on the sqrt-wrapper/fence precedent, never a name guess.
3. **Duplication residue with degraded conditions** (~2.7k
   both-sides-unknown branches, fix-106 list), **one-side-unknown
   comparisons** (~700+), **447 remaining shared tails**, **8,067
   into-block gotos**, Review 87 lists — all stand.

## Previous work — fix 106 (parity-jump NaN fold drops literal arms, gated 2026-09-16)

`ucomiss` + `jp` rendered `IsNaN(a) || IsNaN(b)` even when one side is
a constant (`IsNaN(0f)` — provably false, 665 sites). No numeric
literal spelling denotes NaN, so `_is_non_nan_literal` (new in
`il2cpp/x64.py`, reusing `_int_lit` plus finite-float parsing) drops
such arms in `flag_cond`; the `x != x` idiom and unknown/nullary
operands are untouched, and all-constant pairs decline as before.
Gates: **606 tests (598 + 8 new in
`tests/test_review106_float_parity.py`); direct sweep 116,178 methods
/ 0 crashes / 0 structural changes vs fix 105 (294 bodies changed);
strict build 11,184 files / 115,658 bodies / 0 failures or fallbacks
(`work/review106_out`); parser 0 bad files**. Reports:
`validation_reports/review106_sweep.json`, `review106_vs105.json`
(294 changed, 0 structural), `review106_parse.json`; built tree
`work/review106_out`. The 64 goldens were regenerated after individual
review of the single diff (`DateTimeConverter.ConvertTo`, double
width). NOT promoted — `final_out/` still holds the fix-99 tree
pending a human promotion call.

- [x] Fix 106: 665 literal arms dropped in 144 files (full tree
  audit, 0 unexplained). The single flagged hunk hand-verified
  correct: the arm was a literal at lift time, bound to a temp only
  later (`object obj1 = 1.79…e+308d` feeding a `comisd`).
  `IsNaN(<const>)` falls 665 → 0 (4,968 live-value arms remain).
- [x] Fix 106b: first-char guard (an `inf`-spelled identifier can
  never be taken for a literal). Zero-diff proof on this corpus:
  direct sweep 0/116,178 changed vs fix 106, rebuilt tree
  byte-identical across all 11,184 files (`work/review106b_out`),
  parse re-gated. Reports: `review106b_sweep.json`,
  `review106b_vs106.json`, `review106b_parse.json`.
- [x] Ground truth: `AudioVolumeSliders.SetMusicVolumeInternal` —
  native `ucomiss; jp; jne` to one target; the `IsNaN(0f)` arm is
  gone (the surviving `unknown != unknown` duplication residue is a
  separate structuring matter, below).

### Next priorities (fix 106 follow-ups)

1. **Duplication residue with degraded conditions** (~2.7k
   both-sides-unknown branches with sibling-identical bodies, e.g.
   `else if (unknown != unknown)`): needs _seq/fold-level proof
   (never delete — an unprovable condition can't lose its arm).
2. **One-side-unknown comparisons** (~700+), unbound decls/arithmetic
   (`object obj17 = unknown;`), **honest names** for the top
   unregistered VAs (thunk finals, membarrier, interface-dispatch
   twins), **447 remaining shared tails**, **8,067 into-block gotos**,
   Review 87 lists — all stand.

## Previous work — fix 105 (ternary-condition casts, arm leniency, do-while, gated 2026-09-16)

Same caller-proven rule, one level deeper: a sub_ call in a ternary
CONDITION proves `bool` there (arms keep the line's type), arms without
calls pass through instead of vetoing the line, and `} while (...)`
proves `bool` like `if`/`while`. `== null`, `&&`/`||`, arithmetic and
call-nested conditions still decline whole-line, correctly. Gates:
**598 tests (22-case stub file extended: ternary conds, arm leniency,
do-while); direct sweep 116,178 methods / 0 crashes / 0 structural
changes vs fix 104 (47 bodies changed); strict build 11,184 files /
115,658 bodies / 0 failures or fallbacks (`work/review105_out`);
parser 0 bad files**. Reports: `validation_reports/review105_sweep.json`,
`review105_vs104.json` (47 changed, 0 structural),
`review105_parse.json`; built tree `work/review105_out`. The 64
goldens are untouched (0 overlapping MIs, no regen needed). NOT
promoted — `final_out/` still holds the fix-99 tree pending a human
promotion call.

- [x] Fix 105: 59 cast lines in 42 files, every one a cast-only swap
  at identical indent, 0 suspicious casts (full tree audit).
  Ground truth: `string text4 = (bool)sub_Equals(...) ?
  string.Format(...) : ...`, `float real22 = !((bool)sub_...(304)) ?
  ...`, `Object object1 = (bool)sub_...(type5, ...) ? ... : ...`.
- [x] Returns proven COMPLETE: all 99 bare `return sub_` lines sit in
  void/object methods (pointer returns excluded by design); the 12
  apparent counterexamples were property/nested-class misattributions
  in the audit scaffolding, each verified by hand.

### Next priorities (fix 105 follow-ups)

1. **Operator-nested bool positions** (`&&`/`||` operands,
   `== <lit>` with numeric proof, ternary-in-ternary conds):
   needs per-operator expression typing.
2. **Byref/pointer arguments** into stubs (`&` address-of, `void*`
   params); **honest names** for the top unregistered VAs (thunk
   finals, membarrier, interface-dispatch twins); **447 remaining
   shared tails** (10 via the `this`-rule), **8,067 into-block
   gotos**, Review 87 noreturn-EH/leftover lists — all stand.

## Previous work — fix 104 (object stubs for unresolved sub_ + caller casts, gated 2026-09-16)

53,984 `sub_X(...)` references pointed at methods declared nowhere
(2,687 distinct VAs, 0 definitions tree-wide). The emitter now writes
one global `__SharedBodyStubs` class per assembly (`internal static
object sub_X(params object[] args)`, throwing, with per-VA owner
comments) plus `using static __SharedBodyStubs;` per referencing file,
and a late dec pass (`_shared_stub_casts` in `il2cpp/dec/highlevel.py`,
after the delegate fold) inserts caller-proven `(T)` casts: decl TYPE
(83% of sites), whole-condition `bool`, method return (`void` splits
to call-then-return), unique-mapped plain assigns. Only direct value
positions rewrite (root, ternary arms with sub_-free conditions,
`!`-chains, one paren layer); nested args keep the object spelling;
real metadata `sub_<hex>` names never stub or cast. Gates: **598
tests (576 + 22 new in `tests/test_review104_shared_stubs.py`; 4
review83 spellings updated, behaviors intact); direct sweep 116,178
methods / 0 crashes / 0 structural changes vs fix 103 (7,096 bodies
changed); strict build 11,184 files (11,107 + 77 stub files) /
115,658 bodies / 0 failures or fallbacks (`work/review104_out`);
parser 0 bad files**. Reports: `validation_reports/review104_sweep.json`,
`review104_vs103.json` (7,096 changed, 0 structural),
`review104_parse.json`; built tree `work/review104_out`. The 64
goldens were regenerated after individual review of all 5 diffs (each
exactly a caller-proven cast). NOT promoted — `final_out/` still holds
the fix-99 tree pending a human promotion call.

- [x] Fix 104: 12,716 cast lines (8,584 decl + 1,319 return + 2,544
  conditions + 269 assigns), every cast type proven against its own
  line/method/metadata (decl casts equal their decl, conditions are
  `(bool)`, returns match file signatures and metadata sharer sets,
  assigns match unique decl maps); 3,627 usings; 77 stub files;
  0 void splits left (fix 95 owned them), 0 unexplained hunks.
  Hardening along the way: `\x01` mask alphabet for comments (104c),
  string-aware balanced spans, chained-assign shape proven
  unmatchable so its guards were removed (104e).
- [x] Residue, all verified declined by design: `&`/pointer args
  (~9k, need byref recovery — the method now resolves, the argument
  still doesn't), nested-expression positions (~2.6k conditions with
  calls under operators, `is`/`as`, `??`), untyped sources.
- [x] Next honest-naming targets identified (not attempted): the top
  unregistered VAs are analyzable natives — `0x180434690` (8,046
  uses) is a `jmp` thunk onto `0x180479F80`, `0x1804355f0` (1,449) a
  thunk onto a `lock or [rsp],0` memory barrier, `0x180002210` /
  `0x180002380` (~5,700) near-identical interface-dispatch search
  loops, plus `0x18043dc60`, `0x18043e360`, `0x1804346a0`. Each needs
  native structural proof (sqrt-wrapper precedent), never a name
  guess. A generic `<T>` stub was rejected (C# never infers from
  return position); casts express caller-side need and stay valid if
  a VA later resolves honestly.

### Next priorities (fix 104 follow-ups)

1. **Condition/nested-expression casts** (`&&`/`||` operands,
   `== <lit>` comparisons, ternary conditions, `is`/`as` left alone
   correctly): needs expression-type analysis per operator.
2. **Byref/pointer arguments** into stubs; **honest names** for the
   top unregistered VAs above; **447 remaining shared tails** (10 via
   the `this`-rule), **8,067 into-block gotos**, Review 87
   noreturn-EH/leftover lists — all stand.

## Previous work — fix 103 (native-width INDEXED raw-store lvalues, gated 2026-09-16)

Same display-only rule as fix 102, extended to the indexed raw branch
(`base + idx*scale + disp`): the index/scale pair is recorded in
`_mem_lvalue` and the display mirrors the raw branch's own `_term_up`
construction exactly, so output is identical modulo the cast
(verified `_unsafify` fixpoints, incl. composite and byte*-read
indices). Gates: **576 tests (571 + 5 new indexed cases in
`tests/test_review102_raw_store_widths.py`); direct sweep 116,178
methods / 0 crashes / 0 structural changes vs fix 102 (478 bodies
changed); strict build 11,107 files / 115,658 bodies / 0 failures or
fallbacks (`work/review103_out`); parser 0 bad files**. Reports:
`validation_reports/review103_sweep.json`, `review103_vs102.json`
(478 changed, 0 structural), `review103_parse.json`; built tree
`work/review103_out`. The 64 goldens were regenerated after individual
review of the single diff (`ViscosityVorticityJob.Execute`: indexed
`inc dword` RMW → `int*`; its untyped `mov`-triple sibling correctly
stays byte*). NOT promoted — `final_out/` still holds the fix-99 tree
pending a human promotion call.

- [x] Fix 103: 1,287 widened lines in 276 files, every one a
  cast-only swap at identical indent (full tree audit, 0 unexplained,
  0 added, 0 dropped). Out-of-range literal stores fall 189 → 118;
  byte* stores overall 3,579 → 3,205.
- [x] Residue after fix 103 (each verified declined by design):
  untyped register sources (add-expr `READ + 1` with unknown type),
  `__static_fields` blobs, reference/array/`new` RHS, wide source in
  narrow store, width-1 stores of non-byte values (unencodable
  natively — the value proves a wider write elsewhere).

### Next priorities (fix 103 follow-ups)

1. **Untyped register sources** (expression-typed `READ op LIT`
   values): needs expression type inference, not spelling guesses.
2. **Wide-source-in-narrow-store** and **reference stores through raw
   pointers**: both need field-type recovery.
3. **447 remaining shared tails** (receiver `this`-rule scoped at 10
   `MemberwiseClone` sites), **8,067 into-block gotos**, Review 87
   noreturn-EH/leftover lists — all stand.

## Previous work — fix 102 (native-width raw-store lvalues, gated 2026-09-16)

A raw `*(base + disp)` store lvalue rendered `((byte*)base + disp)[0]`,
which fails to compile whenever the stored value is not a byte (1,524
out-of-range literals tree-wide, plus mistyped variables). The native
width is ground truth from the store instruction, so the statement now
spells a same-width cast (`_wide_src_cast`/`_wide_rmw_cast` +
`_wide_store_disp`/`_wide_rmw_disp` in `il2cpp/lifter/insn.py`, parts
recorded in `_mem_lvalue`). Only the emitted statement spells the
width — kills, slots, barriers and twin dedup keep the raw text; the
barrier twin still renders raw, bridged by `_canon_wide_cast` in
`_norm_twin` (`il2cpp/text.py`); the `unsafe` detector covers all
pointer casts (`il2cpp/dec/textpass.py`). Gates: **571 tests (544 + 27
new in `tests/test_review102_raw_store_widths.py`, incl. end-to-end
`_write_mem`/`_rmw_mem` and an updated packed-lane spelling in
`tests/test_game_review81.py`); direct sweep 116,178 methods / 0
crashes / 0 structural changes vs fix 101 (9,269 bodies changed);
strict build 11,107 files / 115,658 bodies / 0 failures or fallbacks
(`work/review102_out`); parser 0 bad files**. Reports:
`validation_reports/review102_sweep.json`, `review102_vs101.json`
(9,269 changed, 0 structural), `review102_parse.json`; built tree
`work/review102_out`. The 64 goldens were regenerated after individual
review of all 4 diffs (each exactly a width improvement:
`GetChars`, `Rpc_CMD_Heal`, `uint3x3.op_Explicit`, `Finalize`).
NOT promoted — `final_out/` still holds the fix-99 tree pending a
human promotion call.

- [x] Fix 102: integer literals pick signedness by fit (signed first),
  float literals keep their suffixed width (`f`→float, `d`/bare→
  double; fix 102b), register sources are accepted only when the
  source type's size equals the native width so every rendered byte is
  value-determined (a narrower source would leave upper bytes
  unexplained — e.g. a long in a dword store stays honest). RMW keeps
  result unity (`int`/`long`/`uint`/`ulong`/`float`/`double` only,
  width 4/8). Declines on unknown/reference/enum/bool sources,
  indexed stores, `__static_fields` blobs (19 sites, all compiling —
  keeps the sfblob twin machinery byte-identical), and un fitting
  values/widths.
- [x] Fix 102c: `_field_expr`'s miss over a dotted base returned the
  raw text through the field branch, bypassing width recording
  (`this.ropeRenderer + 0x54`, `this.heap[0x0] + 0x22`, ...). The
  exact-passthrough spelling now records the identical parts at true
  instruction width; returned text is byte-identical either way.
- [x] Provenance verified on the built trees (11,107 files, inventory
  identical): 25,765 widened lines in 1,820 files, every one a
  cast-only swap at identical indent; +1 honest line (`Decimal.Abs`:
  a 16-byte struct copy plus a dword flags fixup previously
  accidentally deduped to one line — verified against native);
  3 honest ternary unfolds (one arm widened while a genuinely
  different-width sibling arm stayed byte* — merging them would be the
  bug); 0 unexplained changes. Out-of-range literal stores fall
  1,524 → 189 (residue: indexed fills, untyped registers,
  wide-in-narrow, `__static_fields` — each verified declined by
  design, modulo comparison/indexed census false positives).
- [x] Ground truth: `mov dword [rbx],0FFFFFFFEh` → `((uint*)num1 +
  0x0)[0] = 4294967294;`, `movss` float lanes → `((float*)obj4 +
  0x4)[0] = ...` (review81 proof intact: 4 Sqrt, no helper, no
  unknown), `mov word [x],0FFFFh` → `((ushort*)...)[0] = 65535;` —
  full cases in the test file.

### Next priorities (fix 102 follow-ups)

1. **Indexed raw stores** (`base + idx*scale + disp`, e.g. float-1.0
   array fills): same helper extends naturally, needs its own gate.
2. **Untyped register sources** (`void*` params, untyped slots) and
   **wide-source-in-narrow-store** (long into dword field): both need
   field-type recovery, not spelling guesses.
3. **Reference/array/`new` RHS** through raw pointers: barrier and
   field-recovery territory, never a pointer cast.
4. **447 remaining shared tails** (fix 100 list stands — receiver
   `this`-rule scoped at 10 `MemberwiseClone` sites), **8,067
   into-block gotos**, Review 87 noreturn-EH/leftover lists — all
   stand.

## Previous work — fix 101 (bare-param declaration hints close over `new` RHS, gated 2026-09-16)

A tracked hint that is one bare VAR/MVAR (`T`, `T1`, `TValue` —
top-level 0x13/0x1e with a matching spelling, openness proved
structurally by `_type_has_var`) names no type at all, while the same
line's `new ObiPinConstraintsBatch()` / `new List<int>()` is the exact
closed allocation identity (`_bare_closed_new_type` +
`_bare_new_rhs_type` in `il2cpp/dec/highlevel.py`, wired into
`_decl_type_of` after the fix-98 same-base path). `T x = new C(...)`
never compiles under any binding of `T`, so no compiling method can
regress. Gates: **544 tests (526 + 18 new in
`tests/test_review101_bare_t_decls.py`); direct sweep 116,178 methods /
0 crashes / 0 structural changes vs fix 100 (234 bodies changed, all
line-neutral); strict build 11,107 files / 115,658 bodies / 0 failures
or fallbacks (`work/review101_out`); parser 0 bad files**. Reports:
`validation_reports/review101_sweep.json`, `review101_vs100.json` (234
changed, 0 structural), `review101_parse.json`; built tree
`work/review101_out`. The 64 goldens are untouched (0 overlapping MIs,
no regen needed). NOT promoted — `final_out/` still holds the fix-99
tree pending a human promotion call.

- [x] Fix 101: bare-param hints take the RHS `new` spelling — non-generic
  (`T value1 = new ObiPinConstraintsBatch()`), generic over bare
  (`T value1 = new List<int>()` via the fix-98 path,
  `TValue value1 = new List<GameObject>()`), and qualified
  (`T value1 = new TMPro.KerningPair()` — only the last dotted
  component decides openness, fix-98 invariant; fix 101b). Declines on
  non-bare tuples, non-bare spellings, unreadable openness, open
  generic RHS (`new List<TKey>()`), bare `new T()`, non-`new`/array/
  initializer RHS, `<>c__` display-class spellings (normalized only at
  the file boundary, not a valid mid-pipeline decl type), and T-like
  bare targets (`new TMP_Character()`). Never invents a type: the
  spelling comes literally from the emitted RHS.
- [x] Provenance verified old-vs-new on all 234 changed bodies:
  line-count-identical everywhere; every diff line is a bare-`T`
  declaration-type change (463) or a consistent rename projection of
  one (319 binder renames incl. `foreach` binders, 1,475 use-site
  renames, 0 failures, 0 conflicts, 0 collisions). Every new decl type
  matches its own line's `new` target literally (the one apparent
  mismatch is a whitespace-only audit artifact:
  `List<byte[]>` vs `new List<byte[]>()`).
- [x] Residue: 8 bare-`T`-over-`new` sites in 5 files, both families
  declined by design — 4× `T1 t11 = new __c__DisplayClassN_0()`
  (mid-pipeline `<>c__` spelling; closing needs an emitter-coupled
  mangled-spelling proof) and 4× TMP sites
  (`new WeakReference<TMP_FontAsset>`, `new TMP_Character()`,
  `new TMP_SpriteCharacter()`: `TMP_*` collides textually with the
  bare-param regex, so the RHS reads open; closing needs a metadata
  typedef-closedness proof, not a textual one).

### Next priorities (fix 101 follow-ups)

1. **8 residual sites above**: emitter-coupled `<>c__` decl spelling,
   metadata typedef-closedness for T-like concrete RHS names.
2. **447 remaining shared tails** (fix 100 list stands), **8,067
   into-block gotos**, Review 87 byte-store/noreturn-EH/leftover lists
   — all stand.
3. Discovered and NOT changed: `_args_contain_open_param` is purely
   textual, so concrete `TMP_*` types read as open params on the RHS
   (tracked-tuple side is structurally proved and unaffected); the
   `<>c__` → `__c__` file-boundary mangling runs after all decl
   passes.

## Previous work — fix 100 (shared-tail resolution by caller return type, gated 2026-09-16)

A `return <call>` tail delivers the callee's value as the caller's own,
so the true callee's closed, spec-inflated return must equal the
caller's exact metadata return (`_shared_tail_return_target` +
`_tail_sig_key`/`_tail_subst_closed` in `il2cpp/lifter/calls.py`, wired
into both tail-jmp paths in `il2cpp/lifter/insn.py` and
`il2cpp/dec/analyze.py` — the analyze.py mirror is the one that emits
production tails; insn.py covers mid-block jumps). Gates: **526 tests
(509 + 17 new in `tests/test_review100_tail_returns.py`, incl. an
end-to-end `_insn` twin render); direct sweep 116,178 methods / 0
crashes / 0 structural changes vs fix 99 (64 bodies changed, net -212
lines); strict build 11,107 files / 115,658 bodies / 0 failures or
fallbacks (`work/review100_out`); parser 0 bad files**. Reports:
`validation_reports/review100_sweep.json`, `review100_vs99.json` (64
changed, 0 structural), `review100_parse.json`; built tree
`work/review100_out`. The 64 goldens are untouched (0 overlapping MIs,
no regen needed). NOT promoted — `final_out/` still holds the fix-99
tree pending a human promotion call.

- [x] Fix 100: keep nothing on speculation (open/unreadable rows decline
  the whole resolution), drop closed return mismatches, resolve only on
  one distinct rendering. Declines on void callers (fix 95 owns them),
  open/unknown callers, empty/split survivors, open generic definitions,
  and non-method/generic rows. Winners render through the existing
  resolved-tail emitters. Ground truth: `GameServer.GetHSteamPipe`
  (mi 97624) `return sub_18073e050...(GetHSteamPipe(), 0)` becomes
  `return HSteamPipe.op_Explicit(...);`, `Int32.IConvertible.ToInt64`
  (mi 2044) loses 8 lines of guard/phi scaffolding collapsing to
  `return Convert.ToInt64(this.m_value);`, `CloudServices.get_LocalPlayerRef`
  (-12) becomes `return PlayerRef.FromIndex(cloudServices1 >> 32);`,
  `ValueTuple.CombineHashCodes` ×7 (-6 each) become
  `return HashHelpers.Combine(...);`.
- [x] Provenance verified on the built trees: all 13,646 lost
  call-shaped lines are dead `Type V = typeof(X)` (fix-99 audit; the 3
  apparent gains are renumbering artifacts); every added tree line is a
  consistent rename of a surviving live line. Impure-line conservation
  holds modulo locals.
- [x] Residue: `return sub_*shared body` tails fall 511 → 447 (97 → 87
  addresses). Deliberately honest remainder, by family: string
  `Equals`/`op_Equality` (74, behavior-identical twins), `Compare`/
  `CompareTo` (9), `GetHashCode`/`InternalGetHashCode` (15),
  `Clone`/`MemberwiseClone` (10), `get_Module`/`GetRuntimeModule` (8),
  thunk-address pairs whose finals carry no candidates, same-signature
  twins (`GetTexture`/`GetTextureImpl`, surrogate/`IsDigit` pairs),
  and high-count addresses needing receiver instantiation (`List.Add`,
  `Dictionary.get_IsReadOnly`, `Nullable`) or arg-type overload proof
  (`Convert.ToBoolean` short/ushort, `Exchange` long/IntPtr).

### Next priorities (fix 100 follow-ups)

1. **447 remaining tails**: receiver-driven instantiation (same-owner
   generic families), arg-type overload disambiguation, forwarder
   direction via body-call analysis. Never max-arity guesses.
2. **Bare-`T` declaration LHS** (~425 sites), **8,067 into-block gotos**,
   byte-store/noreturn-EH/leftover lists — all stand.
3. Discovered and NOT changed: `_IMPURE` never matches generic calls
   (`Foo<Bar>(...)`), so pre-existing DCE already treats dead generic
   calls as droppable (see fix 99 notes); the analyze.py/insn.py tail
   mirrors must stay in sync — fix 94/100 wire both.

## Previous work — fix 99 (post-render dead-pure-load DCE, gated 2026-09-15)

`_render` drops empty pure-cond `if`s (e.g. an emptied class-init guard
`if (!(k.initialized != 0)) { }`), orphaning the pure klass loads they
alone read — no DCE ran after render, so `System.Type objN = typeof(X)`
survived dead into output and was renamed `Type typeN`. `_structure`
(`il2cpp/dec/structure.py`) now re-runs the proven `_drop_dead_locals`
on the rendered lines: same predicate (pure RHS incl. pure-loads drop,
impure calls stay), later timing. Gates: **509 tests (499 + 10 new in
`tests/test_review99_render_orphans.py`); direct sweep 116,178 methods /
0 crashes / 0 structural changes vs fix 98 (10,062 bodies changed, every
one pure line deletions, net -16,555 lines); strict build 11,107 files /
115,658 bodies / 0 failures or fallbacks (`work/review99_out`); parser 0
bad files**. Reports: `validation_reports/review99_sweep.json`,
`review99_vs98.json` (10,062 changed, 0 structural), `review99_parse.json`;
built tree `work/review99_out`. The 64 goldens were regenerated after
individual review of all 6 diffs (each exactly dead-typeof removals plus
required renumbering cascades). Promoted 2026-09-15: `final_out/` now holds
`work/review99_out` (11,200 files, candidate and promoted aggregate sha256
both `c14263784492b2f209ff695018376404cf0093f06862e1b20e928da89391f2e7`, 0
mismatches; the fix-97e tree is kept at `bckups/final_out_review97e`).
Promotion record: `validation_reports/review99_promotion_verification.json`;
post-promotion parse recheck
`validation_reports/review99_recheck_parse_final.json` (11,107 files, 0
bad).

- [x] Fix 99: one post-render `_drop_dead_locals` call. Ground truth:
  ActorCOMTransform.Update (mi 23898) ships `Type type1 =
  typeof(Object)` whose only reader is the guard `_render` removes;
  KerningTable.AddKerningPair (mi 95457) is untouched.
- [x] Provenance verified on the built trees: all 13,646 lost
  call-shaped lines are `Type V = typeof(X)` (dead pure loads); the 3
  apparent gains are local-renumbering artifacts of the audit's own
  normalizer (verified method-full diffs); every added tree line is a
  consistent rename (`type2` → `type1`) of a surviving live line.
- [x] Residue: dead `Type typeN = typeof(X)` decls fall 12,700 → 10 (the
  10 survivors are kept by `//` line-comment contents seeding liveness —
  over-retention, safe direction). Diagnosed but NOT changed: `_IMPURE`
  (`[\w\]\)]\s*\(`) never matches generic calls (`Foo<Bar>(...)`), so the
  pre-existing DCE already treats dead generic calls as droppable; fix 99
  adds no new unsoundness class (1 such drop corpus-wide:
  `CompileFunctionPointer<...>` in GPUResidentDrawerBurst).

### Next priorities (fix 99 follow-ups)

1. **511 remaining `return sub_*shared body` tails** (fix 94 list stands).
2. **Bare-`T` declaration LHS** (`T value1 = new KerningPair();`, ~425
   sites), **8,067 into-block gotos**, Review 87 byte-store/noreturn-EH
   lists — all stand.
3. **`UnityAction<T0>` LHS is DONE (fix 98); dead-`typeof` LHS is DONE
   (fix 99)** except the 10 comment-pinned survivors above.

## Previous work — fix 98 (open-generic declaration LHS closes over `new` RHS, gated 2026-09-15)

Open-generic tracked hints (`UnityAction<T0>`, `EventCallback<TEventType>`,
`Func<TSource, bool>`, …) now declare with the same line's closed `new`
allocation spelling when the generic definition matches (same short base,
same arity) and the RHS is textually closed. Gates: **499 tests (483 + 16
new in `tests/test_review98_open_generic_decls.py`); direct sweep 116,178
methods / 0 crashes / 0 structural changes vs fix 97e (229 bodies changed,
all line-neutral declaration-only); strict build 11,107 files / 115,658
bodies / 0 failures or fallbacks (`work/review98_out`); parser 0 bad
files**. Reports: `validation_reports/review98_sweep.json`,
`review98_vs97e.json` (229 changed, 0 structural), `review98_parse.json`;
built tree `work/review98_out`. The 64 goldens are untouched (0 overlapping
MIs, no regen needed).

- [x] Fix 98: `_decl_type_of` (`il2cpp/dec/highlevel.py`) propagates the
  closed RHS `new` type when the tracked type structurally contains
  VAR/MVAR (`_type_has_var` binary walk, not a name guess), the RHS parses
  as a generic `new` (`_new_rhs_type`, arrays/non-generics decline), both
  sides split to the same short base and arity (`_split_generic`), and
  generic-argument-position openness agrees
  (`_args_contain_open_param`: `TMPro.KerningPair`-style qualified names no
  longer read as open). Different bases (`IList<T>` vs `new List<int>()`),
  open RHS, non-`new` RHS (`Enumerator<T> = obj.GetEnumerator()`), bare-`T`
  LHS (`T value1 = new KerningPair()`), and closed/unknown tracked types all
  decline. Built-tree same-base open→closed `new` sites fall 414 → 0 (the 3
  remaining `UnityAction<T0>` lines are legitimate method signatures).

### Next priorities (fix 98 follow-ups)

1. **511 remaining `return sub_*shared body` tails** (fix 94 list stands).
2. **Bare-`T` declaration LHS** (`T value1 = new KerningPair();` family),
   **dead `Type type1 = typeof(Object);` lines** (2,791 sites), Review 87
   byte-store/noreturn-EH/leftover lists — all stand (see below).
3. **`UnityAction<T0>` declaration LHS is DONE (fix 98 above)** except the 3
   legitimate open-generic method signatures, which must stay open.

## Previous work — fix 97 (bare first-use temp declarations + 97e render repair, gated 2026-09-14)

Declare bare first-use temps (`objN = rhs;` with no prior declaration from
stack-slot zeroing, phi copies, unbound call results) exactly like `var`
lines, from the same tracked-type lookup; a later `var` line for the same
temp keeps only its assignment. Gates: **483 tests (462 + 21 new: 15 in
`tests/test_review97_bare_decls.py` plus 6 fix-97e `_render` cases); direct
sweep 116,178 methods / 0 crashes / 0 structural changes vs fix 94 (39,478
bodies changed, net declaration additions); strict build 11,107 files /
115,658 bodies / 0 failures or fallbacks (`work/review97_out`); parser 0
bad files**. Reports: `validation_reports/review97e_sweep.json`,
`review97e_vs97.json` (25 changed, 0 structural — the 97e repair only),
`review97e_parse.json`; built tree `work/review97_out`. The 64 goldens were
regenerated with **0 body changes** (none of the 25 repaired methods is a
golden MI; only source fingerprints refreshed). Promotion record:
`validation_reports/review97e_promotion_verification.json`; post-promotion
parse recheck `validation_reports/review97e_recheck_parse_final.json`.

- [x] Fix 97: first-use bare assignments declare (`_rename_locals` in
  `il2cpp/dec/highlevel.py`, wired through the existing `var` type path).
- [x] Fix 97b: `= default` for zero-literal RHS that cannot spell the
  declaration type (`_bare_rhs_needs_default`: only zero-valued numerics
  rewrite; nonzero literals keep their faithful value).
- [x] Fix 97c: scope-aware declaration tracking (sibling scopes re-declare;
  enclosing declarations suppress).
- [x] Fix 97d: (folded into 97b) nonzero-literal fidelity.
- [x] Companion updates: typed `bool flagN` sugar variants (`_bool_sugar`
  in `il2cpp/dec/sugar.py`), ternary arm declaration normalization
  (`_ternary_pass`), typed hop-temp acceptance (`_HOP_DEF_RX` in
  `_compound_assign`).
- [x] Fix 97e (render-strip repair, found by the parse gate, not the
  sweep): the first `work/review97_out` build gated **23 bad files / 26
  ERROR nodes** (review 94: 0/0/0). Chain: 97b synthesizes `: default`
  false arms, `_ternary` folds `if (!c) { T x = call(); } else
  { T x = default; }` into `T x = c ? call() : default;`, then
  `_strip_dangling_default` (`il2cpp/dec/textpass.py`, inside `_render`)
  dropped the tail — its flat `region_q` flag reset on every `(` (the
  call's parens) and `,` (multi-arg calls), orphaning unparseable
  `? call() ;`, which `_fix_select` cannot repair (statement-level `?`).
  The strip now tracks the paren depth of each live ternary/select `?`
  mark: `(` no longer resets, `,` only forgets marks at its own depth or
  deeper, `)` forgets the closed group's marks, `;{=` still clear the
  region, and `??`/`?.`/nullable `?` never become marks. All 26 sites
  (e.g. `IntPtr num2 = num1 != null ? AndroidJNI.NewGlobalRef(num1) ;`
  → `... : default;`) verified fixed in the rebuilt tree; dangling tails
  (`Foo(a : default)`, including after `int?` declarations) still strip.
  Side note: `tools/validate_corpus.py parse` segfaulted on the broken
  tree (native tree-sitter flakiness; per-file processes and `ts_gate.py`
  were unaffected) and succeeds on the fixed tree.

### Next priorities (fix 97 follow-ups)

1. **511 remaining `return sub_*shared body` tails** (fix 94 list stands).
2. **`UnityAction<T0>` declaration LHS** (61 sites), **dead
   `Type type1 = typeof(Object);` lines** (2,791 sites), Review 87
   byte-store/noreturn-EH/leftover lists — all stand (see below).

## Current work — fixes 94, 95, 96 (gated + promoted 2026-09-13)

Tail-call honesty, void-caller tails, and a `_value_cse` allocation hole,
found by reading `AudioVolumeSliders.Start` end to end. Gates: **462
tests (446 + 16 new); direct sweep 116,178 methods / 0 crashes / 0
structural changes vs fix 92 (3,879 bodies changed, net +1,466 lines,
3,405 line-neutral); strict build 11,107 files / 115,658 bodies / 0
failures or fallbacks (`work/review94_out`); parser 0 bad files**.
Reports: `validation_reports/review94_sweep.json`,
`review94_vs92.json` (3,879 changed, 0 structural),
`review94_comparison.json` (vs Review 84: 17,843 changed, same 4
pre-existing fix-91 structural entries, 0 new crashes),
`review94_parse.json`; built tree `work/review94_out`. Promoted
2026-09-13: `final_out/` now holds `work/review94_out` (11,200 files,
candidate and promoted aggregate sha256 both
`6ec3c6f45deb2f653c1f3bf02053a82251c322f169f5b0df7c8f0249b64e679b`, 0
mismatches; the Review 89 tree is kept at
`bckups/final_out_review89`, the fix-91 tree at
`bckups/final_out_review88`, the Review 84 tree at
`bckups/final_out_r84`). Promotion record:
`validation_reports/review94_promotion_verification.json`;
post-promotion parse recheck
`validation_reports/review94_recheck_parse_final.json` (11,107 files, 0
bad). `validation_reports/SHA256SUMS.txt` still pins the Review 84 era
(prior promotions likewise left it; see the split notes). The 64 goldens
were regenerated after individual review of all 5
diffs (4 void-shape, 1 shared-ctor-tail initializer).

- [x] Fix 94: shared tails strip the hidden instantiation argument
  (exact-text identity proof, trailing-position + single-spec
  tightenings), trim trailing stale unknowns (fix-58 mirror), and render
  the true generic callee instance-folded; resolved ctors take the
  `..ctor` pseudo-form the emitter promotes (`_tail_hidden_generic`,
  `_tail_trim_stale`, `_tail_generic_call` in `il2cpp/lifter/calls.py`,
  wired into both tail-jmp paths). Ground truth: the Start tail's
  `mov r8,[slot]` + dispatch-through-R8 body proves R8 selects
  `UnityEvent<float>.AddListener`, which the 8 listed candidates (all
  zero-arg TypeTraits getters) miss — so NO max-arity trim: the
  candidate set is provably incomplete (a cap of 0 wiped real args in
  testing). `return sub_*shared body` tails fall 1,939 → 511.
  Regressions: `tests/test_review94_tails.py` (12 portable).
- [x] Fix 95: value-returning tails in exact-metadata-void callers render
  `<call>; return;` (`_caller_is_void`, `_emit_tail`; each site keeps its
  `/* tail */` habit). Covers resolved, shared, array-new, and
  generic-resolved tails in both paths.
- [x] Fix 96: `_value_cse` never caches `new` allocations (fresh identity
  per execution; parameterless `new T()` slipped past `_IMPURE`).
  Restores wrongly aliased objects, e.g. all 133
  `StructWrapper<byte>` pool instances in `StructWrapperPools..cctor`
  (+132 lines there). Regressions:
  `tests/test_review96_value_cse.py` (4 portable).

### Next priorities (fixes 94-96 follow-ups)

1. **511 remaining `return sub_*shared body` tails** have no trailing
   hidden identity (absent, non-trailing, or conflicting). The registry
   misses true sharers (fix 94 proof), so closing these needs sharer
   discovery beyond `addr_candidates`, never a max-arity guess.
2. **`UnityAction<T0>` declaration LHS** (61 sites): open-signature hints
   type the declaration while the `new` RHS is closed. Propagate the
   closed RHS type when the hint is an unresolved generic parameter.
3. **Dead `Type type1 = typeof(Object);` lines** (2,791 sites): bound
   results of side-effect-only class-init calls. Drop the result binding
   for class-init helpers.
4. **Review 87 list stands:** untyped `((byte*)+0)[0] = 4294967294`
   stores, five sub-threshold noreturn EH targets, 15 constructor
   leftovers, `object objN` / empty-allocation provenance, ABI gaps,
   8,067 into-block gotos, vector/ARM64/fixture breadth.

## Current work — Review 87 (fix 92, gated 2026-09-11, promoted 2026-09-12)

`docs/reviews/REVIEW87.md`, `validation_reports/review85/sweep4.json`,
`sweep4_comparison.json`, and `parse4.json` describe one source fix (92):
MethodSpec instantiation indices are zero-based with -1 absent. Gates:
**435 tests (317 portable + 64 snapshots + 54 native); strict build 11,107
C# files / 115,658 bodies with 0 failures or fallbacks
(`work/review89_out`); parser 0 bad files; direct sweep 116,178 methods /
0 crashes / 0 new structural changes vs Review 84 (same 4 fix-91
entries)**. Promoted 2026-09-12: `final_out/` now holds `work/review89_out`
(11,200 files, candidate and promoted aggregate sha256 both
`0b906f7d1c8ab400a8718f745df1182bad9e9ffbb55a2bea18c30f51839323b5`, 0
mismatches; the fix-91 tree is kept at `bckups/final_out_review88`, the
Review 84 tree at `bckups/final_out_r84`). Promotion record:
`validation_reports/review85/promotion_verification_review89.json`;
post-promotion parse recheck
`validation_reports/review85/recheck_parse_final.json` (11,107 files, 0 bad).
Note: this section previously reserved "candidate fix 92" for the two
named raisers; that unshipped candidate is renumbered to fix 93.

Completed in this batch:

- [x] Read `classIndexIndex`/`methodIndexIndex` zero-based in
  `generic_method_name` and `_method_spec_type_args`, with -1 as the only
  absent spelling (row 0 is a real instantiation). Proved over all 175,736
  specs: zero-based matches every declared generic arity (32,671 method +
  144,977 class rows, zero exceptions), one-based contradicts 2,749.
  Evidence: `work/review89_spec_arity_census.py`,
  `work/review89_spec_index_base.py`.
- [x] Fixed `Object.Instantiate<Font>`: 66 sites become `GameObject`, 0
  `Font` remain; every generic name steps off its neighbouring row
  (`EpilepsyHandler` -> `ComputeShader`, `Obi.*` -> `Vector2`/`byte`/
  `TouchPhase`/etc.). 16,119 bodies changed, all name-only; inventory and
  line-count shape unchanged.
- [x] Regenerated the 64 golden snapshots: 5 reviewed generic-name changes,
  59 unchanged. Regressions: `tests/test_review89_spec_indices.py` (11
  portable); `tests/test_shared_returns.py` updated to the proved spelling.

### Next priorities (Review 87)

1. **Type the untyped `((byte*)objN + 0x0)[0] = 4294967294;` stores.**
   Carried over from Review 85: the lvalue has no declared width, so the
   immediate cannot be sign-flipped on evidence yet.
2. **DONE - fix 93 shipped 2026-09-13: the two named raisers render as
   `throw new`.** `raise_IndexOutOfRangeException` /
   `raise_NullReferenceException` are each one specific new exception raised
   by a `sub rsp,X; call T; int3` noreturn forwarder, so
   `object objN = raise_NullReferenceException();` becomes
   `throw new NullReferenceException();` (0 old-style sites remain, 834
   throw-new sites in `work/review93_out`). Gates: 446 tests (436 + 10 new
   in `tests/test_review93_named_raise.py`); direct sweep 116,178 methods /
   0 crashes / 0 structural changes vs fix 92 (76 bodies changed, -76
   lines); strict build 11,107 files / 115,658 bodies / 0 failures; parse
   gate 0 bad files. Reports: `validation_reports/review93_sweep.json`,
   `review93_vs92.json` (`review93_comparison.json` vs Review 84),
   `review93_parse.json`. Predicate: exact evidence-derived name, arity 0,
   unregistered target, forwarder shape (`_named_raise_throw` in
   `il2cpp/lifter/calls.py`, wired into `_call` and both tail-jmp paths).
3. **Prove the five sub-threshold noreturn EH targets**
   (`0x180435040`, role-ambiguous `0x1804346b0`, `0x180434690`,
   `0x180001ea0`, `0x180002070`) with evidence other than witness counts,
   then tighten per-method/proven-set agreement.
4. **Review 84 list stands:** 15 constructor leftovers, 112,423
   `object objN` declarations, 13,254 empty allocations, ABI gaps, 8,067
   into-block gotos, vector/ARM64/fixture breadth (see the Current
   replacement section below).

## Previous work — Reviews 85 and 86 (2026-09-10/11)

`docs/reviews/REVIEW85.md` and `validation_reports/review85/` describe five source fixes
(85-89), one validation-tool fix, and one newly diagnosed defect. Gates:
**399 tests (289 portable + 64 snapshots + 46 native); strict build 11,107 C#
files / 115,658 bodies with 0 failures or fallbacks; parser 0 bad files;
direct sweep 116,178 methods / 0 crashes / 0 structural-metric changes / 0 new
crashes vs Review 84**. Promoted 2026-09-11 (itself superseded 2026-09-12 by
the Review 87 promotion; the fix-91 tree is kept at
`bckups/final_out_review88`): `final_out` then held
`work/review88_out`, the tree gated after fixes 90, 91, 91b, and 91c (11,200
files, candidate and promoted aggregate sha256 both
`0ef7607e317dbb00f59ad72ccaa8089b36ccf0a79c42bae7f525ebeb30118d00`, 0
mismatches; the Review 84 tree is kept at `bckups/final_out_r84`).
`work/review86_out` was never promoted. Gates for that tree: 424 tests,
strict build 11,107 files / 115,658 bodies / 0 failures, parse gate 0 errors
and 0 recovery nodes, direct sweep 116,178 methods / 0 crashes, 64 goldens
regenerated with 0 changes. See `docs/reviews/REVIEW86.md`.

Completed in this batch:

- [x] Decode enum member tables through the enum's underlying element type
  with the compressed (zigzag) reader. The old raw fixed-width read doubled
  every value and invented junk members; eight member names are confirmed
  wrong before and correct after, including `DateTimeKind.Utc` -> `Local` and
  `Token.XdrDatatype` -> `XsdSchema`.
- [x] Fold enum-valued call arguments to `Type.Member`, so
  `new FileStream(text2, 3)` becomes `new FileStream(text2, FileMode.Open)`.
- [x] Stop `_int_lit` stripping the hex digits `d` and `f` as float suffixes.
  It had read `0x3d` as 3, `0x7f` as 7, and `0xf` as unparseable.
- [x] Fold literal-base address composition, `(0 + 0x3)` -> `3`, without
  touching `_field_expr`'s dereference form.
- [x] Reinterpret immediates at their declared signed width, `4294967294` ->
  `-2`; 188 rewrites in the first 4,000 methods. Unsigned and native-int type
  codes deliberately excluded.
- [x] Relocate sweep manifests relative to the report that names them, fixing
  moved-report reads on Windows.
- [x] Regenerate the 64 golden snapshots: 9 changed, +37 / -37 lines, every
  changed line an enum-member fold.

### Next priorities (Review 85, historical; use the Current work list above)

1. **DONE - EH helper naming is now evidence based (fixes 90, 91, 91b, 91c).**
   `_seh_helpers` used to discover the raise/rethrow VAs from whichever method
   was lifted first and write them onto the shared lifter, so output depended
   on process partitioning and lift order. That part was right, and it still
   explains 1,913 of the 10,758 changed bodies in that batch, which are **not**
   attributable to fixes 85-89.
   The rest of the diagnosis above was wrong about which side was correct. A
   census of all 4,526 pad-bearing methods found 99 distinct rethrow targets
   and 9 raise targets, and 51 of the rethrow targets were ordinary registered
   methods -- `AsyncTaskMethodBuilder.SetException`, `Debug.LogException`,
   `Marshal.FreeHGlobal`, even `DateTime.AddYears` -- so a large share of
   those 3,113 `throw` statements were leaked values that had each eaten a
   real call, not correct output.
   Fix 90 clears both fields for every method and requires an unregistered
   native target. Fix 91 then proves the pair once from the whole binary:
   `0x180435740` rethrow (3,403 witnesses against 126) and `0x180435670`
   raise (183 against 25). Fix 91b rejects plumbing the lifter can already
   name, directly or through a jmp thunk -- `0x180435420` is a thunk onto
   `il2cpp_codegen_initialize_runtime_metadata` that 181 methods had taught
   as a helper -- and fix 91c rejects any routine with a reachable `ret`,
   which removed five impostors including the 45-witness `0x180002650`.
   Evidence: `work/review87_helper_census.py`,
   `work/review87_helper_classify.py`, `work/review88_helper_ident.py`,
   `work/review88_anchor_diff.py`, `work/review88_sample.py`. Regressions:
   `tests/test_review87_eh_helpers.py`,
   `tests/test_review88_eh_helper_set.py`.
   Still open: five noreturn but sub-threshold targets (`0x180435040` 13/0,
   `0x1804346b0` 12 rethrow against 13 raise, `0x180434690` 8/0,
   `0x180001ea0` 6/0, `0x180002070` 3/0) remain on per-method evidence only,
   and the two named raisers still render as calls rather than
   `throw new IndexOutOfRangeException();` / `throw new
   NullReferenceException();` -- candidate fix 92 (renumbered to fix 93, since
   fix 92 shipped the MethodSpec base; see the Current work section).
2. **Type the untyped `((byte*)objN + 0x0)[0] = 4294967294;` stores.** The
   lvalue has no declared width, so the immediate cannot be sign-flipped on
   evidence yet. Recover the store type and width first.
3. **DONE - Fix the wrong generic argument in `Object.Instantiate<Font>`.**
   Shipped as fix 92; see the Current work section above and `docs/reviews/REVIEW87.md`.

## Current replacement — Review 84 (2026-09-10)

`docs/reviews/REVIEW84.md`, `docs/archive/reviews-log.md` §0bb, and `validation_reports/review84/` describe the
current source and complete output. Release: **358 tests (260 portable + 64
snapshots + 34 native); strict build 11,107 C# files / 115,658 bodies with 0
failures or fallbacks; parser 0 bad files; direct sweep 116,178 methods / 0
crashes / 0 structural-metric changes; constructor sweep 11,737 methods / 0
crashes**. The original DLL/metadata remain unchanged and were read statically,
never executed.

Completed in this release:

- [x] Complete class inheritance chains through a unique
  `IL2CPP_TYPE_OBJECT` → `System.Object` mapping, stop cycles, and isolate
  inheritance/field caches per `Il2Cpp` instance.
- [x] Resolve folded parameterless constructors only from typed current-ctor
  `this` or exact fresh-allocation provenance, one concrete closed MethodDef,
  a reference-type inheritance match, and exact instance/void/zero-argument
  metadata. Decline generic, multiple-match, byref, value-type, or malformed
  cases.
- [x] Distinguish same-type `: this(args)` from ancestor `: base(args)` and
  recover parameterized resolved initializers without leaving raw pseudo calls
  in generated C#.
- [x] Carry exact `_alloc` provenance through binding/copies and complete one
  allocation declaration in place. Audited discarded constructor allocations
  fall 13,292 → 0; empty allocation declarations fall 21,624 → 13,254.
- [x] Reduce `sub_180506120` constructor-family markers 2,958 → 160, legacy
  `this.ctor(...)` text 2,186 → 45, all shared calls 21,504 → 18,703, and
  `object objN` declarations 113,155 → 112,423.
- [x] Increase real `: base(...)` initializers 5,960 → 9,530 and
  `: this(...)` initializers 0 → 325 while shrinking generated C# by 20,568
  lines with no file-inventory change.
- [x] Preserve unrelated shared-call behavior by excluding the newly visible
  Object tail from the broad legacy receiver heuristic; freeze the regression
  where `System.Type.op_Equality` must not become an Object method.
- [x] Freeze the same 64 MethodDefs in `goldens_review84.json`: 56 unchanged and
  eight reviewed constructor/allocation changes.
- [x] Strict-build, overlap-verify, parse, directly sweep all methods and all
  constructors, compare, test, promote, checksum, and package the complete
  replacement.

### Next priorities (current, not archived diagnoses)

1. **Prove the 15 conservative constructor leftovers.** Twelve native
   constructors still contain `sub_180506120` because multiple eligible
   ancestor constructors share it; three complex generic/scope constructors
   retain `this.ctor(...)`. Add receiver/generic proof, never a cosmetic guess.
2. **Trace the producers of the remaining 112,423 `object objN` declarations.**
   Recover register seeds, stack-slot reads, local copy/store provenance, and
   alias identity. Type the producing value before changing its declaration.
3. **Finish allocation and indirect-call identity.** Classify the remaining
   13,254 empty allocations, virtual/function-pointer constructor targets, and
   cyclic allocations with dominance and per-iteration alias proof.
4. **Complete missing return/call ABIs.** Generic value-type instantiated sizes,
   source-level `ref` returns, non-address hidden buffers, mixed candidates, and
   broader stack/vector arguments need explicit models and negative tests.
5. **Finish legal structured control flow and compilation readiness.** 8,067
   into-block gotos remain across 2,047 methods, along with definite assignment,
   project references, constructor/SEH, identifier/type, and ref-return issues.
6. **Vector, ARM64, and fixture breadth.** General packed-lane state, ARM64
   semantics, and an independent licensed fixture remain open.
