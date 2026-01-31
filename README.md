# AoBMaster v1.0

AoBMaster is a **standalone, deterministic CLI tool** that synthesizes **stable Array-of-Bytes (AoB) signatures** from a known **anchor address** in a **PE x64** binary, and optionally validates those signatures across multiple versions of the same program.

## Commands

- `aobmaster synth` — generate and rank AoB candidates from an anchor
- `aobmaster scan` — scan a PE file for a CE-style AoB pattern
- `aobmaster info` — show basic PE metadata

## Examples

Synthesize AoBs from an anchor RVA:

```bash
aobmaster synth --base game.exe --anchor-rva 0x123456
```

Validate across versions using default bytespan alignment:

```bash
aobmaster synth --base game_v1.exe --anchor-rva 0x123456 --versions game_v2.exe game_v3.exe
```

Cheat Engine Auto Assembler output:

```bash
aobmaster synth --base game.exe --anchor-rva 0x123456 --format ce
```

## Outputs

- **JSON** (default): machine-readable run record including inputs, hashes, anchor resolution, alignment, candidates, scores, warnings, and errors.
- **Text**: short human summary and top-ranked candidates.
- **CE**: `aobscanmodule(...)` lines for the top-ranked candidates.

## Limitations (v1.0)

- PE **x64 only** (PE32+ / AMD64).
- File-based analysis only (no live processes).
- No patching or binary modification.

## Development

Install dependencies:

```bash
python3 -m pip install -e .[test]
```

Run tests:

```bash
pytest
```

