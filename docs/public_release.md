# Public release checklist

Status 2026-09-28: the repository is **private**. The chosen route is a
fresh, scrubbed public copy; this file records what is publishable and how
the pieces were prepared.

## Never publish (licensed game data or derived output)

- `testgame/` — the supplied Shift At Midnight `GameAssembly.dll` and
  `global-metadata.dat`. Tracked via Git LFS, so the blobs live in the
  remote's LFS storage: deleting the folder in a new commit does **not**
  remove them from history or from GitHub. Purge with `git filter-repo`
  plus an LFS cleanup, or (preferred) never flip this repo and export a
  scrubbed copy instead.
- `final_out/` — the promoted decompiled tree (r10), git-ignored, ~153 MB.
- `work/` — local scratch and provenance, git-ignored (~16 MB after the
  2026-09-28 cleanup).

## Scrubbed export

1. Copy the tracked file set, excluding `testgame/**`; `git ls-files` is
   the authoritative list.
2. Hash the golden snapshots:
   `python tools/goldens_hash_only.py tests/goldens_review84.json --output <export>/tests/goldens_review84.json`.
   `tests/test_game_goldens.py` compares hashes for hash-only snapshots
   and skips entirely when no fixture env is set.
3. Remove the two `filter=lfs` lines from `.gitattributes` (no LFS
   objects exist in the export).
4. Regenerate `validation_reports/SHA256SUMS.txt` with
   `python work/split/refresh_manifest.py --write` — the shipped one
   hashes `testgame/` and `final_out/` paths from the private tree — or
   drop it.
5. Scan for fixture references (`testgame`, `final_out`,
   `Shift At Midnight`). Prose may stay; binaries and output trees may
   not.
6. `python -m pytest -q -m "not game"` must pass with no fixture env
   set; the game-marked tests skip.
7. Keep `LICENSE` (MIT) and its scope note: it covers the decompiler
   source only, never game-derived content.

## Decisions recorded 2026-09-28

- Fixture: keep the repository private for now; no history rewrite
  performed.
- Golden snapshots: hash-only in the public copy (user call); the tool
  and test support land here.
- License: MIT for the source (user delegated the choice).
