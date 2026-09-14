# Validation evidence

**Current live tree: fix 97 (Review 84 baseline + fixes 85–97, package split).**
Start with `review84/summary.json` (baseline), `review97e_sweep.json` +
`review97e_vs97.json` + `review97e_parse.json` + `review97e_promotion_verification.json`
(promoted tree, 11,200 files, `93a4eb7b…9d87a2`,
0 mismatches) and `../docs/reviews/REVIEW84.md`–`REVIEW87.md` + `../docs/todo.md` (Current work).
The strict build has 0 failures/fallbacks, the syntax gate 0 bad files, the direct sweep
0 crashes. The `.zip` release artifact (`docs/reviews/REPLACEMENT.md`) still describes the
Review 84 handoff ZIP; for the live tree see `../README.md` and `validation_reports/SHA256SUMS.txt`
(`tools/verify_release.py`). The Review 89 tree is kept at `../bckups/final_out_review89`,
the fix-94 tree at `../bckups/final_out_review94`.

Earlier releases — Review 84 (`review84/`), Review 80 (`review80/`), Reviews 79/78
(`review79/`, `review78/`) — are preserved below. Their old bundling/"current"
descriptions are not the state of this replacement.

Historical note: **Review 80 was the last release whose validation ZIP was
regenerated for the archive.** Later promotions (Reviews 84–89, fixes 93–97) keep their
evidence in `review84/`, `review85/`, `split_rebuild_verification.json`,
`review93_*`/`review94_*`, and `review97*/review97e_*` report files; the
`review80/` record below remains the last fully-bundled per-file evidence set.

# Review 77 validation evidence

Start with `../docs/reviews/REVIEW.md` for changes, results, caveats and reproduction commands.
`summary.json` records the exact source/fixture hashes and tested environment.
The game was statically read only; its binaries and the full emitted C# trees
are **not** included.

## Included reports

- `baseline_parse.json`, `final_parse.json`, `parse_diff.json`: per-file C#
  syntax gates, including otherwise-hidden parser recovery nodes.
- `baseline_sweep.json`, `final_sweep.json`: direct-lift sweep summaries from
  the **same final validator**. The baseline is the complete audited rerun;
  discarded early/partial audit results are not bundled.
- `baseline.methods.jsonl.gz`, `final.methods.jsonl.gz`: all 116,178 native-backed
  MethodDef rows with output hashes and audit metrics, not full method bodies.
- `final.tail-args.jsonl.gz`: observed before/after argument preparation at the
  tail helper. The baseline file is empty because that helper did not exist.
- `sweep_diff.json`: every changed method hash and structural-metric comparison.
- `baseline_repeatability.json`: all body hashes matched the repeated baseline.
- `output_diff.json`, `output_changes.diff.gz`: full per-file hash comparisons
  and changed-output excerpts, not a replacement for the complete output tree.
- `*_build.log`, `tests_final_all.log`: original successful build/test runs.
- `tests_release_copy.log`: all 136 tests passed again from the portable release
   copy. Both report comparisons reproduced exactly, all Python files compiled,
   and `../changes.patch` (ships with the portable release copy, not this
   checkout) applied cleanly to the uploaded baseline and reproduced
   the released files.
- `cli_filter.log`, `cli_filter_parse.json`: actual direct-binary filter smoke.
- `tails_before.json`, `tails_after.json`, `byref_after.json`,
  `pointer_methods_after.json`, `gameplay_after.json`, `native_constant.json`:
  selected native instructions/re-lifts and the independently read float constant.

## Recheck portable comparisons

From the project root, with the development requirements installed:

```bash
python tools/validate_corpus.py compare validation_reports/review80/baseline_parse.json validation_reports/review80/final_parse.json --report work/rechecked_parse_diff.json
python tools/validate_corpus.py compare validation_reports/review80/baseline_sweep.json validation_reports/review80/final_sweep.json --report work/rechecked_sweep_diff.json
# For the live tree, compare validation_reports/review84/summary.json + review85/sweep4.json + split_rebuild_verification.json
```

Manifest paths in these copies are relative to their report directory. Generated
tree paths are descriptive labels because those trees are not bundled. Original
fixture directory paths in logs are redacted. Elapsed times are observational;
concurrent jobs make them unsuitable for performance comparisons.
