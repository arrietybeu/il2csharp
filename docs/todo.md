# il2csharp — TODO (open work and historical triage)
## Current work: recovery follow-up round 3e (2026-09-20, unpromoted)

Continued TODONOW.md's blockers 1-3 plus cosmetic items 4-5. Same rules:
`final_out/` untouched, no snapshot regen, no promotion. All `il2cpp/`
edits via binary patches with CRLF/no-BOM asserts; `tests/` edits LF.
`tests/test_recovery_completion.py` grows 5 -> 17 synthetic tests;
`tests/test_game_synth_types.py` pins 4 synthetic-type behaviors.
Accessor-receiver hint (`_hint_accessor_recv` at the `set_` fold):
a resolved instance accessor proves its receiver through the
non-generic declaring typedef (slots/bare `t`-temps; byref-`this`
homes for valuetypes; dotted/`this`/generic/static/foreign kinds
decline). 23762's key is now `Selectable selectable1` with a
guarded typed assignment. 2 unit tests.
Copy-prop type guard: registering `dst = src` declines when both
sides declare different concrete non-object types (a struct home
copied over a typed temp is not value-preserving). Keeps 23762's key
and assignment from merging into the enumerator name; same-type and
object copies fold as before. 2 unit tests. Residual: `Selectable
selectable1 = dictionary22;` over-claims a 16-byte lane copy as a
full-struct copy (pre-existing whole-slot convention); single naming
forces one error site either way -- documented, awaits byte-range
slot versioning (the sidecar).
S6 layout steps (subagent-verified byte-exact vs native): nested-open
fields close through enclosing args in `_sf_infl_chain` (`_current`
carries closed KVP); `returns_sret` admits closed 0x15 with proved
size outside {1,2,4,8} (72-byte Enumerator folds the hidden buffer;
unproven shapes keep the fix-54 stand-down).
Candidate-tree gate for the five affected types (ConsoleUINavigation,
GlobalUINavigation, CollisionEventHandler, AnimationEventTrigger,
MicAudioCanvas, `--types` one build each into Temp): strict build 54
bodies / 0 failed / 0 fallbacks; tree-sitter parse 0/0/0; Roslyn probe
83 errors, all CS0246 missing-assembly scope noise, none on any
recovered identifier; before/after diff strictly improving (no more
elided static stores, unsafe raw blocks, or object soup where typed).
Full-tree compile remains a promotion-time gate.

- Blocker 2 LANDED (24655 OnEnable): the `t1012__1_0` store was NOT a
  `_mem_lvalue` bug (probe: `_field_expr` renders the correct
  `ConsoleUINavigation.<>c.<>9__1_0` every time). Root cause is
  `_bind`'s blind `str.replace`: binding `...<>c.<>9` rewrote the
  longer field name mid-identifier. New `_bind_replace` (`expr.py`,
  used at all 10 `_bind` sites in `lifter/state.py`) rewrites
  whole-token occurrences only (member access on the value still
  folds). Store now reads `ConsoleUINavigation.<>c.<>9__1_0 =
  predicate13;`. 3 unit tests.
- Blocker 3 LANDED (23761 DisableAllActiveSelectables): three parts.
  (1) `_hint_arg_types` `&slot` branch now types by-VALUE struct homes
  from the substituted closed parameter type (`&s_20` + TValue ->
  Navigation at `Dictionary.Add`; TRUST-gated like the `ref`
  rewrite, closed-key proof, setdefault). (2) Stack-slot stores of
  whole-field struct values record the type (`_struct_home_ty`:
  exact closed valuetype, no slices/parts/addresses). (3) A scalar
  constant at a struct-typed home's base renders field-precisely
  (`_home_field_store`: exact-width offset-0 field proof +
  `_fimm`-compiles gate, else today's scalar). Result: `Navigation
  navigation1` at `Add`, `navigation2.m_Mode = Mode.None`, no scalar
  soup; the home-construction residue stays (loop-DCE conservatism is
  load-bearing) but is fully typed and compiling. 3 unit tests.
- Blocker 5 LANDED (23917 contact): the lifter emits exactly one
  packed spelling, `(float2)(lit, lit)` over float literals (constant
  pool) -- provably pure. `_PURE_LOAD_RX` admits paren-free-arg
  `(float2)(...)` (mirroring the `typeof` carve-out; a later
  substituted call keeps parens and still declines), so the dead
  packed temp drops in ordinary DCE. Cyan kept. 1 unit test.
- Improvement (45016 ConvertTo): struct-home recording types the
  `TimeOfDay` temp (`object obj29` -> `System.TimeSpan timeSpan1`),
  fixing an object-member access that cannot compile. Consigned to
  the regen list (below), not reverted.
- Blocker 4 LANDED (`_subexpr_cse`, new pass after `_value_cse`):
  anchor decls (`num`/`obj`/`t`, single-assigned, pure RHS) lend their token
  to later subexpression occurrences (`num3 = num2 | num2 >> 16`). Purity is
  the exact `_value_cse` test (no auto `?` decline; one well-formed ternary
  required); kills mirror the strictest passes (depth/labels/goto/case/
  catch/finally/break-loop-frames/backward-gotos/stores/byref); fix-58b
  holds (calls/`new` never seed); whole-token replacement with atom-paren
  strip. Both pow2 sites fold (23761, 23767). 5 unit tests. Side effect:
  the 25626 offset chain compacts too (`num4 + bytePtr1`, was fully
  re-expanded) -- the pinning test over-fits the old spelling, consigned
  to regen, not a revert.
- Blocker 1 foundation LANDED (table + recursion + homes, zero blast radius):
  S4 (subagent) root-caused B11's loss: NOT a line pass but
  `_abandon_at_region_close` firing on the loop latch (region opened at
  the header, closed on the latch) and emitting `break` + deleting the
  block's statements -- flow inversion by construction. Fix in
  `dec/emit.py`: a latch block carrying statements emits label + stmts,
  marks consumed, emits the backedge copies, and falls off (the
  structured loop IS the backedge); empty latches keep the old
  break-out. 23762 now keeps `if (obj5 != null) { obj5.navigation =
  obj18; }`.
  S5 (subagent) corrected the call map (MethodRef kind-6 slots prove
  closed generic identities: GetEnumerator/MoveNext/Dispose/Clear over
  (Selectable, Navigation); no get_Current call; s_38/s_48 are silent
  aggregate fills) and designed home typing: `_proved_struct_home`
  seeds `slot_types` at proved-generic `info` sites (`&s_N`
  buffer/receiver + closed-struct substitution; static path additionally
  requires struct return and no byref/pointer params). 23762 now
  declares `Dictionary_2<...>.Enumerator dictionary21` with named
  MoveNext/Dispose. s_30 buffer typing skipped (size unprovable for
  open defs); key/value field subst still needs the sidecar.
  Fixed along the way: fake-VA allocator is process-wide (class-level
  `_tn_cache` is shared across Il2Cpp instances -- an order-dependent
  cross-test collision, caught by the suite).

  `_synthetic_inst` (fake-VA side table on `Il2Cpp`, keyed cache for
  dry/real stability) + reader branches (`_generic_inst_name`,
  `_closed_type_key`, `td_of_ty`, `_generic_inst_args`, `_td_of`,
  `_generic_class_args`, `_byval_struct`, `_type_has_var`) +
  recursive `_subst_closed` wired into `candidate_return_type`
  (all-or-None, byref preserved, tails untouched, SRET/`trust`
  stand-downs frozen). Proved on real rows: `Dictionary_2<Selectable,
  Navigation>.Enumerator` renders exact, keys structurally, td 1514
  round-trips; real specs close (`ChangeEvent_1<bool>`). 23762 itself
  is unchanged (no spec carries our args; interface path dominates) --
  the receiver-driven + field-sidecar slice stays next per blueprint.
- DEFERRED with designs (not regressed, still open): blocker 1 remainder
  (23762: no closed Enumerator/KVP rows exist by scan, so return
  substitution alone cannot represent the type; deeper: NO MethodSpec
  carries (Selectable, Navigation), so substitution must be
  receiver-driven (closed Dictionary row 6766 + open 11337 return), not
  spec-driven; `type_sizes[1514]` is None and its field chain shows only
  `_dictionary`, so size/field fast paths need the inflated chain; S1's
  consumer audit (exact touch list in session record) covers table +
  reader branches + recursion + home typing, but homes (0x15 excluded
  from `_struct_home_ty` by design) and field-type substitution at use
  sites still need a sidecar design -- table-alone buys ~2 decl lines
  for corpus-wide hot-path churn, so implementation waits for the full
  blueprint; key/value reads are
  field loads and the assignment loss is structural -- needs a
  synthetic nested-type table + home typing + receiver resolution +
  field substitution; the double Dispose is faithful, two native
  calls; the finally `obj14.Dispose()` on `&obj3` needs the same
  struct-typing machinery) and blocker 4 (power-of-two reuse needs
  subexpression-CSE/value-numbering: `_value_cse` is whole-RHS only
  and lifter `_bind` is per-OBJECT by fix-58b design; output is
  correct and compiling today).
- Crash fixes (prior drift exposed by volume, fixed narrowly): tied
  pending-call sort (`sorted` on Expr compare -> stable key sort +
  discovery order; 129 build fallbacks cleared); unknown-size
  `_stack_store` guard in the sret fold (3 lost bodies recovered);
  `_kill_one` preserves `_mi`/`_usg_idx` + delegate-index guard (8 sweep
  `list[None]` crashes cleared). 1 unit test; repro probes in Temp.
- Parse fixes (prior null-base-address drift): `_wb_operands` renders
  numeric dst as the twin-matching deref (`16 = v` unparseable);
  `_unsafify` repairs cast-prefixed `(T*)*N` (multiplication untouched);
  `_subexpr_cse` paren-strip declines call/type/index/shared-marker
  contexts (77059 + TextGeneratorUtilities cases). 3 unit tests.
- Crash repairs (prior volume exposing HEAD-latent bugs, all
  stash-proven not-mine): tied pending-call `sorted` on Expr compare
  (129 build fallbacks cleared, discovery order kept); unknown-size
  `_stack_store` in the sret fold (3 lost bodies recovered);
  `_kill_one` dropping `_mi`/`_usg_idx` + delegate-index guard (8 sweep
  crashes cleared). 1 unit test; repro probes in Temp.
- Parse repairs (prior null-base/bool drift, all stash-proven
  not-mine): `_wb_operands` renders numeric dst as the twin-matching
  deref; `_unsafify` repairs cast-prefixed `(T*)*N` (multiplication
  untouched); `_subexpr_cse` paren-strip declines call/generic/index/
  shared-marker contexts (77059 + TextGeneratorUtilities cases);
  `_bool_sugar` paren-wrapped folds take the `[^?]` guard (101899
  family); `_simplify_cond` requires whole-group negation
  (MinMaxAABB family). 5 unit tests.
- Parse-0 repairs (prior drift, each stash-proven not-mine except
  where noted): `_bool_sugar` paren-wrapped folds take the `[^?]`
  guard (101899 family: lazy group spanned `&`-joined ternaries);
  `_simplify_cond` requires whole-group negation (MinMaxAABB family:
  `!(A) & (B)` is not `!((A) & (B))`); `FOLD_RE` declines call-argument
  parens like `SUB_CMP_RE` (`s_28.ctor(0 + 1)` kept intact,
  XmlNodeConverter). 3 unit tests.
- Gates: strict rebuild 11,181 files / 114,458 bodies / 0 failed / 0
  fallbacks (matches promoted baseline exactly); brace 0 unbalanced;
  parse 0 bad / 0 ERROR / 0 MISSING (was 109 / 5349 / 33);
  portable 751 green (718 + 33 new); full suite 846 passed / 35
  failed, failure SET byte-identical across every stage. The 34
  = baseline triaged 22 + 12 inherited-drift items, EACH proven
  not-from-this-session (prior tree fails the same 12: P6 files 2,
  unpcklps handler 1, owner-strip 4+closure+45016-line, klass-bind
  gate 4 incl. 39789/packed/datetime/26747-guard; my tree adds only
  the 45016 TimeSpan improvement hunk). Per-item evidence in
  TODONOW.md's session addendum. No new failures from this session
  (the +1 vs the earlier 34-count is the 25626 improvement pinning the
  old spelling, plus 5 new CSE tests on the passing side).
- Leftovers: blocker-1 remainder (receiver-driven substitution +
  field sidecar + structuring, blueprint ready), Navigation merge-side
  facts, per-arm Color, 35 golden/review items awaiting gated regen
  (22 triaged + 12 drift + 1 improvement-pin), promotion (user call).


## Current work: recovery follow-up round 3d (2026-09-20, unpromoted)

Same rules: `final_out/` untouched, no snapshot regen, no promotion.
Portable 718 green; full suite 822 passed / 22 failed (identical triaged
set as 3c — the pass moved none of them).

- `switch(string)` phase 1 (`_hash_string_switch` in `flow.py`, after
  `_switch_synth`): Roslyn string-switch is a ComputeStringHash
  binary-search + per-arm string-equality confirm; ranges only route,
  confirms dispatch. FNV-1a/32 over UTF-16 units verified against 20
  observed constants; every leaf proves itself (unanimous
  ComputeStringHash callee via IL candidates, literal FNV == arm hash
  const, pairwise-distinct hashes, String Equals/op_Equality callees,
  no rebindable flow or S/H refs, H dead past tree, >=3 cases).
  Handles direct `==`, temp-mediated and inline Equals confirms, and
  negated `if (!V) {} else {}` pass-time shapes; declension for gotos,
  loop arms, collisions, unverified leaves. Dead literal/equals temps
  collected downstream. Folds 25293 (8 cases), 24765 (8 cases +
  breaks), twins 25577/26314; 24694 declines honestly (gotos).
  Post-fold hardening: unjumped labels allowed in arm prefixes (26314
  has two dead ones; jumped labels abort anywhere since C# forbids
  jumping into a switch section and dropped labels dangle), plus a
  cross-arm/outside-span temp-use post-check (prefix temps vanish with
  the span). Full suite 822/22 identical triaged set.
- Per-arm Color: deferred with evidence, no source change. All three
  repro shapes flow through phi copies into Color-typed sinks (26794
  `Color color1`, 27827 `.color = ternary`, 23917 `set_color`), but
  text level cannot recover the hidden B/A channels from `(float2)`
  display, and rendering all four floats churns 1445 corpus sites in
  352 files for 8 cosmetic sites (values are correct 16B throughout;
  only display is lossy). Needs use→def const rewrite machinery.
- Leftovers: Navigation merge-side facts, 22 goldens awaiting gated regen.

## Current work: recovery follow-up round 3c (2026-09-20, unpromoted)

Same rules: `final_out/` untouched, no snapshot regen, no promotion.
Portable 718 green; full suite 822 passed / 22 failed (70050 + 107123
restored to golden, no new breaks; remaining 18 snapshots + 4 review
tests match prior triage).

- SIMD twin-consistent, both shapes (design: twin-unanimity with
  raw/honest fallback; looseness is cosmetic-only, never wrongness).
  - Shape B (107123 vorn_u32 -> `/* nothing */`): `_dead_shared_forwarder`
    in `calls.py` declines the pending bare-statement when the caller VA
    is multi-candidate, the target is single-candidate, and the next
    insn is int3/ud2. Single-caller `RemoveAll` still flushes.
  - Shape A (70050 double3x3 negate, byte-exact golden): `_xor_twin_load_sites`
    scan in `build.py` (sqrt-site precedent) proves same -0.0 const +
    same base reg + packed-16/scalar-8 adjacency; scalar loads decline
    member sugar in `_aggregate_load` + `_field_expr`, the `_R4_TY`
    width rule restores `byte*`, textpass renders the golden.
- Event `+=`/`-=` folds mirroring `set_` (void-gated, 3 unit tests);
  native-list `.Count` for field receivers; exact `<T>` narrowed to
  method-level args after a live misfire; assignment-ternary bool
  materialization with all-uses retype.
- DISPROVED with evidence (no source change): Navigation phi-atom
  read-side acceptance. The phi atoms are Navigation-typed chunks
  (v165/v166), so the bool Wrap field can take neither (compile break
  under loose naming; `v166.m_Mode` misread via struct-chain). Needs
  merge-side unanimous-subrange preservation (the stuck design).
- Censuses (read-only, JSON under `%TEMP%/opencode`): hash-switch
  family is real — ComputeStringHash + range splits + string confirms,
  single-write pure temps (25293 FPSController.ConvertStringToKeyCode
  smallest complete + 4 twins, 24765, 24694 with loop-continue arms);
  divergent color ternaries in 8 methods (23917 contact red/green
  headline, 27827 3-way, 26794 if/else stores).
- DEFERRED with designs (not regressed, still open): per-arm Color
  (bytes lost at text level; load can't know Color vs Vector2 — needs
  consumer-type proof); Navigation merge-side design.
  (`switch(string)` landed in 3d below.)
- Leftovers: 22 triaged goldens (regen only after gates).

## Current work: recovery follow-up round 3b (2026-09-20, unpromoted)

Subagent-assisted fixes + reverts. Same rules: `final_out/` untouched, no
snapshot regen, no promotion.

- Exact generic `<T>` call tokens (method-level args only; type-level
  declined after a misfire caught by golden 21027).
- COUNT macro simplified to two shapes; native-list field receivers.
- Assignment-ternary `? 1:0` materialization with all-uses-bool retype;
  phi-decl hoist (mic block fully bool-typed; Update verified).
- Ambiguous-shape slot kill (32837 zeros gone); name-shadow renames.
- Reverted with evidence: full SIMD tracking (stash-proven 0 wins, broke
  twins/sqrt in 3 goldens), partial structs (undeclared slots),
  identity/single-origin folds.
- Gates: portable green; game goldens hold prior fixes (31361/2, 45016,
  21027, review83 typed-shared, review81).
- Leftovers: Navigation path-sensitive facts, color ternary arms, full
  SIMD redesign (twin-consistent), 24 triaged goldens (regen vs genuine:
  32837-shape, 104428-tail, 32832/11974 unclear).

## Current work: recovery follow-up round 3 (2026-09-20, unpromoted)

Subagent-assisted round (4 analyses + 2 implementations, all gated).
Same rules: `final_out/` untouched, no snapshot regen, no promotion.

- Exact generic `<T>` call tokens from proved slot identity (method-level
  type args only; generic-type case declined after a misfire).
- Byref params kill slot caches (80548 head back); ambiguous-shape calls
  union-kill arg0 slots (32837 stale zeros gone); `.ctor`-on-stack-buffer
  records construction (31664 whole).
- VT-echo/exact-first guards (m_State/m_StateBlock); fragment type
  preservation (104428 call type); static RGBA bytes to Color (generalized
  structs, phi-bytes infra that honestly declines divergent arms).
- Ternary bool reconciliation, assignment `? 1:0` materialization with
  all-uses-bool retype, phi-decl hoist (mic block fully bool-typed);
  native-list `+0x28` Count sugar incl. field receivers.
- Reverted with evidence: full SIMD tracking (0 wins, broke twins/sqrt in
  3 goldens — stash-proven), partial structs (undeclared slots),
  identity/single-origin folds.
- Gates: portable 718 green (45 followup tests); full suite 816 passed / 24 failed, every failure triaged
  (improvements-awaiting-regen vs genuine: 32837-shape, 104428-tail,
  32832/11974 unclear, 83s neutral/brittle).
- Leftovers: Navigation path-sensitive facts, color ternary arms, full
  SIMD redesign (twin-consistent), per-golden regen only after gates.

## Current work: recovery follow-up round 2 (2026-09-20, unpromoted)

Continues the prior session (committed 5b13c9d). Same rules: `final_out/`
untouched, no snapshot regen, no promotion. CRLF/no-BOM kept via binary
patches; `tests/test_recovery_followup.py` (LF) now pins 40+ behaviors.

- Exact-tiling composites with per-tile routing (`_parts`), proven-prefix
  recording, fragment type preservation, slot-type fill on composites.
- Ignored-call flush twin-proofed (mov-copies, phi copies, rendered text);
  ambiguous-shape calls union-kill arg0 slots; byref params kill slot
  caches (viscosity head back); `.ctor`-on-stack-buffer records.
- Call rendering: exact generic `<T>` tokens (method-level args only),
  VT-echo/exact-first guards (`.m_State`/`.m_StateBlock` back),
  List `.Count`, native-list `+0x28` `.Count` sugar, static RGBA bytes to
  `Color.*`/`new Color` (+ generalized RGBA structs).
- Dec passes: ternary bool-arm reconciliation, assignment-ternary `? 1:0`
  materialization with all-uses-bool retype, phi-decl hoist (Update mic
  block fully bool-typed; enum decls via hint-guard; IntPtr tests null).
- Reverted with evidence: partial struct assembly (undeclared slots),
  identity/single-origin folds, fragment re-root reversal confusion.
- Fixed-then-verified regressions: 31664 ctor/store/return, 32837 stale
  zeros, 104428 call type, 31361/2, 45016, 126258 null-check, 5769 byte.
- Gates: portable 711 green; full suite ~807 passed / 24 failed, every
  failure triaged (improvements-awaiting-regen vs genuine: 32837-shape,
  104428-tail, 32832/11974 unclear, 83s neutral/brittle).
- Leftovers: Navigation path-sensitive facts, color ternary arms, SIMD
  lanes, `GetComponent` (done), mic scope (done), per-golden regen only
  after gates.

## Current work: decompiler recovery follow-up (2026-09-19, unpromoted)

Continues `nowtodo.md` (2026-09-19 stop record, committed alongside): the
experimental aggregate/interface/null-edge work plus new fixes below. Nothing
here is promoted: `final_out/` untouched, no snapshot regen, no rebuild. All
`il2cpp/` edits kept the CRLF/no-BOM contract (binary patches with
line-ending asserts); `tests/test_recovery_followup.py` (LF) pins the new
behavior (38 tests).

- Aggregate audit: `_write_mem` no longer suppresses sliced stack stores
  (suppression + merge-killed slices produced undefined temps; contact's
  `obj22` is now a defined `contact1.pointB.x`), mem-facts keep the value's
  refined text, exact-tiling composites route per-tile (`_parts`), narrow
  provenance records its prefix, valuetype loads fall through on degraded
  fragments, reference loads defer to exact `_field_expr` hits.
- Ignored non-void calls flush once as bare statements at defpos after phi
  destruction (replaces bind-everything; used calls stay inline; twin-proofed
  against mov-copies and phi copies). `RemoveAll` retained in OnEnable.
- Write barriers and `.ctor`-on-stack-buffer record their stores; byref
  params kill the slot cache (viscosity `num1<num2` + stride back).
- LEA names unified to the `slot_var` convention (no more `s_ffff…`
  aliases); MOVDQA/MOVDQU stores/loads handled; List `+0x18` renders
  `.Count`; static RGBA bytes render `Color.*`/`new Color` via `_color_text`.
- Proven-type beats instruction-shape hints (`InputMode` decls back);
  IntPtr/UIntPtr (any TE spelling) test against null; unknown-kind TESTs
  stay null-style.
- Fixed goldens now passing: 31361/2 (`.m_State`), 32833 field
  (`.m_StateBlock`, entry drift remains), 31664 (ctor/store/return),
  45016, review80-touchscreen. Remaining 24 failures triaged per item
  (several read as improvements pending gated regen; open regressions:
  32837 value→zero folding, 104428 call-absorbs-select, SIMD-lane vectors,
  color ternary arms, Navigation full struct, `GetComponent<T>` args).
- Gates: portable 695+ green; full suite 803 passed / 24 failed (HEAD
  stash-proves-clean at 795/795, so all 24 are working-tree drift).

Leftovers: Navigation struct assembly needs path-sensitive facts
(first-item skip-join legitimately phis); contact color arms + SIMD lanes +
custom `+0x28` count; mic bool/int `SetActive` + PTT flag scope; item 9
(hash-switch/events) correctly deferred; per-golden native review before
any regen/promotion.

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

## Current work: unavailable method bodies (committed 3bf35b3, pushed 2026-09-19)

Concrete methods with no native address now emit a throwing body instead of
an illegal semicolon declaration. The shared body path also covers accessors,
declaration-only output, unavailable lifting backends, and method limits.
Abstract/interface contracts retain semicolons, and successfully recovered
empty bodies remain empty. Missing bodies throw `NotImplementedException`
with an explicit recovery message; these are placeholders, not recovered
implementations, and do not increment lift/failure/fallback counters.
The final namespace-shortening pass preserves alias-qualified names such as
`global::System.NotImplementedException`; stripping `System` there would bind
the exception in the global namespace instead.

Regression coverage compiles generated constructors, ordinary and explicit
interface methods, indexers, properties, and events with Roslyn in all three
unavailable-body modes. Committed evidence: `validation_reports/method_bodies_{parse,
delta,regeneration}.json`; build/compile/tests logs were removed in the
2026-09-19 cleanup. Candidate tree `work/method_bodies_out/` was removed in
the same cleanup (superseded by `work/rpc_payload_out/` below).

Gates: 795 tests pass (669 portable + 126 native); strict build 11,181 files /
114,458 lifted bodies / 0 lift failures / 0 structured fallbacks / 0 type-emission
failures. After the namespace correction, 1,005 files containing `::` were
regenerated through the emitter (21,944 lifts, all failure counters zero),
copied back by TypeDefIndex with full-build shared stubs retained; provenance
and final source fingerprints are in `method_bodies_regeneration.json`.
Final parse: 0 bad files / 0 errors / 0 recovery nodes. Compiler probe:
10,305 → 2,463 errors, 1,516 → 726 files with errors; CS0501 7,718 → 0,
CS0535 88 → 0, CS0073 26 → 0, CS8051 9 → 0, CS0523 1 → 0. Other diagnostic
counts are unchanged. The tree contains 9,193 explicit unavailable-body throws;
it still does not compile or provide those implementations. No control-flow
lifting changes were made. Next largest category is CS0737 (880), followed by
CS0111 (384) and CS0052 (308).

Duplicate-method triage must distinguish actual emission collisions from the
combined-assembly probe: for example, `IsUnmanagedAttribute` has one constructor
in each source assembly, but combining those partial types produces CS0111.
Deleting those constructors would damage the individual recovered assemblies.

## Current work: accessor recovery + RPC payload typing (committed 3bf35b3, pushed 2026-09-19)

Committed tree stacks two units on the promoted fix-123 tree:
`il2cpp/csharp.py` + `emitter.py` + `runtime/fields.py` (storage identity
`__field_X`, real property/event bodies; `tests/test_member_recovery.py`,
`tests/test_game_member_recovery.py`) and `il2cpp/lifter/{state,insn,values}.py`
+ `runtime/types.py` (pointer/array operand typing, below). `final_out/` still
holds fix 123; `work/accessors_out/` and `work/rpc_payload_out/` were the two
gated candidate trees (both 11,181 files, 0 failed lifts, parse 0/0/0).
`work/accessors_out/` was removed in the 2026-09-19 cleanup;
`work/rpc_payload_out/` is the retained newest output and matches the pushed source.

RPC payload typing (specimen InventoryManager.Rpc_CMD_UpdateInventoryForHost,
mi 25626, VA 0x180704750): unbound `obj1` and `object` payload arithmetic are
gone — `inventoryIds_.Length`, `byte* bytePtr1 = (byte*)simulationMessagePtr1
+ 0x1c`, `int` offset chains, `((int*)bytePtr1 + off*1 + 0x0)` stores, one
`num5` temp. Fixes: RBP-as-frame is now value-tested (`_rbp_is_frame`: None /
`&s_xx` / `?addr` / never-written stay slots; params/objects/composites
resolve normally); array-typed entry params carry kind `arr` ([arr+0x18]
folds to `.Length`); `lea` over int is int math while past-struct lea from a
typed pointer spells a `(byte*)` cursor from a genuine metadata `byte*` row
(temps declare `byte*`); int-base + byte*-index SIB renders pointer-first at
scale 1 only; long binop operands bind typed instead of minting anonymous
twins; ADD int+ptr yields ptr (byte-proven type only); `.Length` carries Int32;
empty vtable rows (raw 0x1, no method bits) decline instead of naming mi 0
(healed three pinned `Interop.GetRandomBytes` misresolutions: 39789 hunks,
83647, 109664). Gates: 665 portable + 126 game pass (10 new lifter unit tests
in `tests/test_pointer_operand_typing.py`, 4 game asserts in
`tests/test_game_rpc_payload.py`); sweep 116,178 / 0 crashes / 0 new crashes /
1 structural delta (mi 37884 into_block 1→0, +1 line, nothing dropped);
9,200 changed bodies vs accessors; rebuild 11,181 files / 114,458 bodies / 0
failed; parse 0/0/0; probe 10,305 errors, per-code identical to accessors
(all 1,393 pair moves are line-number shifts). Committed evidence:
`validation_reports/rpc_payload_{parse,sweep}.json` plus
`rpc_payload_sweep.tail-args.jsonl.gz`; build/compile/sweep logs were removed
in the 2026-09-19 cleanup. Retained tree: `work/rpc_payload_out/`.
14 goldens regen'd after review (8 accessor renames untouched by this unit +
6 here: 39789/62312/83647/109664 improvements, 11974 renumber, 5769 noted below).

Open follow-ups: GetChars (mi 5769): merge type preservation for cmov-selected
values is done -- the pass wipe ran after entry setup and discarded the stack
parameter names/types, so the decoder arrived at the cmov as untyped `s_88`;
wiping before setup plus slot reloads restoring the recorded kind recovers
`baseDecoder`/`getClass()`/`charCount`/`_mustFlush`/`_bytesUsed` (was: undeclared
`num3`, then raw decoder derefs). Widths are done: a CMOVE
`recv.getClass() == typeof(T)` selecting `recv` stamps the exact type (klass
equality is exact, unlike `is`; the compared `typeof` usage already carries
the typedef -- td 691 `UTF7Encoding.Decoder` holds exactly `bits@0x30`,
`bitCount@0x34`, `firstByte@0x38`). The predicted alias rule proved
unnecessary: the existing single-known-type phi/var rule carries the derived
type to the working temps on its own. The rule generalizes (delegate types,
`_source`/`_token`, shared-call resolution, enum members, `ref` field args;
two sampled methods shed `unsafe`). Still open: the post-loop arm-scope reads
(`flag5`/`num5`/`num6`), which need declaration hoisting across the loop
boundary (structuring risk) -- do not treat as resolved. Analysis (2026-09-19):
the loop is single-trip (unconditional trailing `break`, no `continue`), and
the snapshots are load-bearing spills (arm C reads old `num2` mid-arm, so they
cannot be eliminated). Hoist-with-state-init is sound only under single-trip
(multi-trip + a non-assigning arm, e.g. `num5` in arm B, would read stale
init instead of the leftover), and the init mapping itself needs the
header-exit-edge register state -- textual `first bare copy` cannot prove
which pre-loop register the 0-trip path reads. Reading the state temps
instead is wrong on arm-C-break (snapshot `num2+6-16` vs pre-arm `num2`).
Verdict: needs exit-path-sensitive phis, not a text hoist;
CopyFromArray dest args reprint the ids extent instead of reusing `num4`:
investigated to ground truth and accepted as residue -- native executes three
copy calls (0x1807048f7/922/94c, mi 25626); the two extra ids-copy texts are
phantoms (one execution re-rendered) over idempotent same-byte rewrites, so
output values/order are faithful. Reusing `num4` would delete executions,
which needs execution-identity proof the pipeline does not have: _bind folds
per OBJECT, never per text, precisely so real duplicate calls are never
merged (fix 58b SaveManager rule). Two honest attempts reverted: counting
movsxd copies as uses bound earlier but collapsed the `num4`/`num5` temp
boundary the spec pins; rewriting live superstrings at bind time did the same
with added epoch hazards. Needs value provenance, not a window tweak.
`&this.field`-in-rbp and genuine `T* + N` element arithmetic keep today's
spelling.

Gate for the three unnumbered follow-ups above (float shortening, cmov
merge-type, exact-type stamp; pushed `a2887e9`): `work/followups_out` built
strict, 11,181 files / 114,458 bodies / 0 failed lifts / 0 structured fallbacks
/ 0 type-emission failures; brace audit 0 unbalanced; tree-sitter parse 0 bad
files / 0 ERROR / 0 MISSING; full-corpus sweep 116,178 methods / 0 crashes;
2,759 files differ from `work/rpc_payload_out` (none added/removed), all
sampled diffs rename/type/field-only. Follow-up: float tie-break prefers fixed
point on length ties (`10000.0f`, not `1e+04f`; 14 addresses moved, 0 crashes)
and `tests/goldens_review84.json` was regenerated with `tools/make_goldens.py`
against the refreshed sweep/parse reports: 6/64 snapshots changed (GetChars,
ReadSpan, Update, OnNextUpdate, ConvertTo, Execute), each reviewed
individually, all structurally identical; full suite 795 passed. Promoted
2026-09-19: `final_out/` holds `work/promote_out` (11,274 files, aggregate
`db468523…050c36105`, 0 mismatches); see `docs/archive/reviews-log.md` 0bg
and `validation_reports/followups_promotion_verification.json`.

## Cleanup 2026-09-19 (after the 3bf35b3 push; `bckups/` deleted later the same day)

Deleted per user call: all untracked build/compile/sweep/tests logs under
`validation_reports/` (reviews 114–123, accessors, method bodies, rpc_payload,
partial_unsafe — the committed parse/sweep/promotion/delta/regeneration JSONs
and tail-args blobs stay, 472 tracked files), all gitignored sweep/compare
blobs (`*.methods.jsonl.gz`, `*_vs*.json`, `*comparison.json`,
`output_audit.json` — regenerable via rebuild/sweep), the superseded
candidate trees `work/accessors_out/` + `work/method_bodies_out/`, and finally
the whole `bckups/` dir (9 promoted-tree copies fix99–fix122 + review97e,
1.24 GB — GitHub is now the history authority; no tracked file was touched).
Work-tree pass the same day: all `work/review98_out`–`work/review123_out`
(26 gated trees, ~3.6 GB — `review123_out` was byte-identical to `final_out/`,
`review114_out` was an unfinished partial rebuild), the unreferenced
`work/method_bodies_alias_regenerated/` intermediate (already copied back),
and `work/accessors_preview/` probe artifacts. Every deleted tree rebuilds
from git history in ~7–9 min; per-fix paragraphs below keep their `built tree`
citations as the gate record.
Kept: `final_out/` (promoted fix-123 baseline), `work/rpc_payload_out/`
(matches pushed source), and the older `work/review*_out` + `work/partial_*_out`
trees. Historical paragraphs below that cite a removed log/blob/tree keep
their original lists as the gate record — the file itself is gone.

## Current work: post-promotion residue (fix 123 promoted, see below)

`final_out/` holds the follow-up tree (probe 2,463 errors / 726 files,
`validation_reports/probe_final_out.json`). CS0053 is 0 there and 0 on the
retained `work/rpc_payload_out` tree (`probe_rpc_payload_out.json`: 10,305 /
1,516, matching the recorded baseline exactly) -- the 222 fix-123-era sites
cleared before this session (likely the accessor-recovery unit), so the
accessibility-honesty lane needs no policy decision. Live lanes: CS0737 done (880 -> 0: private+final+virtual methods with plain
names qualify via the unique directly-listed interface method with the same
name and rendered signature -- async `MoveNext`/`SetStateMachine`, iterator
`MoveNext`; trigger census matched the error count exactly, probe delta is
the sole change, `work/iface_out` + `validation_reports/probe_iface_out.json`);
CS0052 done (308 -> 0: private nested `__StaticArrayInitTypeSize=N` / Mono
`$ArrayType=N` blob structs, always empty, render `internal` -- over-visible
never errors -- with a CS0262 knock-on (28 -> 16: 12 sizes exist as
split-visibility duplicate typedefs, `0x113` vs `0x115`, unified on the
metadata majority; `work/blob_out` + `validation_reports/probe_blob_out.json`);
CS0111 384
(combined-partial duplicate constructors, known do-not-touch: deleting them
would damage the individual assemblies); CS0052 308
(`__StaticArrayInitTypeSize_N` field accessibility); the masked
body-pointer-local layer (needs expression typing first); project wiring.
The complete game is not yet compilable.

## Previous work — fix 123 (collision-aware using/strip; gated + promoted 2026-09-17)

CS0104 triage (140 sites) showed shortening rebinds references two ways:
duplicate short names across imported namespaces (`Hashtable`,
`Object`, `Random`) and heads matching a visible namespace final segment
(`HID.HIDDeviceDescriptor`). `collision_heads` (new in `il2cpp/csharp.py`,
mirroring `rep()`) flags exactly the heads shortening could produce, proven
per file against the metadata short-name table (global-ns rows excluded —
usings win over globals empirically); `strip_namespaces` keeps those full
chains. Generic arguments render full paths at every depth (the `ErrorEventArgs`
bare-arg gap), and explicit *method* qualifiers split before sanitizing
(`IDictionary<TKey,TValue>` kept its commas). Gates: **759 tests** (6 in
`tests/test_review123_collisions.py` — 5 unit + 1 game-backed); strict
rebuild 11,181 files / 113,938 bodies / 0 failures (`work/review123_out`);
parser 0 bad files; direct sweep 116,178 methods / 0 crashes / 0 structural
changes vs fix 122; probe **10,794 → 10,602 (−192)**: CS0104 140→3,
CS0246 43→0, CS0305/CS0308/CS0426/CS0538 →0, CS0535 −13, against CS0053 +21
(accessibility unmasking, characterized above). One golden diff reviewed
(fulldepth args only) before regen; one game-test expectation corrected to
the faithful `System.EventHandler_1<...>` spelling. Reports:
`validation_reports/review123_*`. Promoted 2026-09-17: `final_out/` now
holds `work/review123_out` (11,274 files, aggregate `45711645…3791d3c6`, 0
mismatches; the `bckups/final_out_fix122` copy was removed 2026-09-19, see the
cleanup note above).
Post-promotion parse recheck 0 bad files.

Comparison temps (`obj227 < 6`) are CLOSED with no code change: a full
`.pdata`-extent native scan of `InventoryManager.Update` finds no compare,
test, or arithmetic instruction with immediate 6 anywhere — the literal is
decompiler-synthesized (jump-table/switch-bound recovery), so no width/sign
evidence exists to thread and any numeric cast would invent semantics.
Where a real `cmp reg, nonzero-imm` executes, the existing chain (CMP hint
→ rename classifier → `_decl_type_of` → fix-104 cast) already emits exactly
the desired shape — same VA, other branch: `int num11 =
(int)sub_180001da0(...); if (num11 < 6)`. The remaining work is provenance
for synthesized switch-bound literals, not temp typing.

## Previous work — fix 122 (receiver-proven stub temps; gated + promoted 2026-09-17)

The user's specimen (`object obj228 = sub_...; obj228.SetTrigger("Reload")`)
opened the shared-body/`objN` lane. Triage: two of its three addresses are
unregistered natives (zero candidates — call identity unknowable, only
use-types recoverable); the third is StartCoroutine/StartCoroutine_Auto
(already cast-covered). New rule (`_stub_receiver_decls`, feeding the
existing fix-104 cast machinery): an `object X = sub_(...)` declaration
whose only other mention is one bare `X.Method(literals)` call, resolving
by literal-applicability to exactly one instance non-generic metadata
method (exact arity, or provable defaults; params-array expansion honestly
unmodeled so larger arities without full defaults decline), is retyped to
the owner with a caller-proven cast. Writes, address-takes, ref/out/in,
redeclarations, non-literal args, and accessor-shaped names all decline.
Census: 116 unique-owner sites (game types: StoreManager 30, JSONAccess 7…),
380 non-literal, 195 ambiguous. Ground truth: `UnityEngine.Animator
animator2 = (UnityEngine.Animator)sub_180001d80(...);
animator2.SetTrigger("Reload");` — and the semantic renamer adopts the
proven type for temp names. Gates: **752 tests** (10 new in
`tests/test_review122_receiver_casts.py`); strict rebuild 11,181 files /
113,938 bodies / 0 failures (`work/review122_out`); parser 0 bad files;
direct sweep 116,178 methods / 0 crashes / 0 structural changes vs fix 121
(49 changed bodies, every diff a retype+cast+rename audited file by file);
probe **10,794 → 10,794**: the fix is probe-invisible today because
error-typed/unbound upstream values mask downstream binding (verified: the
fixed shape errors standalone, the region is silent in-tree), so it removes
future CS1061s rather than present ones — zero cost either way. Reports:
`validation_reports/review122_*`; 64 goldens untouched. Promoted 2026-09-17:
`final_out/` now holds `work/review122_out` (11,274 files, aggregate
`3a513e9a…13b49de`, 0 mismatches; the fix-121 tree is kept at
`bckups/final_out_fix121`). Post-promotion parse recheck 0 bad files.

## Previous work — fixes 120 and 121 (nested owner paths + mirror completion; gated + promoted 2026-09-17)

CS0246 triage crowned the nested-qualification gap: the typedef `declaring`
field is -1 top-level and out of range for all 5,719 nested rows, so
`typedef_full`'s owner walk never fired and nested references rendered bare
(`CallbackContext` for `InputAction.CallbackContext`). Owners now resolve
through the forward `nested_types` table inverted once per instance
(`_nested_owner`; top-level `declaring == -1` consumers untouched), with the
outermost namespace on the path. Generic owners distribute instantiation
args outer-first (`List_1<T>.Enumerator`, `Dictionary_2<TKey,
TValue>.KeyCollection`). Nested containers holding mirrored owner params
plus own trailing ones (290 mirror vs 184 independent by census) declare
only the own suffix (`DispatchDelegate(T)` exactly as Valve wrote it;
`ConstraintComparer<K>`), because same-named independence is inexpressible
in C# — proven by names+counts, declined otherwise. Along the way: blob
`__StaticArrayInitTypeSize=`/`$ArrayType=` rewrites match the terminal
segment (48 parse-failing files), reference spellings sanitize per segment
(the guid-braced `PrivateImplementationDetails` owner), and strip keeps
self-shadowed full chains (`HID.HID...`). Gates: **742 tests** (13 in
`tests/test_review120_nested_paths.py` + qualifier/sanitize cases);
strict rebuild 11,181 files / 113,938 bodies / 0 failures
(`work/review121_out`); parser 0 bad files; direct sweep 116,178 methods /
0 crashes / 0 structural changes vs fix 119 (8,081 spelling-only bodies);
probe **13,352 → 10,794 (−2,558)**: CS0246 2,423→43, CS0540 38→0, CS0308
43→4, CS0305 13→4, plus drops across CS0111/CS0146/CS0523/CS0534/CS0535 and
CS0118→0, against CS0053 +6 (accessibility unmasking, characterized), one
documented CS0426 collision cost and CS0234-class silence above. The 6
golden diffs and 2 assertion updates were each reviewed (owner-path
spellings only) before regen. Reports: `validation_reports/review121_*`.
Promoted 2026-09-17: `final_out/` now holds `work/review121_out` (11,274
files, aggregate `b84d8e05…c94253`, 0 mismatches; the fix-119 tree is kept
at `bckups/final_out_fix119`). Post-promotion parse recheck 0 bad files.
(Fix 120 was gated through sweep/tests but held unpromoted when its probe
showed the CS0305 mirror spike; fix 121 completes it — same two-stage
rhythm as 117/118.)

## Previous work — fix 119 (using-feeding qualified spellings; gated + promoted 2026-09-17)

CS0246 triage crowned the using-generation gap: `IntPtr` rendered bare
because `PRIM` carried no namespace (1,076 sites), and `[Serializable]` /
`[SerializeField]` never named one (338/32 sites each). All three now render
qualified pre-strip (`System.IntPtr` / `System.UIntPtr` /
`System.TypedReference`; `[System.Serializable]`; `[UnityEngine.
SerializeField]`), so the tracker imports the namespace and the boundary
strips back to short form — the partial-tree diff is exactly added `using`
lines plus blank separators. Mechanism audit: `type_name` is also the
body-spelling path, so 2,148 lifted bodies changed; tree-wide audit shows
11,167 files identifier-identical, the rest renames plus 14 reflow files of
the known temp-materialization class (traced equivalent); the `_bind` /
`_kill_stale` text-identity gates that select those cascades are
spelling-agnostic within a run. Gates: **727 tests** (5 new in
`tests/test_review119_usings.py`); strict rebuild 11,181 files / 113,938
bodies / 0 failures (`work/review119_out`); parser 0 bad files; direct
sweep 116,178 methods / 0 crashes / 0 structural changes vs fix 118; probe
**15,183 → 13,352 (−1,831)**: CS0246 −1,823, CS0535 −9, no other moves
except the single documented CS0104 ambiguity cost above. Reports:
`validation_reports/review119_*`; 64 goldens untouched. Promoted 2026-09-17:
`final_out/` now holds `work/review119_out` (11,274 files, aggregate
`5855ed65…baf5d`, 0 mismatches; the fix-118 tree is kept at
`bckups/final_out_fix118`). Post-promotion parse recheck 0 bad files.

## Previous work — fix 118 (explicit-qualifier completion; gated + promoted 2026-09-17)

Fix 117's new `_N` references unmasked two explicit-member gaps. First, the
qualifier proof trusted arity-less name strings while the true interface is
the declaring type's tuple: members spelled `IObserver_1<InputRemoting.
Message>` against base `IObserver_1<Message>` (`_iface_qualifier`, unique
tuple match or decline). Second, `sanitize()` ate generic structure inside
qualifiers (`KeyValuePair<TKey, TValue>` → `KeyValuePair<TKey__TValue>`,
`T[]` → `T__`): new structure-aware `sanitize_qualifier` (`il2cpp/names.py`)
sanitizes identifier segments only. Gates: **722 tests** (12 in
`tests/test_review117_arity_spellings.py` — 7 arity + 5 qualifier/sanitize);
strict rebuild 11,181 files / 113,938 bodies / 0 failures
(`work/review118_out`); parser 0 bad files; direct sweep 116,178 methods /
0 crashes / 0 structural changes vs fix 117; probe **15,677 → 15,183
(−307), zero increases**: CS9334 30→0, CS9333→0, CS0540 124→38, plus
knock-on drops. The 38 residual CS0540 are the nested-shadowing family
above, characterized for the next fix. Reports:
`validation_reports/review118_*`; 64 goldens untouched (0 changed bodies).
Promoted 2026-09-17: `final_out/` now holds `work/review118_out` (11,274
files, aggregate `bede44dc…74d418`, 0 mismatches; the fix-117 tree is kept
at `bckups/final_out_fix117`). Post-promotion parse recheck 0 bad files.

## Previous work — fix 117 (generic `_N` reference spellings; gated + promoted 2026-09-17)

CS0115 triage (266 sites) root-caused a declaration/reference convention
split, not wrong override keywords: type declarations spell
`EqualityComparer_1<T>` (fix-113 arity convention) while every reference
spelled `EqualityComparer<byte>`, so derived overrides bound against the
*reference-assembly* base (which has no `IndexOf`) instead of the local one.
`csharp_type_name` (`il2cpp/common.py`) now renders `` `N `` as `_N`, so
references spell the declared identifier; explicit interface qualifiers
(which come from arity-less metadata name strings) recover the suffix
through a (namespace, path, top-level arg-count) typedef proof
(`_arity_qualifier` in `il2cpp/emitter.py`, wired into `method_sig` and
`emit_property`; declines on unknown/ambiguous shapes). Audit surface: 2
`split('<')[0]` uses (both against non-generic names), one `_BACKTICK_RX`
use-site, 0 methods with backticks, 779 generic typedefs.

Provenance (full old-vs-new tree audit, 3,477 changed files): 45,394
arity-insertion tokens; renames from the arity-embedding local renamer
(`list1`→`list11`, `dictionary1`→`dictionary21`; decl↔use consistent, zero
pre-existing collision targets); 18 reflow files (±1–6 lines) of one class —
a `static` generic read materialized into a temp (`object objN =
Span_1<byte>.Slice`) plus renumber cascade, traced semantically identical in
`Convert.TryFromBase64Chars` by old-vs-new direct re-lift; one loop flip
(`while (c)` → header-replay `while (true)`) via the documented `h.stmts`
rule, sound by construction. The 6 golden diffs were each reviewed
(spelling + consistent renames, decl-uniqueness unchanged) before regen;
one stale `Optional<string>` assertion updated to `Optional_1<string>`.

Gates: **717 tests** (7 new in
`tests/test_review117_arity_spellings.py`); strict rebuild 11,181 files /
113,938 bodies / 0 failures (`work/review117_out`); parser 0 bad files;
direct sweep 116,178 methods / 0 crashes / 0 structural changes vs fix 116
(7,275 changed bodies, into_block identical); probe **24,078 → 15,677
(−8,401)**: CS0115 266→0, CS0246 10,337→4,358, CS0535 1,171→191, CS0308
646→49, CS0737 −276, CS0738 259→50, CS0452/CS0453/CS0509/CS8345 →0, with
unmasked CS0540 +4 / CS9334 +3 and single-digit noise elsewhere; CS0501
steady. The mid-gate probe without the qualifier fix read 16,966 (CS0540
+512/CS9334 +148), which scoped exactly the qualifier completion above.
Reports: `validation_reports/review117_*`; goldens regenerated (6 reviewed
bodies, 58 untouched, fingerprints refreshed). Promoted 2026-09-17:
`final_out/` now holds `work/review117_out` (11,274 files, aggregate
`1bd83c61…a46467`, 0 mismatches; the fix-116 tree is kept at
`bckups/final_out_fix116`). Post-promotion parse recheck 0 bad files.

## Previous work — fix 116 (unsafe fields/properties, CS0214 zero; gated + promoted 2026-09-17)

The 517 CS0214 residue classified declaration-only: 465 pointer fields, 52
pointer properties, 0 body lines (the 2 apparent locals are
`[SerializeField]`-prefixed fields). `emit_type` field mods and both
`emit_property` paths now append `unsafe` on `'*'` spellings
(`il2cpp/emitter.py`); all shapes Roslyn-probed, including interface and
explicit-impl properties. Gates: **710 tests** (7 new in
`tests/test_review116_unsafe_members.py`); strict rebuild 11,181 files /
113,938 bodies / 0 failures (`work/review116_out`); parser 0 bad files;
direct sweep 116,178 methods / 0 crashes / 0 structural changes vs fix 115;
probe **24,595 → 24,078, the only delta CS0214 517 → 0**. Body-level
pointer locals (e.g. `NetworkBehaviour` 596) stay silent only through error
cascading — a standalone repro proves the declaration CS0214 masks them, so
a future typing fix will unmask a method-level-`unsafe` lane; nothing to do
until then. Reports: `validation_reports/review116_*`; 64 goldens untouched.
Promoted 2026-09-17: `final_out/` now holds `work/review116_out` (11,274
files, aggregate `8e93363d…9ff462b9`, 0 mismatches; the fix-115 tree is kept
at `bckups/final_out_fix115`). Post-promotion parse recheck 0 bad files.
(Note: the fix-116 promotion run briefly overwrote
`review115_promotion_verification.json` with a stale comparison; restored
from the verified fix-115 values, noted in the file.)

## Previous work — fixes 114 and 115 (dispatch, ctors, unsafe; gated + promoted 2026-09-17)

Corrected CLI MethodAttributes: Virtual=0x40, Final=0x20, NewSlot=0x100,
Abstract=0x400. The old emitter confused these with each other. Methods now
preserve virtual slots, overrides, sealed overrides and abstract overrides.
Final new-slot interface implementations remain ordinary methods; explicit
interface implementations omit access/virtual modifiers. Abstract methods
consistently have no body, even when metadata carries an address. Static
abstract interface members retain their modifiers.

Generic constructors now match their emitted type identifier: Box_1<T> has
Box_1() and static Box_1(), rather than Box(). The metadata census finds
21,410 changed method signatures and 858 changed constructor signatures.
Evidence: validation_reports/review114_declaration_census.json.

Validation: **698 tests pass**, including all 118 fixture tests and a real
Roslyn compilation of generated dispatch/constructor declarations. The Review 83
shared-boolean assertion was stale since fix 110; the prior candidate already
emits proven string equality, and the test now checks those exact conditions.
The 64 frozen method bodies remain unchanged. The strict rebuild was stopped at
the requested wrap-up point after **97,291 bodies with 0 failures**; its partial
candidate is `work/review114_out` and its log was
`validation_reports/review114_build.log` (removed in the 2026-09-19 cleanup). That rebuild never finished, so
fix 114 alone claims no whole-tree result — the Fix 115 gate below rebuilds
the same source completely and supersedes it.

New tools/compile_corpus.py invokes installed Roslyn directly, records a source
inventory digest and diagnostic counts, and saves compressed complete logs.
It merges shared stubs only in temporary storage. This is a single diagnostic
assembly, not verification of project wiring or behavior, and includes some
cross-assembly collisions. Its fix-113 baseline is **34,262 errors**, counted
once per diagnostic. Compare only with the same probe; older build-log totals
can repeat diagnostics and use different compiler references. Its largest
measured groups are missing types/usings (CS0246: 10,337), concrete declarations
without bodies (CS0501: 7,558), pointer declarations outside unsafe contexts
(CS0214: 3,627), and unimplemented abstract/interface members (CS0534: 3,527).

Follow-up (partial, ungated): pointer-signature methods and constructors now
carry `unsafe` (`method_sig`/`ctor_sig` in `il2cpp/emitter.py`, same `'*'`
spelling rule `emit_delegate` already used). Metadata census: 2,564
pointer-signature methods and 82 constructors; ground truth `NodeSwitch`
`@Invoker`s render `protected static unsafe void ...(..., SimulationMessage*
message)`. Partial evidence only: 27 targeted tests (5 new) plus an 87-test
portable subset pass, single-method re-lift of mi 23560 is unchanged, and a
single-file Roslyn probe compiles the new shapes including explicit-interface
`unsafe void IFoo.Bar(byte* p)`. Superseded the same day by the Fix 115 full
gate below (strict rebuild, sweep, probe); pointer fields/properties became
fix 116 above.

CS0501 triage (metadata-only, partial): 9,397 concrete address-less methods —
204 runtime-impl, all delegate members already suppressed through
`emit_delegate`; 8,645 plain managed (iflags 0), including whole
metadata-only types such as `DictionaryLookupTable`2` (all 11 methods
address-less); 520 aggressive-inlining, 28 no-inlining. No blanket `throw`,
`abstract`, `extern`, or `partial` rule is sound without per-method ground
truth (stripped/uninstantiated generics versus real misses), so no code
changed.

Unsafe follow-up, Assembly-CSharp gate (partial, not a full rebuild):
`--only Assembly-CSharp` strict rebuild into `work/partial_unsafe_acs_out`
(490 types, 6,610 bodies, 0 failed, ~67s; `PYTHONHASHSEED=0` — the one
non-unsafe diff in the unseeded run was hash-order noise, byte-identical on
repro). Old-vs-new diff over `work/review114_out/Assembly-CSharp`: 87 files
changed, 518 added lines, every one an `unsafe` insertion, 0 files with any
other change. Single-assembly Roslyn probe
(`validation_reports/partial_unsafe_acs_compile.json`, removed in the
2026-09-19 cleanup): ACS-scope CS0214
falls 518 → 0 (exactly the 518 insertions) and CS0106 199 → 0 (fix-114
explicit-impl rule); CS0501 holds 35 → 35, untouched by design. The 9,196
probe total is dominated by CS0246 scope artifact (8,937: cross-assembly
references are absent from a one-assembly tree), not a regression.

CS0501 tree-wide census (read-only over `work/review113_out`, 11,181 files):
8,926 bare declaration lines = 755 legal `abstract` + ~615 legal `delegate`
+ 3,647 concrete open-generic definitions with no compiled instantiation
(ACS scope: all 35 probe sites are this shape — `Shuffle<T>`,
`ConvertNestedList<T>`, `GetModule<T>`, display-class ctors) + ~3,900
closed concrete without bodies (metadata-only/editor-stripped types such as
`SerializedDictionary` ctors). Concrete-bare minus delegates closes against
the 7,558 diagnostics within noise. No body exists in the binary for any of
these, so no rendering change is sound; the bare signature stays as the
honest marker.

## Fix 115 gate and promotion (2026-09-17, full gate lifted per user call)

Fix 115 is the unsafe-signature follow-up above, built on the fix-114
source. Gates: **703 tests** (698 + 5 new unsafe-signature cases, incl. 118
game fixture tests and the 64 goldens, all live); strict rebuild 11,181
files / 113,938 bodies / 0 failures or fallbacks (`work/review115_out`);
parser 0 bad files; direct sweep 116,178 methods / 0 crashes / 0 structural
changes vs fix 113 (`validation_reports/review115_vs113.json`: 0 changed
bodies — the combined fix-114 + fix-115 delta is declaration-only);
 Roslyn probe **34,262 → 24,595 errors** (−9,667), fully attributed —
CS0106 2,402 → 0, CS0533 226 → 0, CS0534 3,527 → 3, CS1520 797 → 0,
CS0214 3,627 → 517 (residue: pointer fields and body locals only, sampled),
unmasking CS0115 266 / CS0249 121 / CS0507 4; CS0246/CS0501/CS0535/CS0737
unchanged. Reports: `validation_reports/review115_{build.log,sweep.json,
vs113.json,parse.json,compile.json,tests.log}` (build/compile/tests logs and
the vs-compare blob removed in the 2026-09-19 cleanup; sweep/parse JSONs stay
tracked); built tree
`work/review115_out`. The 64 goldens are untouched (0 changed bodies, no
regen needed). Promoted 2026-09-17: `final_out/` now holds
`work/review115_out` (11,274 files — 74 more than the fix-99 tree, exactly
the fix-104 stub files minus the 3 fix-113 orphans; candidate and promoted
aggregate sha256 both
`2379110f106b51f6958d0eb0a3f0c7bdc1a6b0de2a0490ba5612d0e03e9a07a4`, 0
mismatches; the fix-99 tree is kept at `bckups/final_out_fix99`).
Promotion record: `validation_reports/review115_promotion_verification.json`;
post-promotion parse recheck
`validation_reports/review115_recheck_parse_final.json` (11,274 files, 0
bad).

## Previous work — fix 113 (legal type declarations, gated 2026-09-18)

The Roslyn probe's semantic layer is dominated by declaration
shapes, all emitted wrong the same way. `type_decl_line` read
`0x20 & ~0x80` for interfaces — but ECMA mandates abstract+interface
together, so nearly all 636 interfaces rendered as classes (fixing
CS1721/CS0527/CS1722/CS0737 at the root: all four codes go to zero).
Abstract+sealed renders `static partial class` (census: all 1,015
have no instance fields/methods/properties/events, no bases or
interfaces — zero tradeoff). User delegates (616, via MulticastDelegate
parentage) render `delegate R Name(params);` through Invoke (generic
arity mirrors the `List_1<T>` class convention so references match;
.ctor/Invoke/BeginInvoke/EndInvoke suppressed as compiler-provided;
falls back to class rendering if Invoke/fields/props/events/nested
are ever missing/present). Interface members lose access/instance
modifiers (DIM bodies kept under a new `<LangVersion>latest</LangVersion>`
in the csproj template); properties/events propagate accessor
staticness (all-static on the 431/19 absseal ones; mixed would fall
back). Gates: **682 tests (564 portable incl. 6 new in
`tests/test_review113_type_decls.py` + 118 game); direct sweep 116,178 methods / 0 crashes / 0 structural changes vs
fix 112 (0 bodies changed — emitter-only); strict build 11,181 files
/ 113,938 bodies / 0 failures or fallbacks (`work/review113_out`);
parser 0 bad files**. Reports: `validation_reports/review113_sweep.json`,
`review113_vs112.json` (0 changed, 0 structural),
`review113_parse.json`; built tree `work/review113_out`. The 64
goldens are untouched (0 overlapping MIs; fingerprints refreshed).
NOT promoted — `final_out/` still holds the fix-99 tree pending a
human promotion call.

- [x] Fix 113: 2,001 files changed — exactly 1,015 `static`,
  636 `interface`, 615 `delegate` headers (census-exact), plus
  modifier-stripped members; 3 orphaned `__SharedBodyStubs.cs`
  dropped (delegate-suppressed bodies took the only refs).
- [x] Recompile probe: **87,224 → 68,528 instances, 5,461 → 4,097
  files; CS1721/CS0527/CS0418/CS0644/CS1722/CS0708 all go to
  exactly zero** (CS0708 needed the property/event staticness
  follow-through: 900 → 0). ZipEntry.cs (12 delegate-shape errors
  after fix 112) is fully clean.
- [x] Residue is the next program: missing types (CS0246 20.7k:
  usings, nested qualification, open generics, absent types),
  bodiless methods (CS0501 15.1k), unsafe modifiers (CS0214 7.3k),
  unimplemented members (CS0534 7.1k), overrides (CS0533/CS0535),
  ctors (CS1520), overload collisions, ref/out ABI — then the
  unmasked body layer (gotos, definite assignment).

## Previous work — fix 112 (fresh-array bracket repair, gated 2026-09-18)

`new T[N][i]` parses as an invalid rank specifier and
`new T[N](idx)[0]` (single argument, ldelema shape) as an invalid
call (the last 2 parse-failing files). `_fresh_array_brackets`
(new dec text pass) parenthesizes the creation — `(new T[N])[i]`,
`(new T[N])[idx]` — meaning-preserving everywhere (allocation,
size, and index survive verbatim; verified parsing with Roslyn).
Multi-arg calls, bare calls without a deref, and unbalanced spans
decline. Gates: **676 tests (558 portable incl. 8 new in
`tests/test_review112_array_brackets.py` + 118 game); direct sweep
116,178 methods / 0 crashes / 0 structural changes vs fix 111 (181
bodies changed, all line-neutral); strict build 11,184 files /
115,658 bodies / 0 failures or fallbacks (`work/review112_out`);
parser 0 bad files**. Reports: `validation_reports/review112_sweep.json`,
`review112_vs111.json` (181 changed, 0 structural),
`review112_parse.json`; built tree `work/review112_out`. The 64
goldens are untouched (0 overlapping MIs; fingerprints refreshed
with fix 113's). Provenance: 709/709 paired paren insertions, zero
other diff lines. SqlDecimal.cs fully clean; ZipEntry.cs left 12
delegate-shape errors for fix 113 (which cleared them).

## Previous work — fix 111 (C# keyword escaping, gated 2026-09-18)

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
