# Decompiler recovery follow-up — 2026-09-19

## Status at stop

Stopped at the user's request. **The decompiler changes are experimental, incomplete, and not ready to promote.** No commit, full rebuild, corpus comparison, or promotion was performed. No new regression tests were written yet.

The goal is to improve the generic decompiler so these examples regenerate correctly—not hand-edit recovered game classes. The supplied path `work/blob/_out/Assembly-CSharp` does not exist; the matching examples are in `work/blob_out/Assembly-CSharp`.

The initial manual edits to MicAudioCanvas.cs, ConsoleUINavigation.cs, CollisionEventHandler.cs, and AnimationEventTrigger.cs were restored byte-for-byte from `work/mic_review_before/`. All four were verified restored at stop. `final_out/` was not edited.

## Working-tree ownership

Pre-existing changes, which must be preserved:
- `il2cpp/emitter.py`: static-data blob-container visibility handling.
- `docs/todo.md`: existing notes.
- `.freebuff/` and existing `validation_reports/probe_*` files.

Changes made during this task:
- `il2cpp/dec/analyze.py`: narrow a register to zero on a single incoming native null-equality edge.
- `il2cpp/lifter/insn.py`: recognize constant field-address ADD/SUB, distinguish value TESTs from null TESTs, render zero as null for reference stores, and wire aggregate load/store tracking.
- `il2cpp/lifter/calls.py`: inflate exact generic return types before sret handling; bind ordinary non-getter call results so ignored results do not erase calls; recognize one exact nullary interface-dispatch template; connect sret buffers to aggregate tracking.
- `il2cpp/lifter/values.py`: typed TEST classification, correct scalar types on struct-field reads, and reconstruction of copied by-value struct arguments.
- `il2cpp/lifter/aggregates.py` (new): experimental byte-range provenance for stack copies and struct assembly.
- `il2cpp/expr.py`, `il2cpp/lifter/state.py`, `il2cpp/lifter/__init__.py`: provenance slots, copy support, and mixin wiring.

`calls.py` currently has a disproportionately large diff (about the whole file). Inspect line-ending changes and remove incidental churn before review. Core Python files have a CRLF/no-BOM contract; the launcher has a different BOM contract. Avoid blindly normalizing unrelated lines.

## Evidence and current result

Local fixture: `testgame/GameAssembly.dll` and `testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat`. The binary was read statically, not executed.

| Example | MethodDef / VA | Latest observed result |
| --- | --- | --- |
| MicAudioCanvas.Start | 26312 / 0x180565720 | Null arm now assigns null; non-null arm uses a Recorder; duplicate raw write is gone. |
| MicAudioCanvas.OnVoiceConnectionReady | 26311 / 0x1805656D0 | Intermediate probe removed duplicate raw write and kept typed recorder assignment. Recheck against final working tree. |
| MicAudioCanvas.Update | 26313 / 0x180565750 | Now reads CurrentAvgAmp and compares against InputMode.OpenMic. Still emits an int for the enum local, bool/int mixtures, and a branch-local flag used outside its scope. |
| ConsoleUINavigation.OnEnable | 24655 / 0x18069DC90 | RemoveAll is now retained, but the predicate delegate is still incomplete, list Count renders as Length, and navigation still collapses to scalar 4 with missing neighbor links. |
| ConsoleUINavigation predicate | 24659 / 0x1806AF040 | Native metadata proves RemoveOnConsole checks on the selectable and its immediate parent, then !enabled. Generic GetComponent and delegate construction still need recovery. |
| CollisionEventHandler.OnDrawGizmos | 23917 / 0x180515DA0 | Now recovers typed Oni.Contact, distance, and normal.x. Still has undefined temps, incomplete vector/color arguments, raw count access, and a scalar ray direction. Not fixed. |
| AnimationEventTrigger.TeleportPlayer | 24224 / 0x180606AF0 | Latest probe passes all three position components and the complete Quaternion. Vector copy renders as a field initializer rather than a direct value copy. Needs regression and corpus validation. |

Native facts established:
- Navigation calls `List<Selectable>.RemoveAll`, sets explicit mode (4), connects the previous/next remaining controls, and preserves existing endpoint links where no neighbor exists.
- Hidden metadata slot 0x183BE71E0 identifies `Component.GetComponent<RemoveOnConsole>`; 0x183C17240 identifies `List<Selectable>.RemoveAll`.
- Mic interface slot 0 resolves to `AudioUtil.ILevelMeter.CurrentAvgAmp`, not peak amplitude.
- Contact drawing uses pointB, normal * distance, green for positive distance and red otherwise, then sets cyan.
- Interface helper at 0x180002BB0 searches interfaceOffsets and invokes a nullary method through the vtable. The implementation matches its instruction template, not this address or a game class name.

Probe artifacts under ignored `work/`:
- `mic_review_native.json`: original navigation, contact, and mic Update instructions/bodies.
- `mic_review_more.json`: original Start, connection callback, and teleport instructions/bodies.
- `mic_review_candidate.json`: early decompiler changes.
- `mic_review_small.json`: intermediate mic output, superseded by the aggregate probe.
- `mic_review_aggregate.json`: latest successful targeted lift; inspected at stop.
- `mic_review_before/`: original four generated files, already restored.

## Validation actually completed

One portable test run, before the final aggregate changes:

`python -m pytest -q -m "not game" --disable-warnings --maxfail=3`

Result: **626 passed, 3 failed, 126 deselected**, stopped after three failures. Failures in `tests/test_stack_args.py`:
- `test_resolved_call_recovers_the_fifth_stack_argument_without_xmm_tail_noise`
- `test_resolved_scalar_float_result_uses_xmm0`
- `test_resolved_byref_float_result_uses_rax`

Those tests expect an inline call expression in the result register; eager binding now puts a temp there. Review the semantic change and assert both the emitted call and result register, rather than simply replacing expected strings. Further failures may exist.

The subsequent test invocation was interrupted. There is no completed test result for the final working tree. Successful targeted lifting only proves those probes ran; it does not prove compilation, equivalence, or absence of regressions.

## Next work, in order

1. **Audit/isolate the aggregate experiment first.** It suppresses some original stack stores, invents reconstructed struct initializers, and carries fragments through register-state merges. It must never drop observable effects or replace an unsupported case with guessed fields. Roll back only this task's aggregate changes if a small, sound implementation cannot be established.
2. Add focused synthetic regressions and native fixture cases for field-address barriers, null-edge assignment, enum TESTs, ignored call results, exact generic return inflation, interface-dispatch recognition, and complete Vector3/Quaternion argument recovery. Include negative cases: ambiguous signatures, nonmatching helper bytes, partial copies, overwritten fragments, overlapping fields, and conflicting CFG paths.
3. Validate null-edge narrowing against direct native TEST/CMP evidence, not only rendered condition text. Check the flat lifting path and all callers of shared helpers too.
4. Verify interface-template recognition, scalar return ABI, metadata interface ownership, and unknown/generic/byref rejection. Do not infer helper identity from its address or a method name.
5. Finish aggregate correctness: stack-frame offsets and slot reuse; byte coverage and SIMD lanes; register spills; branch merges; loops/back edges; aliasing and calls that mutate stack memory; invalidation after writes. Preserve scalar field types and full value lifetimes. Avoid generating inaccessible-field initializers as if they were valid source-level constructors.
6. Finish navigation recovery: exact closed predicate signature/delegate target, generic GetComponent, list Count, full Navigation value copy, mode, and up/down assignments. Retaining RemoveAll alone does not finish the fix.
7. Finish contact recovery: native list count/indexing, pointB Vector3 construction, packed color constants, normal scaling, and all outgoing struct arguments. Remove undefined temps by fixing provenance, not textual substitution.
8. Finish mic output typing and phi-variable scope: enum locals must retain enum types; Boolean results must not become int arguments to SetActive; PTT flag must be declared in a scope shared by both branches and its use.
9. Only after correctness, consider the key-name hash-switch simplification and event +=/-= cleanup. RPC plumbing is optional; ShrineEvent needs no change based on the report. Do not rewrite by class name or hardcoded RVA.
10. Run the full portable and licensed-fixture suites with PYTHONHASHSEED=0 and the fixture environment variables. Review golden differences against native instructions; do not blindly regenerate snapshots. Run strict emission, parse checks, and before/after compiler/corpus comparisons into a separate candidate tree. Preserve pre-existing emitter/docs work. Promote generated output only once these gates pass.

## Resume commands

PowerShell, from the repository root:

```powershell
$env:PYTHONHASHSEED = '0'
$env:IL2CSHARP_METADATA = (Resolve-Path 'testgame/ShiftAtMidnight_Data/il2cpp_data/Metadata/global-metadata.dat').Path
$env:IL2CSHARP_BINARY = (Resolve-Path 'testgame/GameAssembly.dll').Path
python -m pytest -q
python tools/inspect_methods.py --metadata $env:IL2CSHARP_METADATA --binary $env:IL2CSHARP_BINARY --va 0x180565720 0x1805656D0 0x180565750 0x18069DC90 0x1806AF040 0x180515DA0 0x180606AF0 --save work/mic_review_resume.json
```

## Addendum 2026-09-20 (round 3c, unpromoted)

Items 6/7/8 mostly landed since the stop record: generic GetComponent,
list/nativelist Count, mic enum/bool/scope, event +=/-=, 32837 zeros,
m_State/m_StateBlock, 31664 construction, SIMD twins (70050 golden-exact,
107123 /* nothing */). Full suite 822 passed / 22 failed (all triaged).
Still open with evidence/designs in docs/todo.md: Navigation merge-side
facts (read-side phi atoms disproved), per-arm Color (repros: mi
23917/27827/26794), 22 goldens awaiting gated regen. switch(string)
phase 1 landed (mi 25293/24765/25577/26314 fold; 24694 gotos decline;
jumped-label + temp-use hardening). final_out/ untouched.
final_out/ untouched.
