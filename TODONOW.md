# Decompiler recovery follow-up — current handoff

## Current state

The work remains source-level; `final_out/` was not hand-edited or promoted.
The private fixture is available at:

- metadata: `testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat`
- binary: `testgame/GameAssembly.dll`

Fresh targeted lifts are in `work/recovery_continue.json` and the intermediate
`work/recovery_step*.json` files.

## Proven fixes now in the working tree

- `MicAudioCanvas.Start` assigns `null` on the null connection path and a
  `Recorder` on the non-null path; duplicate raw stores are gone.
- `MicAudioCanvas.Update` reads `CurrentAvgAmp`, preserves `InputMode`, compares
  against `InputMode.OpenMic`, and keeps the branch-produced PTT Boolean in
  scope.
- `MicAudioCanvas.OnVoiceConnectionReady` emits typed assignments without the
  duplicate unsafe write.
- `AnimationEventTrigger.TeleportPlayer` passes all `Vector3` and `Quaternion`
  components.
- `CollisionEventHandler.OnDrawGizmos` recovers native-list `.Count`, typed
  `Oni.Contact`, red/green/cyan colors, complete `pointB`, and complete
  `normal * distance` vectors. The missing vector components were caused by
  ignored `UNPCKLPS`; aggregate phi provenance now also preserves conditional
  16-byte colors.
- `ConsoleUINavigation.OnEnable` retains `RemoveAll`, uses `.Count`, recovers
  the `RemoveOnConsole` predicate body, and reconstructs explicit Navigation
  with preserved endpoint links and previous/next neighbors.
- `GlobalUINavigation.DisableNavigation` now emits the lock-count increment,
  restoring nested disable/enable semantics.
- Power-of-two sizing retains the conditional expression as one operand, so
  subtraction and shifts no longer bind into the wrong ternary arm.
- Struct calls recover complete by-value arguments instead of scalar members
  or addresses of local temporaries in the covered paths.

Portable regression coverage was added in
`tests/test_recovery_completion.py` for conditional precedence, metadata
storage exclusion, `UNPCKLPS` lanes, Boolean XOR, and Boolean returns.

## Remaining blockers before promotion

1. `GlobalUINavigation.RestoreSelectableNavigation` is still not recovered.
   Its `Dictionary<Selectable, Navigation>.Enumerator` return is an open
   nested `GENERICINST`. `candidate_return_type()` substitutes only a direct
   `VAR`/`MVAR`, so the hidden sret buffer, `MoveNext`, `Current`, key/value,
   navigation assignment, and disposal remain anonymous. Fix this generically
   by recursively substituting class arguments inside a generic-instance
   return; do not special-case this class or RVA.
2. Delegate construction is substantially recovered (`new Predicate<Selectable>(
   <>c.<>9.<OnEnable>b__1_0)`), but the cached-field store currently renders
   as an invalid `tNNNN__1_0 = predicate;`. `_mem_lvalue` proves the correct
   target is `ConsoleUINavigation.<>c.<>9__1_0`; compiler-generated static
   field identifiers need the same storage-name sanitation as declarations.
3. `DisableAllActiveSelectables` still types the saved `Navigation` value as
   `object` at `Dictionary.Add`. The full struct is present in native state;
   propagate the closed value parameter type into that argument and remove
   the obsolete scalar `obj` temporaries.
4. Some power-of-two expressions still re-expand their original conditional
   source instead of using the preceding local. Their precedence is now
   correct, but use binding should preserve the compact `num |= num >> N`
   form.
5. Fresh contact output contains a dead packed-color temporary before setting
   cyan. It is defined and harmless, but should be removed by ordinary dead
   value cleanup.
6. Do not promote generated output until the three semantic blockers above
   are fixed and the affected files pass the C# compiler probe.

## Validation status

Last clean focused run before this handoff:

```powershell
python -m pytest -q tests/test_recovery_completion.py tests/test_recovery_followup.py --disable-warnings
# 54 passed
```

The portable suite was previously clean at 718 passed before the latest small
delegate/aggregate changes; rerun it after this handoff. The licensed full
suite has the known unreviewed golden drift documented in `docs/todo.md`; a
run with `--maxfail=10` stopped at 10 snapshot differences, rather than a new
portable failure. Goldens must be reviewed against native instructions, not
blindly updated.

## Resume commands

```powershell
$env:PYTHONHASHSEED = '0'
$env:IL2CSHARP_METADATA = (Resolve-Path 'testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat').Path
$env:IL2CSHARP_BINARY = (Resolve-Path 'testgame/GameAssembly.dll').Path

python -m pytest -q -m "not game" --disable-warnings
python tools/inspect_methods.py `
  --metadata $env:IL2CSHARP_METADATA `
  --binary $env:IL2CSHARP_BINARY `
  --mi 23757 23761 23762 23767 23917 24224 24655 24659 26311 26312 26313 `
  --save work/recovery_resume.json
```

After the blockers are fixed, generate the five affected types into a separate
candidate directory, run `tools/validate_corpus.py` and
`tools/compile_corpus.py`, inspect the diff, then ## Addendum 2026-09-20 (round 3e session)

Landed in the working tree (all `il2cpp/` edits binary-patched,
CRLF/no-BOM asserted; `tests/test_recovery_completion.py` LF, 12 tests):

- Blocker 2 DONE: `t1012__1_0` was `_bind`'s blind `str.replace`
  cutting `...<>c.<>9` inside `...<>c.<>9__1_0` (`_field_expr` was
  innocent -- probe trace). `_bind_replace` (`il2cpp/expr.py`, all 10
  `_bind` sites) rewrites whole-token occurrences only. 24655 now
  emits `ConsoleUINavigation.<>c.<>9__1_0 = predicate13;`. The handoff
  suspected `_mem_lvalue`/sanitation; evidence says the store path
  was already right.
- Blocker 3 DONE: 23761 now emits `Navigation navigation1` at
  `dictionary22.Add(...)`, `navigation2.m_Mode = Mode.None` (dword-0
  at the home base, proved against the field chain + `_fimm`), and
  `Navigation navigation1 = navigation2`. Machinery: byval-struct
  `&slot` call hints (TRUST-gated, closed-key, setdefault),
  `_struct_home_ty` recording on whole-field stores, `_home_field_store`
  for base constants (declines to scalar when unprovable). Residual
  home-construction lines stay (loop-DCE conservatism) but compile.
- Blocker 5 DONE: 23917's dead `(float2)(0.0f, 1.0f)` drops in
  ordinary DCE (`_PURE_LOAD_RX` admits paren-free `(float2)(...)`;
  the only packed spelling emitted, over literals). Cyan kept.
- Bonus improvement: 45016 `TimeOfDay` temp is now `System.TimeSpan`
  (was `object`, uncompilable member access) via home recording.
- Deferred with designs: blocker 1 (no closed Enumerator/KVP rows by
  scan; return-subst insufficient -- field loads + structural loss;
  needs synthetic nested-type table et al.; double-Dispose is
  faithful), blocker 4 (needs subexpression-CSE; output correct).
- Gates: portable 730/730; full suite 822 passed / 34 failed. The 12
  beyond the triaged 22 are INHERITED drift, each attributed:
  review80-direction + review83-unobserved (prior P6 files);
  mi-67525 (prior UNPCKLPS handler -- honest `?/bits` vs golden's
  stale-value luck, proven by branch-skip restore);
  mi-21027/47817/112379 + mi-26747-strip-line + closure +
  mi-45016 `string.Empty` line (prior owner-strip in
  `lifter/values.py` -- `X.F` compiles, `typeof(X).F` does not);
  mi-39789 + packed + datetime + mi-26747-guard + mi-45016
  type1/guards/renumber (prior klass/sfblob `_note_use` gate --
  proven by revert-restore, twice for packed/datetime).
  My tree contributes ZERO new failures; 45016 additionally carries
  the TimeSpan improvement hunk (regen-list, not a revert).
  Per-item configs, diffs, and native evidence recorded in the
  session transcript; probe/patch scripts live outside the repo
  (`%TEMP%/opencode`, never committed).
- Leftovers: 34 golden/review items await gated regen (22 triaged +
  12 drift incl. 1 improvement); promotion still gated on a user call
  plus the compiler probe over the five affected types.

(End of file - session addendum 2026-09-20)

## Addendum 2026-09-20, turn 2 (subagents + CSE + candidate gate)

- Three analysis subagents (read-only, Temp scratch): S1 audited every
  GENERICINST consumer (exact touch list: table-first suffices for
  `type_name`/`td_of_ty`/`_td_of`; own branches needed for
  `_closed_type_key`, `_type_has_var`, `_generic_inst_args`,
  `_byval_struct`; SRET/`trust` stand-downs frozen) with Q1-Q5 answers;
  S2 censused the pow2 idiom (2 sites: 23761 + twin 23767) and wrote
  the complete `_subexpr_cse` rule design incl. 5 unit-test sketches;
  S3 independently re-verified all 12 drift attributions (10 VERIFIED
  as prior, 45016-TimeSpan VERIFIED as session improvement).
- Candidate-tree gate (Temp `candidate_out`, `--types` per type):
  54 bodies / 0 failed / 0 fallbacks strict; parse 0/0/0; Roslyn 83
  errors all CS0246 missing-assembly scope noise, zero on recovered
  identifiers; five-file diff strictly improving. Full-tree compile
  stays promotion-time.
- Blocker 4 LANDED per S2's design (`_subexpr_cse` in `dec/dataflow.py`,
  hooked after `_value_cse`): 23761 + 23767 fold to the compact
  `num |= num >> N` cascade; 25626's offset chain compacts as a
  designed side effect (pinning test consigned to regen). 5 unit
  tests. Portable 735 green; full suite 826/35 (+1 improvement-pin,
  +5 new tests passing; zero regressions).
- Blocker 1 NOT started beyond blueprint: S1 + Q-answers prove the
  handoff's mechanism insufficient (receiver-driven, not spec-driven;
  `type_sizes[1514]` None; field chain shows only `_dictionary`;
  homes/fields need an undesigned sidecar; table-alone ~= 2 decl
  lines for hot-path churn). Full blueprint + Q-decisions recorded
  in `docs/todo.md` round 3e; implementation is the next rock.

(End of file - turn 2, 2026-09-20)

## Addendum turn 3: blocker-1 foundation + CSE (2026-09-20)

- _subexpr_cse landed (blocker 4): both pow2 sites fold; 5 unit tests.
- Synthetic nested-type table + _subst_closed + candidate_return_type
  recursion landed with 4 game tests; full-suite failure set identical
  (830/35). Receiver-driven + field-sidecar slice stays next.
- Candidate-tree gate for the five types: strict 54/0/0, parse 0/0/0,
  Roslyn 83xCS0246 scope-noise only, diff strictly improving.

(End of file - turn 3, 2026-09-20)

## Addendum turn 4: B11 rescue + home typing (2026-09-20)

- S4: B11's loss was _abandon_at_region_close on the loop latch
  (break-out + statement deletion). Fixed in dec/emit.py: latch
  blocks with statements emit + edge-copy + fall off; empty latches
  keep the old break. 23762 keeps the guarded navigation assignment.
- S5: MethodRef slots prove the closed generic identities; designed
  _proved_struct_home (seeded at proved-generic info sites).
  23762 declares the closed Enumerator with named MoveNext/Dispose.
  s_30 buffer typing skipped (size unprovable); key/value fields need
  the sidecar (instance_field_chain(1514) has only _dictionary).
- Fixed: process-wide fake-VA allocator (class-level _tn_cache
  shared across instances caused an order-dependent suite failure).
- Gates: portable 738, full 833/35 identical sets. No commit.

(End of file - turn 4, 2026-09-20)

## Addendum turn 5: accessor-receiver key typing (2026-09-20)

- The `set_` fold never hinted its receiver, so 23762's key stayed
  `object`. `_hint_accessor_recv` types it from the non-generic
  declaring typedef (slots/bare `t`; byref homes for valuetypes).
  Key is now `Selectable selectable1`; assignment guarded and typed.
- Gates: portable 740, full 835/35 identical sets. Value chain
  (untyped piece homes) still needs the sidecar. No commit.

(End of file - turn 5, 2026-09-20)

## Addendum turn 6: copy-guard + layout steps (2026-09-20)

- `_copy_prop` declines merges when both sides declare different
  concrete types (struct home over typed temp). 23762 keeps its
  guarded typed assignment; residual over-claim line documented.
- `_sf_infl_chain` closes nested-open fields; `returns_sret` admits
  proved-size closed 0x15 (72B Enumerator folds sret + facts).
- Gates: portable 742, full 837/35 identical sets. No commit.

(End of file - turn 6, 2026-09-20)

## Addendum turn 7: crash + parse gates (2026-09-20)

- 129 fallbacks = tied-pending `sorted` crash (HEAD-latent, prior
  volume); fixed with stable key sort. 3 failed = unknown-size sret
  facts crash; guarded. 8 sweep fails = `_kill_one` dropping `_mi`;
  preserved + delegate guard.
- Parse 109 -> 6 bad, all 6 proven prior drift (5 bool-materialization
  + 1 ctor-leftover, per-item stash evidence). Numeric-address class
  fixed at three narrow points (wb dst, cast-nconst, CSE paren-strip).
- Gates: rebuild 114458/0/0, brace 0, parse 6/11/8, portable 747,
  full 837+/35 identical. No commit.

(End of file - turn 7, 2026-09-20)

## Addendum turn 8: gate repairs (2026-09-20)

- Crash class fixes (all prior-exposed, stash-proven): tied-sort,
  sret-facts guard, `_mi` preservation + delegate guard. Rebuild:
  114458/0/0. Parse 109 -> 6 bad (numeric-address trio + bool duo
  fixed narrowly with 5 unit tests); all 6 residuals stash-proven
  prior drift. Gates: portable 749, full 845/35 identical. No commit.

(End of file - turn 8, 2026-09-20)

## Addendum turn 9: parse-0 (2026-09-20)

- Residual bool family fixed narrowly: `_bool_sugar [^?]` guard,
  `_simplify_cond` whole-group check. Fold-call guard for
  `FOLD_RE`. 3 unit tests. All prior drift (stash-proven each).
- Gates: rebuild 114458/0/0, brace 0, parse 0/0/0 (was 109/5349/33),
  portable 751, full 846/35 identical. Promotion-ready pending call.

(End of file - turn 9, 2026-09-20)

## Addendum turn 10: regen review + ctor-home fix (2026-09-21)

- S7/S8 read-only subagent review: 20 golden REGEN + 7 review-test
  REGEN (all native-proven) applied and passing; 4 golden + 3 review
  FIX verdicts with fix specs (below). 67525 saturate deferred:
  honest `unknown`s vs stale-luck `0f/1.0f` pin (XMM lanes provable
  at `_piece_value`, but struct-param tails render GPR text; splat
  rendering unsound; scalar-lane extension tried then reverted).
- 18054/34279 FIXED (one root cause): whole-struct reload of a
  ctor-constructed home rendered a stale scalar (`return 0`) or the
  first field (`return fourCc1.m_Code`, changed return type).
  Fix: `_ctor_slots` proof (state init + calls record incl. `&`-stripped
  member-fold receivers and sizing-independent record for open-generic
  ctors) + whole-slot render in `_aggregate_load` gated on proved
  struct size == load width (side-effect-free stack_map lookup;
  eager slot_var creation flipped 108722 `= t1` to `= s_0`).
  Both pins regen'd to native-proven bodies. Zero regressions.
- Pre-existing (dirty-tree, stash-proven, NOT this session):
  `test_source_format` CRLF failure (bulk 19:36 LF checkout churn);
  108722/32174/25687 review failures (fail on clean-stash too).
  108722 root-caused: churn `_scalar_parts` tiles make the result
  store read stale `s_0` instead of live `t1`, orphaning the second
  call into dec DCE (`_drop_dead_temps`/`_locals` both guard impure
  calls, so the drop is downstream -- TBD via stage tracing).
- Remaining FIX (diagnosed, not yet attempted): 32832 (Change/Schedule
  + governing branches DCE'd), 104428 (vector31-38 lane temps
  abandoned before sibling GetBounds), 32174 (both struct calls gone
  + unbound obj19), 25687 (unbound obj18, [rbp-30h] Ray tile missing).
- Gates: goldens 61/3 (32832, 104428, 67525-deferred), full 872/9
  (those 3 + 5 review FIX + source_format-env). Portable 750 + 1 env.
  No commit (60+ pre-existing dirty files) -- commit needs user call.

(End of file - turn 10, 2026-09-21)

## Addendum turn 11: impure-DCE + sret-share fixes, re-promote (2026-09-21)

- 108722 FIXED: `_drop_dead_temps` dropped the orphaned 2nd shared
  call because the `/*shared body*/` comment between callee and `(`
  defeats `_IMPURE`. New `_impure` helper (comment-strip before test)
  at the 6 DCE guard sites in `dec/dataflow.py` (copies/temps/locals/
  lastdef). Unresolved/shared calls are impure by definition.
- 32174 FIXED: one native sret buffer shared by both calls, but the
  lifter minted a fresh temp per call. New `_sret_home_buf` map
  (state + calls sret fold): same stack home + same rty reuses the
  buffer temp, so the 2nd result is a reassignment
  (`primitiveValue1 = ...(1)`). Reassignment is exactly faithful --
  the callee overwrites the buffer. Residual: 16B-wide consumer
  stores still read stale slot (obj20 unbound, unpinned, pre-existing
  class).
- 32833/32837 regens (effect retention): the same `_impure` fix keeps
  one real native call each (0x1804FD690 x1, 0x180ECEC60 x1, both
  disasm-proven executed once) plus the correct live cascade; pins
  updated (+1/+2 lines).
- 25687 deferred: 2nd `.point` needs shared-Vector3-getter resolution
  (0x180895B20 shared by 8+ getters incl. RaycastHit.get_point;
  receiver-type disambiguation = new feature). 32832/104428 deferred:
  need retention research (Change/Schedule DCE, lane-temp
  over-collapse). CRLF contract restored (17 files, bulk-checkout
  damage; test_source_format green again).
- Gates: portable 751 (all green), full 877/4 (32832, 67525-deferred,
  104428, 25687 -- the diagnosed set, zero regressions), rebuild
  r3g_out1 114458/0/0 brace 0, re-promoted to final_out
  (byte-identical; +2 stub assemblies from retained calls).
  Pushed per user call (commit `1cf3e1c` was turn 10; this turn's
  files uncommitted).

(End of file - turn 11, 2026-09-21)

## Addendum turn 12: subagent analyses + 32832 fix, ponytail full (2026-09-21)

- Spawned 3 read-only analysis subagents (25687/32832/104428). All
  three paid off; two corrections to prior beliefs inside.
- 32832 FIXED: `_IMPURE` missed `>(`, so generic `Schedule<T>` /
  `Change<T>` calls classified pure and DCE'd with their blocks.
  Global regex broke CSE pins (rpc unfolded) -> scoped `>(` +
  comment-blindness to DCE-only `_impure()` helper; `_IMPURE` itself
  unchanged. Blocks restored (43 -> 70 lines, native-proven); pin
  regen'd. Residual: `Schedule<Obi...>` attributions (naming, separate).
- 25687 FIXED AS SIDE EFFECT: A1 proved the shared-getter fold
  already resolves 0x180895B20 -> RaycastHit.get_point at both sites;
  the sret-home sharing (turn 11) unifies them into 2x `.point`.
  No new feature needed. Residual: obj18 Format/LookRotation aliasing.
- 104428: my sret map briefly suspected, EXONERATED by experiment
  (fresh temps also drop snapshots; pin itself reuses vector32).
  Root: `movsd`-spills of XMMs clobbered by MPM calls (value-flow
  sidecar, not narrow) -> deferred with spec. Map stays: pin's reuse
  shape requires it; reverted-experiment residue verified absent.
- 67525: declined again (splat-vector render unsound; honest unknowns
  stand; stale-luck pin stays red by decision).
- Gates: portable 751, full 879/2 (104428 + 67525 only), rebuild
  NOT re-run this turn (code deltas since r3g: dataflow guards only;
  promotion carries turn-11 tree). Uncommitted: dataflow.py,
  goldens_review84.json.

(End of file - turn 12, 2026-09-21)

## Addendum turn 13: re-promote round-3h tree (2026-09-21)

- Rebuilt `r3h_out1` (114458/0/0, brace 0; 567 files differ from the
  turn-11 tree, all retained-effect lines from the `_impure` fix) and
  promoted to `final_out` (byte-identical copy verified, brace 0).
  Promoted tree now matches committed source through round 3g work.

(End of file - turn 13, 2026-09-21)







