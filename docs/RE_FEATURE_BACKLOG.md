# RE Feature Backlog (Potential Future Implementation)

This document lists additional RE-focused modes that are likely to be useful, but are **not** part of the current implementation plan.

For the active plan, see `docs/RE_LOCATE_XREF_IMPLEMENTATION_PLAN.md`.

---

## High-value next candidates

### `sig test --ad-hoc`
Test a raw AoB against:
- one binary (`--binary`)
- a corpus (`--corpus glob1 glob2 ...`)

Without requiring the DB. Output hit counts and offsets. This is a fast iteration loop while building signatures.

### `diff` (code-region diff)
Given:
- `--base base.exe --base-rva 0x...`
- `--other other.exe --other-rva 0x...`

Disassemble both and output a human-readable comparison:
- which instructions match in shape
- which bytes differ (esp. rel32 displacements)
- recommended “stable” anchor candidates near that area

### `patch` / `apply` (signature verifier / resolver)
Given:
- an AoB signature
- a target binary

Scan and report:
- match count
- matched FO/RVA/VA
- a short disasm window around the match
- optional: emit a ready-to-use Cheat Engine symbol snippet

### `xref` extensions
Beyond call/jmp:
- RIP-relative memory refs (global vars, vtables)
- string xrefs
- import xrefs (“who calls `GetProcAddress`?”)

---

## Additional useful modes

### `strings` (RE-friendly extraction)
- extract ASCII/UTF-16 strings
- include FO/RVA/VA, section name
- optional min length, entropy filter

### `symbols`
If available:
- parse exports
- optionally load PDB (where present) to map names ↔ RVAs

### `importscan`
Summarize imports and optionally find likely call sites:
- scan for IAT references or `call [rip+...]` patterns
- useful for quickly locating API usage

### `cfg-lite`
Given an RVA, attempt:
- function boundary heuristic (prologue patterns, ret/jmp tail)
- basic block discovery via branch targets

Output a small DOT/JSON graph for quick inspection.

### `bytes` / `hexdump`
Ergonomic dump by FO/RVA with:
- section context
- optional disasm overlay for decoded instructions

### `rebase`
Utility conversions:
- VA ↔ RVA ↔ FO
- show section name and raw pointer ranges

### `trace-match`
For a signature hit:
- explain why each wildcarded byte matched
- show the instruction/operand context

### `sig rank`
Given a set of candidate AoBs:
- rank by uniqueness across a corpus
- rank by stability across versions (requires test corpus)

### `collect` (workspace/manifest builder)
Given a folder of versions:
- build a manifest with hashes, labels, section layouts
- optional: infer version label from path

This makes other commands reproducible and CI-friendly.

### `batch` / `pipeline`
Run:
- locate → synth → test

Across many targets using a single config/manifest file.

