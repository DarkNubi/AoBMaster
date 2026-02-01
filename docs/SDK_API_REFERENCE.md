# AoBMaster SDK API Reference

**Version**: 2.1  
**Status**: Production Ready

## Overview

The AoBMaster SDK provides programmatic access to signature generation, testing, and analysis without subprocess calls. All SDK classes call the same battle-tested codepaths as the CLI.

## Quick Start

```python
from aobmaster.sdk import Synthesizer, SignatureDatabase

# Generate a signature
synth = Synthesizer("game.exe")
result = synth.generate(anchor_rva="0x14001A000")

# Save to database
if result.ok:
    db = SignatureDatabase("signatures.db")
    db.init()
    
    top = result.get_top_candidate()
    db.save_signature(
        signature_id="player_health",
        name="Player Health Pointer",
        pattern=top["aob"],
        anchor_rva="0x14001A000"
    )
```

## Core Classes

### Synthesizer

Generate AoB signatures from binaries.

#### Constructor

```python
Synthesizer(binary_path: Union[str, Path])
```

**Parameters:**
- `binary_path`: Path to PE binary file

**Raises:**
- `FileNotFoundError`: If binary doesn't exist
- `AoBMasterError`: If binary is invalid

**Example:**
```python
synth = Synthesizer("C:/Games/game.exe")
```

#### Methods

##### `generate()`

Generate signature candidates for an anchor point.

```python
def generate(
    self,
    anchor_rva: Optional[str] = None,
    anchor_fo: Optional[str] = None,
    anchor_va: Optional[str] = None,
    version_binaries: Optional[List[Path]] = None,
    profile: str = "balanced",
    explain: bool = False,
    require_unique: bool = True
) -> SynthesisResult
```

**Parameters:**
- `anchor_rva` (str, optional): Anchor RVA in hex (e.g., "0x1000")
- `anchor_fo` (str, optional): Anchor file offset in hex
- `anchor_va` (str, optional): Anchor virtual address in hex
- `version_binaries` (List[Path], optional): Additional binary versions for multi-version synthesis
- `profile` (str): Synthesis profile - "specific", "balanced", or "generic" (default: "balanced")
- `explain` (bool): Enable explainability mode (default: False)
- `require_unique` (bool): Require unique match (default: True)

**Returns:**
- `SynthesisResult`: Result object with candidates, warnings, errors

**Example:**
```python
# Basic usage
result = synth.generate(anchor_rva="0x1000")

# Multi-version synthesis
result = synth.generate(
    anchor_rva="0x1000",
    version_binaries=[Path("game_v1.1.exe"), Path("game_v1.2.exe")],
    profile="specific"
)

# With explainability
result = synth.generate(anchor_rva="0x1000", explain=True)
print(result.trace)
```

### SynthesisResult

Result from signature generation.

#### Attributes

```python
@dataclass
class SynthesisResult:
    ok: bool                      # True if synthesis succeeded
    version: str                  # AoBMaster version
    candidates: List[Dict]        # List of candidate patterns
    alignment: List[Dict]         # Multi-version alignment data
    warnings: List[str]           # Non-fatal warnings
    errors: List[str]             # Error messages
    trace: Optional[Dict]         # Explainability trace (if explain=True)
```

#### Methods

##### `get_top_candidate()`

Get the highest-scoring valid candidate.

```python
def get_top_candidate(self) -> Optional[Dict[str, Any]]
```

**Returns:**
- `Dict` with candidate data, or `None` if no valid candidates

**Example:**
```python
result = synth.generate(anchor_rva="0x1000")
if result.ok:
    top = result.get_top_candidate()
    if top:
        print(f"Pattern: {top['aob']}")
        print(f"Score: {top['score']['score']:.2f}")
```

##### `get_top_pattern()`

Get the AoB pattern string of the top candidate.

```python
def get_top_pattern(self) -> Optional[str]
```

**Returns:**
- Pattern string (e.g., "48 8B 05 ?? ?? ?? ??"), or `None`

**Example:**
```python
pattern = result.get_top_pattern()
if pattern:
    print(f"Use this pattern: {pattern}")
```

##### `to_dict()`

Convert result to dictionary (JSON-serializable).

```python
def to_dict(self) -> Dict[str, Any]
```

**Returns:**
- Dictionary representation of result

**Example:**
```python
import json
result_dict = result.to_dict()
with open("result.json", "w") as f:
    json.dump(result_dict, f, indent=2)
```

### SignatureDatabase

Interface to signature database.

#### Constructor

```python
SignatureDatabase(db_path: Union[str, Path])
```

**Parameters:**
- `db_path`: Path to SQLite database file

**Example:**
```python
db = SignatureDatabase("signatures.db")
```

#### Methods

##### `init()`

Initialize database schema.

```python
def init(self) -> None
```

Safe to call multiple times (idempotent). Applies migrations automatically.

**Example:**
```python
db = SignatureDatabase("new_db.db")
db.init()  # Creates schema
```

##### `save_signature()`

Save signature to database.

```python
def save_signature(
    self,
    signature_id: str,
    name: str,
    pattern: str,
    anchor_rva: Optional[str] = None,
    binary_hash: Optional[str] = None,
    author: Optional[str] = None,
    version_range: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    parent_id: Optional[str] = None
) -> None
```

**Parameters:**
- `signature_id` (str): Unique identifier
- `name` (str): Human-readable name
- `pattern` (str): AoB pattern string
- `anchor_rva` (str, optional): Anchor RVA in hex
- `binary_hash` (str, optional): SHA256 of binary
- `author` (str, optional): Author name
- `version_range` (str, optional): Compatible version range (e.g., "1.0-1.5")
- `metadata` (Dict, optional): Additional metadata (JSON-serializable)
- `parent_id` (str, optional): Parent signature ID (for families)

**Example:**
```python
db.save_signature(
    signature_id="player_health_v1",
    name="Player Health Pointer",
    pattern="48 8B 05 ?? ?? ?? ?? 85 C0",
    anchor_rva="0x1000",
    version_range="1.0-1.5",
    metadata={"description": "Points to player health value"}
)
```

##### `query_signature()`

Query signature by ID.

```python
def query_signature(self, signature_id: str) -> Optional[Dict[str, Any]]
```

**Returns:**
- Signature dictionary, or `None` if not found

**Example:**
```python
sig = db.query_signature("player_health_v1")
if sig:
    print(f"Pattern: {sig['pattern']}")
```

##### `list_signatures()`

List all signatures.

```python
def list_signatures(self, filter_text: Optional[str] = None) -> List[Dict[str, Any]]
```

**Parameters:**
- `filter_text` (str, optional): Filter by name/ID substring

**Returns:**
- List of signature dictionaries

**Example:**
```python
# List all
all_sigs = db.list_signatures()

# Filter
health_sigs = db.list_signatures(filter_text="health")
```

##### `export_signatures()` / `import_signatures()`

Export/import signatures to/from JSON.

```python
def export_signatures(self, output_path: Union[str, Path]) -> None
def import_signatures(self, input_path: Union[str, Path]) -> None
```

**Example:**
```python
# Backup
db.export_signatures("backup.json")

# Restore
db2 = SignatureDatabase("restored.db")
db2.init()
db2.import_signatures("backup.json")
```

### SignatureTester

Test signatures against binaries.

#### Constructor

```python
SignatureTester(db_path: Union[str, Path])
```

#### Methods

##### `test_signature()`

Test single signature against single binary.

```python
def test_signature(
    self,
    signature_id: str,
    binary_path: Union[str, Path],
    record: bool = False
) -> Dict[str, Any]
```

**Parameters:**
- `signature_id`: Signature to test
- `binary_path`: Binary to test against
- `record`: Record result to database (default: False)

**Returns:**
- Dict with `passed`, `match_count`, `failure_reason`

**Example:**
```python
tester = SignatureTester("signatures.db")
result = tester.test_signature(
    "player_health_v1",
    "game_v1.2.exe",
    record=True
)

if result["passed"]:
    print(f"✓ Matched {result['match_count']} time(s)")
else:
    print(f"✗ Failed: {result['failure_reason']}")
```

##### `test_all()`

Test signature(s) against corpus.

```python
def test_all(
    self,
    corpus_pattern: str,
    signature_id: Optional[str] = None,
    parallel: int = 1,
    record: bool = False
) -> Dict[str, Any]
```

**Parameters:**
- `corpus_pattern`: Glob pattern for binaries
- `signature_id`: Test specific signature, or None for all
- `parallel`: Number of parallel workers (default: 1)
- `record`: Record results (default: False)

**Returns:**
- Dict with `summary` and `results`

**Example:**
```python
results = tester.test_all(
    corpus_pattern="binaries/*.exe",
    parallel=4,
    record=True
)

print(f"Passed: {results['summary']['passed']}/{results['summary']['total']}")
```

### TemporalAnalyzer

Analyze signature stability over time.

#### Constructor

```python
TemporalAnalyzer(db_path: Union[str, Path])
```

#### Methods

##### `analyze_signature()`

Perform temporal analysis on signature.

```python
def analyze_signature(self, signature_id: str) -> Dict[str, Any]
```

**Returns:**
- Analysis dict with:
  - `pass_rate`: Historical success rate
  - `drift_analysis`: RVA drift trends
  - `confidence_interval`: Confidence bounds
  - `stability_assessment`: "stable" | "fragile" | "unknown"
  - `recommendation`: Actionable advice

**Example:**
```python
analyzer = TemporalAnalyzer("signatures.db")
analysis = analyzer.analyze_signature("player_health_v1")

print(f"Pass Rate: {analysis['pass_rate']:.1%}")
print(f"Assessment: {analysis['stability_assessment']}")
print(f"Recommendation: {analysis['recommendation']}")
```

##### `analyze_all()`

Analyze all signatures.

```python
def analyze_all(self) -> List[Dict[str, Any]]
```

**Returns:**
- List of analysis dicts (one per signature)

**Example:**
```python
analyses = analyzer.analyze_all()

for analysis in analyses:
    sig_id = analysis['signature_id']
    assessment = analysis['stability_assessment']
    print(f"{sig_id}: {assessment}")
```

## Configuration

### SynthesisConfig

Configuration dataclass for synthesis (advanced users).

```python
@dataclass
class SynthesisConfig:
    base_binary: Path
    anchor_rva: Optional[str] = None
    anchor_fo: Optional[str] = None
    anchor_va: Optional[str] = None
    version_binaries: List[Path] = field(default_factory=list)
    profile: str = "balanced"
    context_before: int = 8
    context_after: int = 8
    require_unique: bool = True
    explain: bool = False
```

**Example:**
```python
from aobmaster.sdk import SynthesisConfig

config = SynthesisConfig(
    base_binary=Path("game.exe"),
    anchor_rva="0x1000",
    profile="specific",
    context_before=16,
    context_after=16
)
```

## Error Handling

All SDK methods use exceptions for errors:

```python
from aobmaster.errors import AoBMasterError

try:
    synth = Synthesizer("game.exe")
    result = synth.generate(anchor_rva="0x1000")
except FileNotFoundError:
    print("Binary not found")
except AoBMasterError as e:
    print(f"Error: {e.message}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Best Practices

### 1. Always Check `result.ok`

```python
result = synth.generate(anchor_rva="0x1000")
if not result.ok:
    print(f"Errors: {result.errors}")
    return

# Safe to use result
top = result.get_top_candidate()
```

### 2. Use Context Managers for Resources

```python
# Database connections are managed internally
db = SignatureDatabase("sig.db")
db.init()
# No need to close - handled automatically
```

### 3. Record Test Results for Temporal Analysis

```python
# Enable recording to build historical data
tester.test_signature("sig1", "game.exe", record=True)

# Later, analyze trends
analyzer = TemporalAnalyzer("sig.db")
analysis = analyzer.analyze_signature("sig1")
```

### 4. Use Multi-Version Synthesis

```python
versions = [
    Path("game_v1.0.exe"),
    Path("game_v1.1.exe"),
    Path("game_v1.2.exe"),
]

result = synth.generate(
    anchor_rva="0x1000",
    version_binaries=versions,
    profile="balanced"
)
```

### 5. Handle Optional Returns

```python
top = result.get_top_candidate()
if top is None:
    print("No valid candidates found")
    return

pattern = top["aob"]
```

## Performance Considerations

### Pattern Matching Optimization

The SDK automatically uses NumPy acceleration if available:

```python
from aobmaster.matcher_optimized import get_performance_info

info = get_performance_info()
print(f"Optimization: {info['optimization_level']}")
# Output: "numpy" or "standard"
```

To install NumPy for better performance:
```bash
pip install numpy
```

### Parallel Testing

Use parallel workers for large test corpora:

```python
# Sequential (slow for large corpus)
results = tester.test_all("binaries/*.exe", parallel=1)

# Parallel (4x faster with 4 cores)
results = tester.test_all("binaries/*.exe", parallel=4)
```

## Migration from CLI

### Before (CLI)

```bash
# Generate signature
aobmaster synth --input game.exe --anchor-rva 0x1000 > result.json

# Save to database
aobmaster db save --db sig.db --id player_health --name "Player Health" --pattern "48 8B..."

# Test
aobmaster test --db sig.db --corpus "binaries/*.exe"
```

### After (SDK)

```python
from aobmaster.sdk import Synthesizer, SignatureDatabase, SignatureTester

# Generate
synth = Synthesizer("game.exe")
result = synth.generate(anchor_rva="0x1000")

# Save
db = SignatureDatabase("sig.db")
db.init()
top = result.get_top_candidate()
db.save_signature(
    signature_id="player_health",
    name="Player Health",
    pattern=top["aob"]
)

# Test
tester = SignatureTester("sig.db")
results = tester.test_all("binaries/*.exe")
```

## Complete Example

```python
#!/usr/bin/env python3
"""
Complete workflow: Generate → Save → Test → Analyze
"""

from pathlib import Path
from aobmaster.sdk import (
    Synthesizer,
    SignatureDatabase,
    SignatureTester,
    TemporalAnalyzer
)

def main():
    # Configuration
    binary = Path("game.exe")
    db_path = Path("signatures.db")
    anchor = "0x14001A000"
    
    # 1. Generate signature
    print("Generating signature...")
    synth = Synthesizer(binary)
    result = synth.generate(anchor_rva=anchor, profile="balanced")
    
    if not result.ok:
        print(f"Failed: {result.errors}")
        return
    
    top = result.get_top_candidate()
    if not top:
        print("No valid candidates")
        return
    
    print(f"✓ Generated pattern: {top['aob']}")
    print(f"  Score: {top['score']['score']:.3f}")
    
    # 2. Save to database
    print("\nSaving to database...")
    db = SignatureDatabase(db_path)
    db.init()
    
    db.save_signature(
        signature_id="player_health",
        name="Player Health Pointer",
        pattern=top["aob"],
        anchor_rva=anchor,
        version_range="1.0+",
        metadata={"description": "Tracks player HP"}
    )
    print("✓ Saved")
    
    # 3. Test against corpus
    print("\nTesting against corpus...")
    tester = SignatureTester(db_path)
    test_results = tester.test_all(
        corpus_pattern="binaries/game_v*.exe",
        signature_id="player_health",
        parallel=4,
        record=True  # Record for temporal analysis
    )
    
    summary = test_results["summary"]
    print(f"✓ Tested: {summary['passed']}/{summary['total']} passed")
    
    # 4. Analyze stability
    print("\nAnalyzing stability...")
    analyzer = TemporalAnalyzer(db_path)
    analysis = analyzer.analyze_signature("player_health")
    
    print(f"  Pass Rate: {analysis['pass_rate']:.1%}")
    print(f"  Assessment: {analysis['stability_assessment']}")
    print(f"  Recommendation: {analysis['recommendation']}")
    
    print("\n✓ Complete!")

if __name__ == "__main__":
    main()
```

## See Also

- [Migration Guide](MIGRATION_GUIDE.md)
- [Usage Examples](examples/)
- [CI/CD Integration](examples/ci/README.md)
- [v2.1 Implementation Plan](V2.1_IMPLEMENTATION_PLAN.md)
