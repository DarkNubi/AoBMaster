# RE Feature Implementation Plan: `locate` / `xref` + explicit per-version RVAs in `synth`

This document proposes an implementation plan for three Reverse-Engineering focused features:

1) A new command to **resolve/guess anchor RVAs** in a target build: `aobmaster locate` (aka “resolve”).
2) A new command to **find code references**: `aobmaster xref` / `aobmaster refs`.
3) An enhancement to `aobmaster synth` to **generate AoBs from explicit per-version RVAs** (no seed-based alignment required).

The goal is to make multi-version workflows practical when relative displacements and layout changes make exact-byte “seed” alignment unreliable.

---

## Goals / Success Criteria

### `locate`
- Given `(base exe, known base anchor RVA)` and a `(target exe with unknown RVA)`, output **top-N candidate RVAs** in the target with:
  - a confidence/score, match uniqueness, and the candidate AoB(s) used
  - enough diagnostic data to understand “why” (and why others were rejected)
- Works without requiring IDA/Ghidra, PDBs, or external tooling.
- Works for the common “same function, different layout” case.

### `xref`
- Given `(exe, target RVA/VA/FO)`, list **call/jmp** sites that reference that target.
- Output locations as FO/RVA/VA and include a minimal disassembly rendering for each hit.

### `synth` explicit per-version RVAs
- Allow users to provide a **mapping** of version binaries to their **known anchor RVAs**.
- `synth` then generates signatures using those explicit RVAs for validation (no bytespan/seed alignment step).

---

## Non-Goals (for v1)
- Full function-boundary recovery, CFG reconstruction, or decompilation.
- Structural similarity / ML-based matching.
- Import-table based semantic matching (that can be a later feature).
- Cross-architecture support beyond existing PE32/PE32+ handling.

---

## Command: `aobmaster locate` (RVA resolver)

### Why this is a separate command (not `synth`)
`synth` should remain responsible for **signature generation** given an anchor. RVA guessing is a different problem:
it wants different outputs (ranked candidates + diagnostics) and can be iterated without generating signatures.

### Core idea (v1): “Candidate-driven locate”
Use AoBMaster’s existing synthesis pipeline to generate **candidate AoBs** from the base around the anchor, then:
- scan the target binary’s executable sections for each candidate pattern
- aggregate all matches into a ranked list of candidate locations (RVA/FO/VA)

This avoids any requirement that a fixed “seed bytespan” exists in the target and naturally tolerates many relocations/offset changes
because candidates already contain wildcarding.

### Proposed CLI

Minimal:
```bash
aobmaster locate --base base.exe --anchor-rva 0x123456 --target target.exe --top-n 10
```

Options (initial set):
- Inputs:
  - `--base <path>`
  - `--anchor-rva | --anchor-fo | --anchor-va` (same as `synth`)
  - `--target <path>` (repeatable) OR `--targets <glob>` (optional convenience)
- Candidate generation (shared with `synth`):
  - `--profile ...`
  - `--context-before/after`, `--max-context-insns`, `--min-insns`, `--max-insns`
  - `--context-variations on|off`
  - `--anchor-shift N` (try nearby instruction starts)
  - `--top-n` (final output size)
  - `--candidate-limit` (how many base candidates to generate/scan before ranking; default e.g. 20)
- Scanning:
  - `--scan-range module|section` (default `module`)
  - `--section .text` (only if `section`)
  - `--allow-multiple` (if set, don’t discard candidates that hit multiple times; instead penalize)
- Output:
  - `--format json|text` (default `json`)
  - `--explain` (include extra scoring + per-candidate scan results)

### Output schema (JSON)
High-level:
```json
{
  "ok": true,
  "base": {"path": "...", "anchor_rva": "0x...", "anchor_fo": "0x...", "anchor_va": "0x..."},
  "targets": [
    {
      "path": "...",
      "results": [
        {
          "target_rva": "0x...",
          "target_fo": "0x...",
          "target_va": "0x...",
          "score": 0.9234,
          "match_count": 1,
          "candidate": {"aob": "...", "wildcard_ratio": 0.31, "byte_len": 42, "base_score": 0.88}
        }
      ]
    }
  ]
}
```

### Scoring proposal (simple + practical)
Start with a heuristic score that is easy to reason about:
- Base candidate score (existing synthesis scoring) is a strong prior.
- Penalize non-unique matches in the target.
- Prefer matches located in executable sections.

Example:
- `score = base_candidate_confidence * uniqueness_factor * length_factor`
  - `uniqueness_factor = 1.0` if match_count==1
  - else `uniqueness_factor = 1 / match_count` (or stronger penalty)
  - `length_factor` could mildly reward longer patterns (but do not over-reward if wildcard_ratio is high)

### Code changes (files / modules)
- Add `aobmaster/locate_command.py`
  - implement `run_locate(args)` similar to existing `run_scan` / `run_smart`
  - reuse:
    - anchor resolution from `aobmaster/synth.py` (`_resolve_anchor`)
    - candidate generation from `aobmaster/candidates.py` via `run_synthesis_core(..., version_binaries=[])`
    - scanning from `aobmaster/matcher.py` (`scan_ranges`) or similar logic used by `scan.py`
- Update `aobmaster/cli.py`
  - add `locate` subcommand + args
  - route `args.cmd == "locate"` to `run_locate`
- Update `docs/SDK_API_REFERENCE.md` (optional but recommended)
  - document `locate` output schema + examples

### Tests
Add tests using the existing PE generator in `tests/conftest.py` (`build_minimal_pe64`):
- `tests/test_locate_command.py`
  - Create base + target PE where target contains a wildcard-compatible variant of base’s anchor region.
  - Ensure `locate` returns the correct RVA and ranks it first.
  - Include a case where the same pattern appears twice and verify scoring penalizes it (unless `--allow-multiple`).

---

## Command: `aobmaster xref` / `aobmaster refs`

### Scope (v1)
Code xrefs for **near branch** instructions:
- `call rel32`, `jmp rel32`, and other “near branch” forms supported by iced-x86.

This is a big win for RE without needing full CFG recovery.

### Proposed CLI
```bash
aobmaster xref --file target.exe --to-rva 0x123456 --type call,jmp --scan-range module
```

Args:
- `--file <path>`
- destination:
  - `--to-rva 0x...` OR `--to-va 0x...` OR `--to-fo 0x...`
- filters:
  - `--type call|jmp|branch|all` (default `call,jmp`)
  - `--scan-range module|section` (default `module`)
  - `--section .text` (if `section`)
- output:
  - `--format json|text` (default `json`)
  - `--limit N` (default e.g. 200)
  - `--context 0|1|2` (optional: include preceding/following insn strings)

### Implementation approach
- Reuse `aobmaster.pe.PEFile` to iterate executable sections.
- For each executable section:
  - decode sequentially using `iced_x86.Decoder` (already used in `aobmaster/disasm.py`)
  - for each instruction:
    - if it is a near `CALL`/`JMP`/branch with a resolvable target:
      - compare the computed target VA/RVA to `--to-*`
      - if matched, record ref:
        - from_fo, from_rva, from_va
        - instruction text (using iced-x86 formatter or minimal custom string)
        - to_rva/to_va
- Output results sorted by `from_rva`.

### Code changes
- Add `aobmaster/xref_command.py`
  - implement `run_xref(args)`
  - share a small helper to normalize `to_*` into a canonical `to_va` + `to_rva`
- Update `aobmaster/cli.py`
  - add `xref` subcommand (and optionally alias `refs`)
- Optional: extend `aobmaster/disasm.py`
  - add a small helper to “decode entire section” efficiently (shared by xref and future tools)

### Tests
Add `tests/test_xref_command.py`:
- Build a minimal PE with a `.text` containing:
  - a `call rel32` to a known internal target
  - a `jmp rel32` to a known internal target
- Verify `xref --to-rva` returns correct reference locations.

---

## `synth`: Generate AoBs from explicit per-version RVAs

### Problem
Current `synth --versions ...` attempts to align anchors across versions using:
- `--align bytespan` (exact seed bytes must exist) OR
- `--align anchor-rva` (assumes same RVA across builds)

In real builds, **RVAs frequently drift** and exact bytes around an anchor often change due to relative displacements, so alignment fails.

### Desired behavior
Let users supply:
- base anchor RVA (or FO/VA)
- per-version anchor RVAs (explicit mapping)

Then `synth` can:
- generate candidates around each version’s true anchor
- validate candidates across all versions using the provided anchors
- output stable AoB signatures

### Proposed CLI additions

Option A (recommended): JSON mapping file
```bash
aobmaster synth --base base.exe --anchor-rva 0x123456 --versions-map anchors.json
```

`anchors.json` schema (v1):
```json
{
  "versions": [
    { "path": "v7.246.2/MapleStory.exe", "anchor_rva": "0x51A0000" },
    { "path": "v7.247.2/MapleStory.exe", "anchor_rva": "0x5189C01" }
  ]
}
```

Option B (convenience): repeatable `--version-anchor`
Windows-safe format (avoid `C:\...:0x...` ambiguity): use `@` delimiter:
```bash
aobmaster synth --base base.exe --anchor-rva 0x123456 ^
  --version-anchor "C:\path\to\v1.exe@0x51A0000" ^
  --version-anchor "C:\path\to\v2.exe@0x5189C01"
```

### Behavioral rules
- If `--versions-map` or `--version-anchor` is provided:
  - **do not** run `align_versions()` at all
  - interpret those anchors as authoritative
  - still run the normal validation steps across versions (uniqueness/present-all, etc.)
- If neither is provided:
  - preserve existing behavior (`--versions` + `--align ...`)

### Code changes
- Update `aobmaster/cli.py`
  - add new args to `synth` parser:
    - `--versions-map <Path>`
    - `--version-anchor <str>` (repeatable)
- Update `aobmaster/synth.py`
  - parse explicit anchors and construct an `AlignedAnchor` list directly:
    - base record + one record per version
    - compute FO/VA from RVA using `PEFile` conversions
    - compute drift_rva vs base for reporting
  - keep output schema stable but include:
    - `anchor.resolved_versions[]` with the explicit anchors and drifts
- Add input validation errors:
  - missing file paths
  - invalid hex RVAs
  - RVA not in an executable section

### Tests
Add `tests/test_synth_explicit_version_anchors.py`:
- Create 2–3 minimal PEs where the same “function” bytes are present but at different RVAs.
- Provide explicit RVAs per version and verify `synth` succeeds even though bytespan seed alignment would fail.

---

## Milestones (recommended delivery order)
1) `synth` explicit per-version RVAs (unblocks real usage immediately)
2) `locate` v1 (candidate-driven scan) with JSON output + top-N ranking
3) `xref` v1 (call/jmp xrefs)

---

## Future Enhancements (after v1)
- `locate` improvements:
  - instruction-shape fingerprints (ignore rel32 displacements)
  - constant pool matching (immediates, strings)
  - “structural” hints (prologue/epilogue, basic block count)
- `xref` improvements:
  - RIP-relative memory xrefs (strings, globals)
  - import xrefs (“where is `CreateFileW` called?”)
  - optional function boundary heuristic around each ref

