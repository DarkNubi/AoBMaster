# AoBMaster v2.0

AoBMaster is a **standalone, deterministic CLI tool and signature management platform** that synthesizes **stable Array-of-Bytes (AoB) signatures** from a known **anchor address** in a **PE x64** binary, and optionally validates those signatures across multiple versions of the same program.

**What's New in v2.0:**
- 🔍 **Explainability**: Understand WHY patterns work with `--explain` mode
- 💾 **Signature Database**: Persistent storage and version control for signatures
- 🧪 **Automated Testing**: Test signatures against binary corpus with regression detection
- 📊 **Temporal Analysis**: Predict when signatures will break before they break
- 🏗️ **Signature Families**: Track signature evolution and lineage over time
- 🎯 **Structural Anchors**: Function-relative anchoring (experimental)

v2.0 is **fully backward compatible** with v1.x - all v1.x commands work identically.

## Commands

### v1.x Commands (Core Functionality)

- `aobmaster synth` — generate and rank AoB candidates from an anchor
- `aobmaster scan` — scan a PE file for a CE-style AoB pattern
- `aobmaster info` — show basic PE metadata

### v2 Commands (Signature Management & Analysis)

- `aobmaster synth --explain` — generate signatures with explainability trace
- `aobmaster db init` — initialize signature database
- `aobmaster db save` — save signature to database
- `aobmaster db list` — list all signatures in database
- `aobmaster db query` — query signature by ID
- `aobmaster db export` — export signatures to JSON
- `aobmaster db import` — import signatures from JSON
- `aobmaster test` — test signatures against binary corpus
- `aobmaster analyze` — perform temporal analysis on signatures
- `aobmaster diagnose` — show signature family lineage

## Quick Start Examples

### Basic Synthesis

Synthesize AoBs from an anchor RVA:

```bash
aobmaster synth --base game.exe --anchor-rva 0x123456
```

### Multi-Version Validation

Validate across versions using default bytespan alignment:

```bash
aobmaster synth --base game_v1.exe --anchor-rva 0x123456 --versions game_v2.exe game_v3.exe
```

### Cheat Engine Auto Assembler Output

```bash
aobmaster synth --base game.exe --anchor-rva 0x123456 --format ce
```

### Using Different Wildcard Profiles

```bash
# Minimal wildcarding (maximum uniqueness, may break on updates)
aobmaster synth --base game.exe --anchor-rva 0x123456 --profile minimal

# Balanced wildcarding (recommended for most cases)
aobmaster synth --base game.exe --anchor-rva 0x123456 --profile balanced

# Aggressive wildcarding (maximum stability across versions)
aobmaster synth --base game.exe --anchor-rva 0x123456 --profile aggressive
```

### Context Variations

Generate multiple candidate sets with different context windows:

```bash
aobmaster synth --base game.exe --anchor-rva 0x123456 --context-variations on
```

### v2 Explainability Mode

Understand WHY patterns work or fail:

```bash
aobmaster synth --base game.exe --anchor-rva 0x123456 --explain
```

### v2 Database Workflow

Build a signature database for your project:

```bash
# Initialize database
aobmaster db init --db signatures.db

# Generate and manually save signature
aobmaster synth --base game.exe --anchor-rva 0x123456 --format json > sig.json
# (Then use db save to store it - see documentation)

# List all signatures
aobmaster db list --db signatures.db

# Test signatures against corpus
aobmaster test --db signatures.db --corpus "releases/*.exe" --record

# Analyze signature stability over time
aobmaster analyze --db signatures.db

# View signature family lineage
aobmaster diagnose --db signatures.db --signature-id sig_001
```

### Control Output Size

Limit the number of top candidates shown in text/CE formats:

```bash
aobmaster synth --base game.exe --anchor-rva 0x123456 --format text --top-n 10
```

## v2 Features Deep Dive

### Explainability (--explain)

v2 adds transparent reasoning about signature generation:

```bash
aobmaster synth --base game.exe --anchor-rva 0x123456 --explain
```

The `--explain` flag adds structured trace events showing:
- **Anchor Resolution**: How the anchor address was resolved (RVA/FO/VA)
- **Alignment Events**: How patterns were aligned across versions
- **Wildcarding Decisions**: Why each byte is wildcarded or fixed
- **Scoring Breakdown**: Component scores (uniqueness, presence, specificity, length, proximity)
- **Validation Results**: Why patterns passed or failed validation

This makes AoBMaster a "glass box" instead of a "black box" - you understand exactly why patterns work.

### Signature Database

Store and manage signatures persistently:

```bash
# Initialize
aobmaster db init --db sigs.db

# Save signature (after manual creation - see full docs)
aobmaster db save --db sigs.db --id sig_001 --name "player_health" --pattern "48 8B ?? ??" ...

# List with optional filter
aobmaster db list --db sigs.db --filter "health"

# Query by ID
aobmaster db query --db sigs.db --id sig_001

# Export for sharing
aobmaster db export --db sigs.db --output sigs.json

# Import from team member
aobmaster db import --db sigs.db --input team_sigs.json
```

**Benefits:**
- Signatures persist across sessions
- Version control friendly (export to JSON)
- Team collaboration (share databases)
- Audit trails (who created what, when)

### Automated Testing

Test signatures against binary corpus automatically:

```bash
# Test single signature
aobmaster test --db sigs.db --signature sig_001 --binary game.exe

# Test against corpus (glob patterns)
aobmaster test --db sigs.db --corpus "releases/*.exe"

# Record results in database
aobmaster test --db sigs.db --corpus "*.exe" --record

# Parallel execution
aobmaster test --db sigs.db --corpus "*.exe" --parallel 4
```

**Use Cases:**
- CI/CD regression testing
- Signature validation before deployment
- Quality assurance workflows
- Pattern stability monitoring

### Temporal Analysis

Predict when signatures will break:

```bash
# Analyze single signature
aobmaster analyze --db sigs.db --signature-id sig_001

# Analyze all signatures
aobmaster analyze --db sigs.db
```

**Output includes:**
- **Pass Rate**: Historical success rate (e.g., 87.0%)
- **Confidence Interval**: Current/pessimistic/optimistic estimates
- **Stability Assessment**: "stable", "moderately_stable", "fragile", "unstable"
- **Breakage Prediction**: Likelihood of future failure
- **Drift Analysis**: RVA drift trends over time
- **Recommendations**: Actionable advice (e.g., "Consider regenerating signature")

**This is v2's killer feature:** Know when patterns will break BEFORE they break, not after.

### Signature Families

Track signature evolution over time:

```bash
aobmaster diagnose --db sigs.db --signature-id sig_002
```

**Example Output:**
```
Signature Family: player_health
Family Size: 3 signatures

Lineage:
  1. player_health_v1 (sig_001) [DEPRECATED]
     Pattern: 48 8B ?? ?? ?? ??
     Version Range: 1.0.0-1.5.3
     Tests: 15, Pass Rate: 100.0%
     Deprecation: Broke at v1.6 due to compiler inlining
  
    2. player_health_v2 (sig_002) ← CURRENT
       Pattern: 48 83 EC 20 48 8B ?? ?? ?? ??
       Version Range: 1.6.0-current
       Tests: 8, Pass Rate: 87.5%
       Parent: sig_001
```

**Benefits:**
- Never lose institutional knowledge
- Understand why signatures broke
- Track pattern evolution
- Forensic analysis of signature history

### Structural Anchors (Experimental)

Function-relative anchoring (opt-in, high-risk):

```bash
aobmaster synth --base game.exe --anchor-rva 0x123456 --anchor-mode structural
```

**How it works:**
- Detects function boundaries (prologue patterns)
- Anchors patterns relative to function start
- More resilient to code movement within functions

**Caveats:**
- Heuristic-based (70-80% accuracy)
- Only works with standard compiler-generated prologues
- Fails loudly on low confidence
- Use with caution and validation

**Default:** `--anchor-mode byte-offset` (v1.x behavior)

## Wildcard Profiles

AoBMaster supports 8 wildcard profiles to balance **uniqueness** (fewer false positives) vs **stability** (resilience to updates):

| Profile | Wildcards | Use Case |
|---------|-----------|----------|
| **minimal** | Only branch/call offsets | Maximum pattern uniqueness; use when binary rarely changes |
| **strict** | Same as minimal | Alias for minimal; most restrictive wildcarding |
| **default** | Branches + all memory displacements | **Recommended**: balanced approach for most scenarios |
| **balanced** | Default + RIP-relative globals | Good middle ground between uniqueness and stability |
| **aggressive** | Everything including immediates | Maximum version resilience; use for frequently updated binaries |
| **stack-only** | Only stack offsets ([rsp/rbp+X]) | Focus on stack frame changes only |
| **global-only** | Only RIP-relative addressing | Focus on global variable relocation |
| **memory-heavy** | All memory displacements | Comprehensive memory operand wildcarding |

### What Gets Wildcarded?

- **Branches (all profiles)**: `call`, `jmp`, `jcc` relative offsets (change when code moves)
- **RIP-relative (default+)**: Global variable addresses affected by ASLR
- **Stack offsets (default+)**: `[rsp+X]`, `[rbp+X]` frame layout changes
- **Other displacements (default+)**: `[reg+X]` struct/array offsets
- **Immediates (aggressive only)**: Constant values that may be tuned

## Context Variations

The `--context-variations on` option generates candidates using multiple instruction window configurations:

- **User-specified context**: Your `--context-before` and `--context-after` values
- **Forward-heavy**: `(0, 10)`, `(0, 15)` — useful for patterns after the anchor
- **Balanced**: `(5, 10)` — equal weight before and after
- **Backward-heavy**: `(10, 5)`, `(12, 8)` — more instructions before anchor

This increases candidate diversity and may find more stable regions.

## Understanding Output

### JSON Format (Default)

Machine-readable output including:
- Full run metadata (inputs, versions, alignment details)
- SHA-256 hashes of all binaries analyzed
- All candidates with scores, patterns, and validation results
- Warnings and errors with diagnostic context

### Text Format

Human-readable summary showing:
- Top N candidates (configurable with `--top-n`)
- Score breakdown (uniqueness, presence, specificity, length, anchor proximity)
- Confidence metric based on drift and alignment quality
- CE-formatted patterns for easy copy-paste

### CE Format

Cheat Engine Auto Assembler syntax:
```asm
aobscanmodule(AOB_MASTER_1, game.exe, 48 8B 05 ?? ?? ?? ?? 85 C0)
aobscanmodule(AOB_MASTER_2, game.exe, 48 89 5C 24 ?? 48 89 74 24 ??)
```

## Scoring Explained

Each candidate receives a composite score (0.0-1.0) based on:

1. **Uniqueness (U)** [35% weight]: Pattern matches exactly once in base binary
2. **Presence (P)** [25% weight]: Pattern exists in all provided versions
3. **Specificity (S)** [20% weight]: Lower wildcard ratio = more specific pattern
4. **Length Regularization (L)** [10% weight]: Prefers ~32 bytes (penalizes too short/long)
5. **Anchor Proximity (A)** [10% weight]: Pattern centered on anchor instruction

**Confidence** (separate metric) considers:
- Number of versions validated (more = higher confidence)
- RVA drift magnitude (large drift = lower confidence)
- Alignment ambiguity (multiple seed matches = lower confidence)
- Anchor resynchronization needed (not instruction-aligned = lower confidence)

## Advanced Options

### Anchor Specification

```bash
--anchor-rva 0x123456   # Relative Virtual Address (preferred)
--anchor-fo 0x1000      # File offset
--anchor-va 0x140001000 # Virtual address
```

### Alignment Modes

```bash
--align bytespan         # Default: search for byte pattern (robust to drift)
--align anchor-rva       # Assume identical RVA across versions (fails if drifted)
```

### Bytespan Alignment Tuning

```bash
--seed-bytes 32          # Bytes to extract around anchor for alignment (default: 32)
--seed-scan section      # Search within section only (default)
--seed-scan module       # Search entire executable sections
--seed-allow-multi true  # Allow multiple seed matches (use with caution)
```

### Context Control

```bash
--context-before 8       # Instructions before anchor (default: 8)
--context-after 8        # Instructions after anchor (default: 8)
--max-context-insns 32   # Maximum total instructions (default: 32)
```

### Candidate Generation

```bash
--min-insns 6            # Minimum instruction window size (default: 6)
--max-insns 14           # Maximum instruction window size (default: 14)
```

### Scanning Scope

```bash
--scan-range section     # Scan only anchor's section (default for base)
--scan-range module      # Scan all executable sections (default for versions)
```

### Validation Rules

```bash
--require-unique true    # Reject if pattern matches multiple times (default)
--require-present-all true  # Reject if pattern missing in any version (default)
```

## Outputs

- **JSON** (default): machine-readable run record including inputs, hashes, anchor resolution, alignment, candidates, scores, warnings, and errors.
- **Text**: short human summary and top-ranked candidates.
- **CE**: `aobscanmodule(...)` lines for the top-ranked candidates.

## Limitations

### v1.x Limitations (Still Apply)

- PE x86 and x64 (PE32 (x86) and PE32+ (x64)) only
- File-based analysis only (no live processes)
- No patching or binary modification

### v2 Additional Notes

- **SDK (Phase 7)**: Design complete, implementation pending (v2.1 roadmap)
- **Structural Anchors (Phase 6)**: Experimental, heuristic-based, opt-in only
- **Test Command**: Core functionality complete, some CLI features pending
- **Multi-Architecture**: Still PE x64 only (ARM, MIPS, etc. not supported)

## Development

Install dependencies:

```bash
python3 -m pip install -e .[test]
```

Run tests:

```bash
pytest
```

## Troubleshooting

### "Anchor not within any section"
- Verify your anchor address is valid for the binary
- Try different anchor address types (`--anchor-rva`, `--anchor-fo`, `--anchor-va`)

### "No valid candidates"
- Pattern may be too unique or too generic
- Try different `--profile` options (e.g., `balanced` or `aggressive`)
- Enable `--context-variations on` for more diversity
- Adjust `--min-insns` / `--max-insns` range

### "Alignment failure"
- Seed pattern not found in version
- Try increasing `--seed-bytes` (e.g., 48 or 64)
- Or use `--seed-scan module` to search more broadly
- Or use `--align anchor-rva` if RVAs are stable

## Tips for Best Results

1. **Start with default profile**: `--profile default` works for most cases
2. **Use multiple versions**: Validation across 2-3 versions greatly improves confidence
3. **Enable context variations**: `--context-variations on` finds better patterns
4. **Check confidence scores**: Low confidence (<0.5) means pattern may be unstable
5. **Prefer high uniqueness**: Patterns with U=1.0 have exactly one match (ideal)
6. **Review drift metrics**: Large RVA drift (>4KB) suggests major code changes

## Examples by Use Case

### Game Trainer Development
```bash
# Maximum stability for frequently updated games
aobmaster synth --base game_v1.0.exe --anchor-rva 0x12345 \
  --versions game_v1.1.exe game_v1.2.exe \
  --profile aggressive --context-variations on --format ce
```

### Malware Analysis
```bash
# High uniqueness to avoid false positives in samples
aobmaster synth --base malware.exe --anchor-rva 0xABCD \
  --profile minimal --require-unique true --format json
```

### Reverse Engineering Research
```bash
# Balanced approach with comprehensive output
aobmaster synth --base target.exe --anchor-rva 0x5678 \
  --versions target_v2.exe --profile balanced \
  --context-variations on --format json
```



## Upgrading from v1.x to v2.0

### Is v2 Right for You?

**Stick with v1.x if:**
- You only need one-shot signature generation
- You don't need signature persistence
- Simple CLI workflow is sufficient

**Upgrade to v2.0 if:**
- You want to understand WHY patterns work (`--explain`)
- You need to manage signatures over time (database)
- You want automated testing and CI/CD integration
- You need predictive analysis (when will signatures break?)
- You work on a team and need to share signatures

### Migration Path

v2.0 is **100% backward compatible**. Your v1.x commands work identically:

```bash
# This still works exactly as before
aobmaster synth --base game.exe --anchor-rva 0x123456
```

To adopt v2 features progressively:

1. **Start with --explain**: Add explainability to existing workflows
   ```bash
   aobmaster synth --base game.exe --anchor-rva 0x123456 --explain
   ```

2. **Create a database**: Initialize signature storage
   ```bash
   aobmaster db init --db project_sigs.db
   ```

3. **Store signatures**: Save your generated patterns
   ```bash
   # Generate signature, then save manually (see full docs)
   ```

4. **Add testing**: Validate against corpus
   ```bash
   aobmaster test --db project_sigs.db --corpus "releases/*.exe" --record
   ```

5. **Enable analysis**: Track temporal stability
   ```bash
   aobmaster analyze --db project_sigs.db
   ```

### Breaking Changes

**None!** v2.0 is fully backward compatible. All v1.x commands, flags, and outputs work identically.

### Version Numbers in Output

- v1.x outputs: `"version": "1.1.0"`
- v2.0 outputs: `"version": "2.0.0"`

This allows tooling to detect v2 features programmatically.

## What Makes v2 Different?

### v1.x: Point-in-Time Tool

- Generate signatures → use immediately
- No memory (signatures are ephemeral)
- Black box (no reasoning about decisions)
- Manual testing required
- Individual developer workflow

### v2.0: Signature Intelligence Platform

- Generate signatures → store → track → analyze
- Persistent memory (signatures accumulate value)
- Glass box (full explainability with `--explain`)
- Automated testing with regression detection
- Team collaboration workflow
- Predictive intelligence (know when patterns will break)

**Key insight:** v2 transforms signatures from **disposable byte patterns** into **valuable, versioned assets** with institutional knowledge.

## v2 Roadmap

### v2.0 (Current)
- ✅ Explainability (Phase 1)
- ✅ Signature Database (Phase 2)
- ✅ Automated Testing (Phase 3)
- ✅ Temporal Analysis (Phase 4)
- ✅ Signature Families (Phase 5)
- ✅ Structural Anchors (Phase 6, experimental)
- ⚠️ SDK (Phase 7, design complete, implementation pending)

### v2.1 (Planned)
- Full SDK implementation
- Enhanced temporal prediction models
- Performance optimizations
- Additional CI/CD integrations

### v2.2+ (Future)
- Multi-architecture support (ARM64, x86-32)
- Advanced structural analysis (CFG reconstruction)
- Cloud-based signature repository (if demand exists)
- Web dashboard for signature browsing (optional)

## Contributing & Feedback

Found a bug? Have a feature request? See something that could be improved?

- File issues on GitHub
- Check existing documentation (V2_FINAL_SUMMARY.md, AOBMASTER_V2_VISION.md)
- Read implementation summaries (PHASE_*_SUMMARY.md files)

## License

Proprietary - see project license file

---

**AoBMaster v2.0** - From byte patterns to signature intelligence.
