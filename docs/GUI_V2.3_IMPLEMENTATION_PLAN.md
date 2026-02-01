# AoBMaster v2.3 GUI — Production Implementation Plan

**Version**: 2.3  
**Status**: Design & Planning Phase  
**Date**: 2026-02-01  
**Classification**: Career-Critical Tooling — Not a Demo

---

## Executive Summary

This document outlines a production-grade implementation plan for AoBMaster v2.3 GUI. The GUI is designed as a **thin, explicit client** of the existing AoBMaster SDK (v2.1+), preserving all core guarantees: determinism, reproducibility, explainability, CLI parity, and CI/CD compatibility.

**Key Principle**: The GUI introduces **zero new logic**. It is a visualization and interaction layer over the battle-tested SDK.

**Assessment**: This GUI can be safely shipped as v2.3 **if and only if** the architectural constraints defined in this document are strictly enforced.

---

## 1. Codebase Reconnaissance

### 1.1 Component Map

```
┌─────────────────────────────────────────────────────┐
│                    GUI Layer (v2.3)                  │
│              [Thin Client - Zero Logic]              │
└─────────────────┬───────────────────────────────────┘
                  │
                  │ SDK Calls Only
                  │ (No Direct Module Access)
                  ▼
┌─────────────────────────────────────────────────────┐
│                 SDK Layer (v2.1+)                    │
│   Synthesizer │ SignatureDatabase │ SignatureTester  │
│              TemporalAnalyzer                        │
└─────────────────┬───────────────────────────────────┘
                  │
                  │ Internal Calls
                  ▼
┌─────────────────────────────────────────────────────┐
│                   Core Modules                       │
│  synth │ align │ candidates │ matcher │ score │      │
│  disasm │ trace │ database │ temporal │ etc.         │
└─────────────────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│                    CLI Layer                         │
│          [Thin Wrapper Over SDK]                     │
└─────────────────────────────────────────────────────┘
```

### 1.2 SDK Surface Area (GUI-Accessible)

The GUI **MUST ONLY** call these SDK classes and methods:

#### **Synthesizer** (aobmaster/sdk.py:109-198)
- `__init__(base_binary: Path)`
- `generate(anchor_rva/fo/va, version_binaries, profile, explain, **kwargs) -> SynthesisResult`

**Configuration Parameters** (all SDK-controlled):
- `anchor_rva`, `anchor_fo`, `anchor_va` (mutually exclusive)
- `version_binaries`: List[Path]
- `profile`: "minimal"|"default"|"strict"|"balanced"|"aggressive"|"stack-only"|"global-only"|"memory-heavy"
- `align_mode`: "bytespan"|"anchor-rva"
- `seed_bytes`: int (default: 32)
- `seed_scan`: "section"|"module"
- `seed_allow_multi`: bool
- `context_before`, `context_after`: int
- `max_context_insns`: int
- `context_variations`: bool
- `min_insns`, `max_insns`: int
- `require_unique`, `require_present_all`: bool
- `scan_range`: "section"|"module"|None
- `explain`: bool (v2 feature)
- `anchor_mode`: "byte-offset"|"structural" (HIGH RISK)
- `anchor_shift`: int (0 = off)

**Returns**: `SynthesisResult` with:
- `ok`: bool
- `candidates`: List[Dict]
- `warnings`, `errors`: List[Dict]
- `trace`: Optional[Dict] (if explain=True)
- `get_top_candidate()`: Optional[Dict]
- `get_top_pattern()`: Optional[str]

#### **SignatureDatabase** (aobmaster/sdk.py:201-312)
- `__init__(db_path: Path)`
- `init()`: Initialize schema
- `save_signature(signature_id, name, pattern, **metadata)`
- `query_signature(signature_id) -> Optional[Dict]`
- `list_signatures(filter_text=None) -> List[Dict]`
- `export_signatures(output_path)`
- `import_signatures(input_path)`
- `deprecate_signature(signature_id, reason)`

#### **SignatureTester** (aobmaster/sdk.py:315-405)
- `__init__(db_path: Path)`
- `test_signature(signature_id, binary_path, record=False) -> Dict`
- `test_all(corpus_pattern, signature_id=None, parallel=1, record=False) -> Dict`

#### **TemporalAnalyzer** (aobmaster/sdk.py:408-456)
- `__init__(db_path: Path)`
- `analyze_signature(signature_id) -> Dict`
- `analyze_all() -> List[Dict]`

### 1.3 CLI Command → SDK Mapping

| CLI Command | SDK Method | GUI Action |
|-------------|------------|------------|
| `synth` | `Synthesizer.generate()` | "Generate Signature" button |
| `scan` | **NOT SDK** (uses `matcher.py` directly) | **GUI-FORBIDDEN** (direct module call) |
| `info` | **NOT SDK** (uses `pe.py` directly) | Read-only: display via SDK only |
| `db init` | `SignatureDatabase.init()` | "New Database" action |
| `db save` | `SignatureDatabase.save_signature()` | "Save Signature" dialog |
| `db list` | `SignatureDatabase.list_signatures()` | Signature browser view |
| `db query` | `SignatureDatabase.query_signature()` | Detail view |
| `db export/import` | `SignatureDatabase.export/import_signatures()` | File menu actions |
| `test` | `SignatureTester.test_signature/test_all()` | "Run Tests" action |
| `analyze` | `TemporalAnalyzer.analyze_signature/analyze_all()` | "Analyze Stability" view |
| `diagnose` | **NOT SDK** (database query) | Read-only: query via SDK |
| `smart` | **NOT SDK** (direct smart_analyzer.py call) | **GUI-FORBIDDEN** |

### 1.4 GUI-Safe vs GUI-Forbidden Operations

#### ✅ **GUI-SAFE** (SDK-Backed, Explicit)
- Signature generation via `Synthesizer.generate()` with **all parameters explicit**
- Database management (init, save, query, list, export, import)
- Signature testing (single or batch)
- Temporal analysis (read-only)
- Result visualization (candidates, scores, traces)
- Configuration management (save/load synthesis configs)

#### ❌ **GUI-FORBIDDEN** (No SDK Interface or Dangerous)
- **Pattern scanning** (`aobmaster scan`) — No SDK wrapper, direct module call
- **Smart anchor suggestion** (`aobmaster smart`) — No SDK wrapper
- **PE metadata inspection** (`aobmaster info`) — No SDK wrapper
- **Free-form pattern editing** — Would bypass synthesis validation
- **Direct database SQL queries** — Would break schema integrity
- **Batch mutation without confirmation** — Dangerous, non-replayable
- **Hidden defaults** — All parameters must be explicit or visibly defaulted
- **GUI-invented wildcarding** — SDK profiles only

### 1.5 Configuration Objects (Read-Only)

The GUI **MUST NOT** construct or modify these directly:

- **`SynthesisConfig`** (sdk.py:20-59): Dataclass with 20+ fields
  - GUI displays these as form fields
  - GUI passes them to `Synthesizer.generate()` verbatim
  - GUI never modifies them after SDK returns

- **`SignatureRecord`** (database.py:22-52): Database schema
  - GUI queries via `SignatureDatabase.query_signature()`
  - GUI never writes to database except via `save_signature()`

- **`ScoreBreakdown`** (score.py:8-26): Scoring components
  - GUI displays these read-only (pie chart, table)
  - GUI never recalculates scores

- **Trace Events** (trace.py:15-26): Explainability log
  - GUI displays as timeline or tree view
  - GUI never generates or modifies trace events

### 1.6 Determinism & Reproducibility Mechanisms

The GUI **MUST** preserve these guarantees:

1. **No Randomness**: GUI introduces zero non-deterministic behavior
2. **Parameter Transparency**: All synthesis parameters visible in GUI
3. **Configuration Export**: Any GUI workflow must be exportable as:
   - CLI command (exact equivalent)
   - JSON config file (for SDK replay)
4. **Audit Trail**: GUI logs all SDK calls with timestamps
5. **Reproducibility Test**: Given same inputs, GUI produces same outputs as CLI

**Validation Rule**: For any GUI action, there must exist an equivalent CLI command that produces identical results.

---

## 2. GUI Architectural Model

### 2.1 Technology Choice

**Decision**: **Desktop-first Hybrid (Electron or Tauri)**

**Justification**:

| Technology | Pros | Cons | Verdict |
|------------|------|------|---------|
| **Pure Web (Browser)** | No install, cross-platform | Security (no file system), SDK integration complex | ❌ Rejected |
| **Qt/PyQt** | Native, Python integration | Large dependency, limited web tech | ⚠️ Fallback |
| **Electron** | Web tech, mature, large ecosystem | Heavy (~150MB), Node.js overhead | ✅ **Recommended** |
| **Tauri** | Lightweight (~10MB), Rust security | Less mature, smaller ecosystem | ✅ **Alternative** |

**Recommendation**: **Electron** (primary) with **Tauri** as future optimization.

**Why Electron**:
1. **SDK Integration**: Python SDK runs as subprocess, communicates via stdin/stdout (JSON-RPC)
2. **Risk Minimization**: No direct file access from web context—all SDK calls proxied
3. **Ecosystem**: Mature tooling (React, Vue, testing frameworks)
4. **Separation**: Web frontend **cannot** access aobmaster modules directly
5. **Security**: Inter-Process Communication (IPC) enforces API boundaries

### 2.2 Process Model

```
┌─────────────────────────────────────────────────────┐
│            Electron Main Process (Node.js)           │
│              [IPC Gateway - No Logic]                │
│                                                       │
│  ┌──────────────────────────────────────────────┐  │
│  │  SDK Worker (Python subprocess)              │  │
│  │  - Runs aobmaster SDK                        │  │
│  │  - Accepts JSON-RPC commands                 │  │
│  │  - Returns JSON results                      │  │
│  │  - Stateless (restart safe)                  │  │
│  └──────────────────────────────────────────────┘  │
└───────────────────┬─────────────────────────────────┘
                    │ IPC
                    │ (JSON messages only)
                    ▼
┌─────────────────────────────────────────────────────┐
│         Electron Renderer Process (Web UI)           │
│              [Pure Presentation Layer]               │
│                                                       │
│  React/Vue + TypeScript                              │
│  - Forms (synthesis config)                          │
│  - Tables (signature list, test results)             │
│  - Charts (scores, temporal trends)                  │
│  - Trees (explainability traces)                     │
│  - NO business logic                                 │
└─────────────────────────────────────────────────────┘
```

**Critical Properties**:
1. **No Direct File Access**: Renderer process cannot touch aobmaster code
2. **IPC Validation**: Main process validates all IPC messages against schema
3. **SDK Lifecycle**: Python SDK worker is disposable (crash-safe)
4. **Stateless UI**: All state comes from SDK (no GUI-side caching)
5. **Audit Logging**: All IPC messages logged to file for replay

### 2.3 SDK Invocation Mechanism

**JSON-RPC over stdin/stdout** (CLI mode):

```json
// Request (GUI → SDK worker)
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "synthesizer.generate",
  "params": {
    "base_binary": "C:/game.exe",
    "anchor_rva": "0x14001A000",
    "profile": "balanced",
    "explain": true
  }
}

// Response (SDK worker → GUI)
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "ok": true,
    "candidates": [...],
    "trace": {...}
  }
}

// Error
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32000,
    "message": "Anchor not within any section"
  }
}
```

**SDK Worker Implementation** (Python script):
```python
# aobmaster/gui_worker.py (NEW)
import sys
import json
from pathlib import Path
from .sdk import Synthesizer, SignatureDatabase, SignatureTester, TemporalAnalyzer

def handle_request(req):
    method = req["method"]
    params = req["params"]
    
    if method == "synthesizer.generate":
        synth = Synthesizer(params["base_binary"])
        result = synth.generate(**params)
        return result.to_dict()
    
    elif method == "database.list_signatures":
        db = SignatureDatabase(params["db_path"])
        return db.list_signatures(params.get("filter_text"))
    
    # ... other methods
    
    else:
        raise ValueError(f"Unknown method: {method}")

def main():
    for line in sys.stdin:
        req = json.loads(line)
        try:
            result = handle_request(req)
            response = {"jsonrpc": "2.0", "id": req["id"], "result": result}
        except Exception as e:
            response = {"jsonrpc": "2.0", "id": req["id"], "error": {"code": -32000, "message": str(e)}}
        
        print(json.dumps(response))
        sys.stdout.flush()

if __name__ == "__main__":
    main()
```

**Benefits**:
- **Enforces SDK-only access**: GUI cannot call internal modules
- **Language-agnostic**: TypeScript frontend, Python backend
- **Testable**: JSON-RPC can be mocked/replayed
- **Crash isolation**: SDK worker crash doesn't kill GUI
- **CLI parity**: Worker uses same SDK as CLI

---

## 3. GUI–SDK Contract (NON-NEGOTIABLE)

### 3.1 Allowed Methods (Whitelist)

The GUI **MAY ONLY** call these SDK methods:

```typescript
// TypeScript SDK interface (enforced by IPC gateway)

interface Synthesizer {
  generate(params: SynthesisParams): Promise<SynthesisResult>;
}

interface SignatureDatabase {
  init(): Promise<void>;
  save_signature(params: SaveSignatureParams): Promise<void>;
  query_signature(signature_id: string): Promise<SignatureRecord | null>;
  list_signatures(filter_text?: string): Promise<SignatureRecord[]>;
  export_signatures(output_path: string): Promise<void>;
  import_signatures(input_path: string): Promise<void>;
  deprecate_signature(signature_id: string, reason: string): Promise<void>;
}

interface SignatureTester {
  test_signature(params: TestSignatureParams): Promise<TestResult>;
  test_all(params: TestAllParams): Promise<TestSummary>;
}

interface TemporalAnalyzer {
  analyze_signature(signature_id: string): Promise<TemporalAnalysis>;
  analyze_all(): Promise<TemporalAnalysis[]>;
}
```

**Any method not in this list is FORBIDDEN.**

### 3.2 Parameter Rules

1. **Explicit Over Implicit**:
   - GUI forms display **all** parameters with their current values
   - No hidden defaults (e.g., "smart" profile selection)
   - User sees exactly what SDK will receive

2. **Validation**:
   - Frontend validates types (string, int, bool, Path)
   - Backend (IPC gateway) validates against schema
   - SDK performs final validation (canonical)

3. **Defaults**:
   - GUI shows SDK defaults as placeholder text
   - User can override or accept defaults
   - GUI never invents new defaults

4. **Mutually Exclusive Parameters**:
   - `anchor_rva` XOR `anchor_fo` XOR `anchor_va` — enforced by radio buttons
   - GUI prevents impossible combinations

### 3.3 Error Handling

**Errors propagate to GUI verbatim**:

```typescript
try {
  const result = await sdk.synthesizer.generate(params);
  if (!result.ok) {
    // Display errors/warnings from SDK
    showErrors(result.errors);
    showWarnings(result.warnings);
  }
} catch (error) {
  // IPC failure or SDK crash
  showFatalError("SDK communication failed", error);
}
```

**GUI MUST NOT**:
- Suppress errors
- Retry without user consent
- Modify error messages
- Implement "smart" error recovery

### 3.4 Confidence & Uncertainty Display

**Score Breakdown** (from `SynthesisResult.candidates[].score`):
- GUI displays all 5 components: U (35%), P (25%), S (20%), L (10%), A (10%)
- GUI shows composite score (0.0-1.0) with color coding:
  - 🟢 Green: ≥0.80 (high confidence)
  - 🟡 Yellow: 0.50-0.79 (medium confidence)
  - 🔴 Red: <0.50 (low confidence)

**Confidence Metric** (from `SynthesisResult.candidates[].confidence`):
- Display as percentage (e.g., 87%)
- Show factors: `num_versions`, `max_drift_rva`, warnings

**Fallbacks** (from `SynthesisResult.warnings`):
- If `anchor_shift` triggered fallback, highlight this
- Show original anchor vs fallback anchor
- Warning badge on result

**Experimental Features**:
- If `anchor_mode="structural"`, show warning badge: "⚠️ Structural (Experimental)"
- Display confidence interval if available

### 3.5 Replayability Guarantees

**CLI Export**: Every GUI action generates equivalent CLI command:

```typescript
function exportAsCLI(params: SynthesisParams): string {
  const cmd = ["aobmaster", "synth"];
  cmd.push("--base", params.base_binary);
  if (params.anchor_rva) cmd.push("--anchor-rva", params.anchor_rva);
  if (params.profile !== "default") cmd.push("--profile", params.profile);
  if (params.explain) cmd.push("--explain");
  // ... all other parameters
  return cmd.join(" ");
}
```

**JSON Config Export**:
```json
{
  "config": {
    "base_binary": "game.exe",
    "anchor_rva": "0x1000",
    "profile": "balanced",
    "explain": true
  },
  "timestamp": "2026-02-01T12:00:00Z",
  "gui_version": "2.3.0",
  "sdk_version": "2.1.0"
}
```

**Audit Log** (`~/.aobmaster/gui_audit.log`):
```
[2026-02-01 12:00:00] SYNTHESIZER.GENERATE base=game.exe anchor_rva=0x1000 profile=balanced
[2026-02-01 12:00:15] DATABASE.SAVE_SIGNATURE id=sig_001 name="player_health"
[2026-02-01 12:01:00] TESTER.TEST_ALL corpus=*.exe parallel=4
```

---

## 4. Feature Scope Definition (Hard Boundaries)

### 4.1 Allowed GUI Features

#### **Signature Browsing** (Read-Only)
- ✅ List signatures from database (`SignatureDatabase.list_signatures()`)
- ✅ Filter by name, ID, status, date
- ✅ Sort by creation date, pass rate, confidence
- ✅ View signature details (pattern, metadata, lineage)
- ✅ Export selected signatures to JSON

#### **Health & Confidence Visualization**
- ✅ Score breakdown charts (pie chart, bar chart)
- ✅ Confidence meter (0-100%)
- ✅ Pass rate history (line chart over time)
- ✅ Stability assessment badge (stable / fragile / unknown)
- ✅ Drift analysis graph (RVA delta over versions)

#### **Explainability Inspection**
- ✅ Trace timeline (if `explain=True`)
- ✅ Event tree (ANCHOR_RESOLUTION → ALIGNMENT → WILDCARDING → SCORING)
- ✅ Byte-level annotations (why each byte is fixed or wildcarded)
- ✅ Alignment visualization (seed match locations)
- ✅ Scoring component breakdown

#### **Test History Timelines**
- ✅ Test result history (chronological)
- ✅ Per-binary pass/fail status
- ✅ Failure reasons (not unique, not present, pattern changed)
- ✅ Temporal trends (stability over time)

#### **Explicit SDK-Backed Actions** (With Confirmation)
- ✅ Generate signature (opens form with all parameters)
- ✅ Save signature to database (confirmation dialog)
- ✅ Run test suite (shows corpus pattern, parallel config)
- ✅ Export database (file picker)
- ✅ Import signatures (file picker + merge strategy)
- ✅ Deprecate signature (reason required)

#### **Configuration Management**
- ✅ Save synthesis config as preset (JSON file)
- ✅ Load synthesis config from preset
- ✅ "Copy as CLI command" button (generates exact CLI equivalent)
- ✅ "Copy as SDK code" button (generates Python SDK snippet)

### 4.2 Forbidden GUI Features

#### **Pattern Editing** ❌
- **Forbidden**: Free-form AoB pattern text editor
- **Reason**: Patterns must come from SDK synthesis (validation guarantees)
- **Alternative**: Re-generate signature with different parameters

#### **Heuristic Auto-Fix** ❌
- **Forbidden**: "Fix failing signature" button that modifies pattern
- **Reason**: No GUI-invented logic; user must understand why it failed
- **Alternative**: Show failure reason + suggest CLI command to regenerate

#### **GUI-Only Batch Mutation** ❌
- **Forbidden**: "Apply aggressive profile to all failing signatures"
- **Reason**: Batch operations must be explicit, scriptable
- **Alternative**: Export failing IDs, user writes script, imports results

#### **Hidden Regeneration** ❌
- **Forbidden**: Auto-regenerate signature on test failure
- **Reason**: Non-deterministic, hides failures
- **Alternative**: User manually re-synthesizes after review

#### **Smart Anchor Suggestions** ❌
- **Forbidden**: GUI implementing `aobmaster smart` logic
- **Reason**: No SDK wrapper exists; would duplicate code
- **Alternative**: Future SDK integration or external CLI call

#### **Pattern Scanning** ❌
- **Forbidden**: GUI implementing `aobmaster scan` logic
- **Reason**: No SDK wrapper exists
- **Alternative**: Use CLI for scanning, GUI for signature management

#### **Direct Database Manipulation** ❌
- **Forbidden**: SQL query UI, raw record editing
- **Reason**: Schema integrity, audit trail
- **Alternative**: Use SDK methods only (`save_signature`, `deprecate_signature`)

---

## 5. UX Flow Design (Power-User Safe)

### 5.1 Flow: Viewing a Signature

```
1. [Signature List View]
   - Table: ID | Name | Status | Pass Rate | Last Tested
   - Filter bar (text search)
   - Sort dropdown (by date, pass rate, name)
   
   ↓ User clicks signature row
   
2. [Signature Detail View]
   - Header: ID, Name, Status, Created Date, Author
   - Pattern (monospace font, syntax highlighted)
   - Metadata: anchor_rva, version_range, binary_hash
   - Score breakdown (pie chart + table)
   - Confidence meter
   - Lineage tree (if parent_id exists)
   - Test history timeline
   - Actions: [Test] [Deprecate] [Export]
   
   ↓ User clicks "Show CLI Command"
   
3. [CLI Export Dialog]
   - Displays: `aobmaster db query --db sigs.db --id sig_001`
   - Copy button
```

**SDK Calls**:
- Step 1: `database.list_signatures(filter_text)`
- Step 2: `database.query_signature(signature_id)`
- Step 3: None (GUI generates CLI string locally)

### 5.2 Flow: Running Synthesis via GUI

```
1. [New Signature Form]
   - Section: Anchor
     - Binary path picker
     - Radio buttons: RVA | File Offset | Virtual Address
     - Text input (hex) with validation
   
   - Section: Version Alignment (collapsible)
     - Version binaries (file list, add/remove)
     - Align mode: Bytespan | Anchor-RVA
     - Seed bytes: 32 (slider)
     - Seed scan: Section | Module
   
   - Section: Wildcarding
     - Profile dropdown (minimal, default, balanced, aggressive, etc.)
     - Info icon → shows profile descriptions
   
   - Section: Context Window (collapsible)
     - Context before: 8 (number input)
     - Context after: 8 (number input)
     - Max context insns: 32
     - Context variations: Off | On
   
   - Section: Advanced (collapsible)
     - Min/max insns: 6-14 (range slider)
     - Require unique: ✓
     - Require present all: ✓
     - Scan range: Auto | Section | Module
     - Anchor mode: Byte-offset | Structural ⚠️
     - Anchor shift: 0 (slider, 0-5)
   
   - Checkbox: Enable explainability
   
   - Buttons: [Preview CLI] [Generate]
   
   ↓ User clicks "Preview CLI"
   
2. [CLI Preview Dialog]
   - Shows: `aobmaster synth --base game.exe --anchor-rva 0x1000 --profile balanced ...`
   - Buttons: [Copy] [Close]
   
   ↓ User clicks "Generate"
   
3. [Progress Dialog]
   - "Generating signature..."
   - Spinner
   - Cancel button (terminates SDK worker)
   
   ↓ SDK returns result
   
4. [Result View]
   - Success banner or error panel
   - Candidate list (table):
     - Rank | Pattern (truncated) | Score | Confidence | Valid
   - Expandable rows:
     - Full pattern (copyable)
     - Score breakdown
     - Validation results (unique, present)
   - If explain=True:
     - "View Trace" button → opens explainability viewer
   - Actions: [Save to Database] [Export JSON] [Copy Pattern]
   
   ↓ User clicks "Save to Database"
   
5. [Save Signature Dialog]
   - Database path picker (or use default)
   - Signature ID (auto-generated, editable)
   - Name (required)
   - Version range (optional)
   - Description (optional)
   - Author (auto-filled from system user)
   - Buttons: [Save] [Cancel]
   
   ↓ User clicks "Save"
   
6. [Confirmation]
   - "Signature saved: sig_001"
   - Action: [View in Database]
```

**SDK Calls**:
- Step 4: `synthesizer.generate(params)`
- Step 6: `database.save_signature(signature_id, name, pattern, ...)`

### 5.3 Flow: Reviewing Explainability Output

```
1. [Explainability Viewer] (triggered from result view)
   
   - Left panel: Event Timeline
     - ANCHOR_RESOLUTION (timestamp)
     - ALIGNMENT (timestamp)
     - CONTEXT_EXTRACTION (timestamp)
     - WILDCARDING (timestamp)
     - CANDIDATE_GENERATION (timestamp)
     - SCORING (timestamp)
     - VALIDATION (timestamp)
   
   ↓ User clicks "WILDCARDING" event
   
   - Right panel: Event Details
     - Event type: WILDCARDING
     - Timestamp: 2026-02-01 12:00:00.123
     - Profile: balanced
     - Decisions (table):
       - Offset | Byte | Instruction | Wildcarded? | Reason
       - 0x00   | 48   | mov         | No          | Opcode (fixed)
       - 0x01   | 8B   | mov         | No          | Opcode (fixed)
       - 0x02   | 05   | mov         | Yes         | RIP-relative displacement
       - 0x03   | ??   | mov         | Yes         | RIP-relative displacement
       - ...
   
   - Bottom panel: Visualization
     - Hex dump with color-coded bytes:
       - Green = fixed byte
       - Orange = wildcarded byte
       - Gray = outside pattern
```

**SDK Calls**:
- None (trace data already in `SynthesisResult.trace`)

### 5.4 Flow: Triggering a Test Run

```
1. [Test Configuration Dialog]
   - Database: sigs.db (picker)
   - Signature: [All] or select from dropdown
   - Corpus pattern: binaries/*.exe (glob pattern input)
   - Parallel workers: 1 (slider, 1-8)
   - Record results: ✓ (checkbox)
   - Buttons: [Preview] [Run Tests]
   
   ↓ User clicks "Run Tests"
   
2. [Test Progress View]
   - Progress bar (% complete)
   - Current binary: game_v1.2.exe
   - Passed: 5 | Failed: 1 | Remaining: 3
   - Log (scrollable):
     - ✓ sig_001: game_v1.0.exe (1 match)
     - ✓ sig_001: game_v1.1.exe (1 match)
     - ✗ sig_002: game_v1.2.exe (no match)
     - ...
   - Cancel button
   
   ↓ Tests complete
   
3. [Test Summary View]
   - Header: 8/10 signatures passed (80%)
   - Table: Signature | Passed | Failed | Pass Rate
   - Expandable rows:
     - Per-binary results (binary name, status, failure reason)
   - Actions: [Export Report] [View Failing Signatures]
```

**SDK Calls**:
- Step 2: `tester.test_all(corpus_pattern, signature_id, parallel, record)`

### 5.5 Flow: Exporting Artifacts

```
1. [Export Menu]
   - Export database to JSON
   - Export signatures (filtered selection)
   - Export test report
   - Export configuration preset
   
   ↓ User selects "Export database to JSON"
   
2. [File Picker Dialog]
   - Filename: signatures_backup.json
   - Location: ~/Documents
   - Buttons: [Save] [Cancel]
   
   ↓ User clicks "Save"
   
3. [Progress Dialog]
   - "Exporting database..."
   - Spinner
   
   ↓ Export completes
   
4. [Confirmation]
   - "Exported 42 signatures to signatures_backup.json"
   - Action: [Open Folder]
```

**SDK Calls**:
- Step 3: `database.export_signatures(output_path)`

### 5.6 Flow: Copying Equivalent CLI Command

```
Every GUI form has a "Copy as CLI" button:

Example (synthesis form):
1. User fills form:
   - Base: game.exe
   - Anchor RVA: 0x1000
   - Profile: balanced
   - Explain: ✓

2. User clicks "Copy as CLI"

3. Clipboard receives:
   aobmaster synth --base game.exe --anchor-rva 0x1000 --profile balanced --explain

4. Notification: "CLI command copied!"
```

**SDK Calls**: None (pure string generation)

---

## 6. Safety & Trust Mechanisms

### 6.1 Confidence Visualization

**Score Breakdown Chart**:
- Pie chart with 5 slices (U, P, S, L, A)
- Hovering shows:
  - Component name
  - Value (e.g., U = 1.00)
  - Weight (e.g., 35%)
  - Contribution to score (e.g., 0.35)

**Confidence Meter**:
- Horizontal bar (0-100%)
- Color-coded:
  - 🟢 ≥80%: "High confidence"
  - 🟡 50-79%: "Medium confidence"
  - 🔴 <50%: "Low confidence — manual review recommended"
- Tooltip shows factors:
  - Number of versions validated
  - Max RVA drift
  - Warnings

**Stability Assessment Badge** (from temporal analysis):
- 🟢 Stable: Pass rate ≥95%, low drift
- 🟡 Moderately Stable: Pass rate 80-94%
- 🟠 Fragile: Pass rate 60-79%
- 🔴 Unstable: Pass rate <60%
- ⚪ Unknown: Insufficient test data

### 6.2 Experimental Feature Warnings

**Structural Anchors** (`anchor_mode="structural"`):
- Warning banner in form:
  - "⚠️ Structural anchoring is EXPERIMENTAL and may fail. Use with caution."
- Confirmation dialog before generation:
  - "Structural mode uses heuristics with 70-80% accuracy. Continue?"
  - Checkbox: "I understand the risks"
  - Buttons: [Cancel] [Continue]
- Result badge:
  - "⚠️ Structural (Experimental)"

**Anchor Shift** (fallback anchoring):
- Warning icon next to anchor field if shift > 0
- Result notification:
  - "⚠️ Original anchor failed. Used fallback: anchor + 2 instructions."

### 6.3 Fallback Visibility

**Alignment Fallbacks**:
- If `seed_allow_multi=True` and multiple matches found:
  - Warning: "Multiple seed matches found (alignment ambiguity)"
  - Display all match locations (RVA list)

**Profile Fallbacks**:
- No implicit fallbacks
- If minimal profile fails, GUI suggests:
  - "Consider using 'balanced' or 'aggressive' profile"
  - Links to profile descriptions

### 6.4 Failure Transparency

**Error Display**:
- Errors from SDK shown verbatim (no rewording)
- Error panel with:
  - Error code (from SDK)
  - Message
  - Context (anchor RVA, binary name)
  - Suggested action (if available)
- Example:
  ```
  Error: Anchor not within any section
  Context: anchor_rva=0xFFFFFF, binary=game.exe
  Suggestion: Verify anchor address is valid for this binary.
  ```

**Warning Display**:
- Warnings shown in result view (badge count)
- Expandable list:
  - Warning message
  - Severity (info, warning, error)
  - Source (alignment, validation, scoring)

**Test Failures**:
- Per-signature failure reasons:
  - "Not unique (2 matches)"
  - "Not present (0 matches)"
  - "Pattern changed (offset drift)"
- Link to binary for manual inspection

### 6.5 Preventing Accidental Destructive Actions

**Confirmation Dialogs** (required for):
- Save signature (overwrites if ID exists)
- Deprecate signature (irreversible)
- Import signatures (merge strategy)
- Delete database (if feature added)

**Undo/Redo**:
- Not applicable (SDK operations are final)
- Export before destructive operations

**Batch Operations**:
- Require explicit confirmation
- Show preview: "This will test 42 signatures against 10 binaries (420 operations)"
- Estimated time: "~5 minutes"

**Auto-Save**:
- None (all saves explicit)
- Draft config saved locally (not in database)

---

## 7. Implementation Phases (Engineering-Realistic)

### Phase 0: Foundations (Weeks 1-2)

**Deliverables**:
- ✅ Electron project scaffold (React + TypeScript)
- ✅ IPC gateway (Node.js → Python SDK)
- ✅ JSON-RPC protocol implementation
- ✅ SDK worker script (`aobmaster/gui_worker.py`)
- ✅ Basic UI layout (header, sidebar, main content)
- ✅ File picker integration (Electron API)

**Risks**:
- IPC latency (mitigate: use async/await, show progress)
- SDK worker crashes (mitigate: auto-restart, error recovery)

**Validation**:
- IPC round-trip test: send request, receive response
- SDK worker can execute `Synthesizer.generate()`
- GUI can display JSON result

### Phase 1: Read-Only Inspection (Weeks 3-4)

**Deliverables**:
- ✅ Signature browser (list view)
  - Table with sorting, filtering
  - SDK call: `database.list_signatures()`
- ✅ Signature detail view
  - Pattern display
  - Metadata (anchor, version_range, created_at)
  - SDK call: `database.query_signature()`
- ✅ Export functionality
  - SDK call: `database.export_signatures()`

**Risks**:
- None (read-only operations)

**Validation**:
- Load existing database (from CLI)
- Verify GUI displays identical data to `aobmaster db list`
- Export JSON, compare with CLI export

### Phase 2: Controlled SDK Invocation (Weeks 5-7)

**Deliverables**:
- ✅ Synthesis form (all parameters)
  - Validation (hex strings, paths, enums)
  - Preview CLI command
- ✅ Generate button → SDK call
- ✅ Result view (candidates table)
- ✅ Save to database dialog
- ✅ Test runner UI
  - Configuration form (corpus, parallel)
  - Progress view
  - Results summary

**Risks**:
- Form validation complexity (mitigate: use schema validation library)
- Long-running operations (mitigate: cancel button, progress updates)

**Validation**:
- Generate signature via GUI, verify identical to CLI output (JSON diff)
- Save signature via GUI, query via CLI, compare
- Run tests via GUI, compare results with CLI

### Phase 3: Advanced Views (Weeks 8-9)

**Deliverables**:
- ✅ Score breakdown visualizations
  - Pie chart (5 components)
  - Bar chart (per-candidate comparison)
- ✅ Confidence meter
- ✅ Explainability trace viewer
  - Timeline (event list)
  - Event details (table)
  - Byte-level annotations
- ✅ Temporal analysis view
  - Pass rate chart (line over time)
  - Drift analysis (scatter plot)
  - Stability assessment

**Risks**:
- Chart library performance with large datasets (mitigate: pagination)

**Validation**:
- Visual inspection (manual QA)
- Compare charts with CLI JSON output (data integrity)

### Phase 4: Optional Polish (Weeks 10-11)

**Deliverables**:
- ⚠️ Dark mode / themes
- ⚠️ Keyboard shortcuts
- ⚠️ Drag-and-drop (file import)
- ⚠️ Search/filter history
- ⚠️ Configuration presets (save/load)
- ⚠️ Improved error messages (user-friendly wording)

**Risks**:
- Scope creep (mitigate: strict feature freeze after Phase 3)

**Validation**:
- User acceptance testing (UAT)
- Accessibility audit (WCAG compliance)

---

## 8. Testing & Validation Strategy

### 8.1 Unit Tests

**Frontend (TypeScript/Jest)**:
- ✅ IPC message construction (correct JSON-RPC format)
- ✅ CLI command generation (accurate string building)
- ✅ Form validation (hex strings, paths, enums)
- ✅ Error handling (IPC failures, SDK errors)

**Backend (Python/pytest)**:
- ✅ SDK worker request handling
- ✅ JSON-RPC protocol compliance
- ✅ Error serialization (exceptions → JSON)

**Coverage Target**: ≥80% for critical paths (IPC, validation, SDK calls)

### 8.2 Integration Tests

**SDK Parity Tests**:
- ✅ For each GUI workflow, execute equivalent CLI command
- ✅ Compare outputs (JSON diff, byte-for-byte)
- ✅ Examples:
  - Generate signature: GUI vs `aobmaster synth`
  - Save signature: GUI vs `aobmaster db save`
  - Test suite: GUI vs `aobmaster test`

**Replayability Tests**:
- ✅ Record GUI session (audit log)
- ✅ Replay via CLI (parse log, execute commands)
- ✅ Verify identical results

**Error Propagation Tests**:
- ✅ Inject SDK errors (invalid anchor, missing binary)
- ✅ Verify GUI displays errors verbatim
- ✅ Verify no silent failures

### 8.3 Regression Detection

**Baseline Suite**:
- ✅ Capture 10 known-good synthesis scenarios (input + output)
- ✅ Run GUI tests against baseline
- ✅ Fail CI if outputs differ

**Version Compatibility**:
- ✅ Test GUI v2.3 with SDK v2.1, v2.2 (backward compatibility)
- ✅ Verify CLI parity across versions

**Performance Tests**:
- ✅ IPC round-trip latency: <100ms
- ✅ Generate signature: <5s (same as CLI)
- ✅ Load 1000 signatures: <2s

### 8.4 Manual QA Checklist

**Before Release**:
- ✅ Install on clean machine (no Python pre-installed)
- ✅ Verify SDK worker auto-starts
- ✅ Test all workflows (generate, save, test, analyze)
- ✅ Test error scenarios (missing binary, invalid anchor)
- ✅ Verify CLI command export accuracy (run exported commands)
- ✅ Test on Windows, macOS, Linux
- ✅ Verify database compatibility (CLI ↔ GUI)

---

## 9. Non-Goals & Explicit Exclusions

### 9.1 What This GUI Does NOT Do

**Pattern Editing**:
- ❌ Free-form AoB pattern editor
- **Reason**: Patterns must be SDK-generated (validation guarantees)

**Smart Features**:
- ❌ Auto-suggest anchor points (no `aobmaster smart` integration)
- ❌ Auto-fix failing signatures
- ❌ Heuristic profile selection
- **Reason**: No SDK wrappers exist; would duplicate CLI logic

**Binary Inspection**:
- ❌ Disassembly viewer (no `aobmaster info` integration)
- ❌ Hex editor
- ❌ Pattern scanning (no `aobmaster scan` integration)
- **Reason**: Out of scope for signature management; use external tools

**Live Process Interaction**:
- ❌ Attach to running process
- ❌ Read/write process memory
- **Reason**: AoBMaster is file-based only (by design)

**Cloud Features**:
- ❌ Signature sharing/repository
- ❌ User accounts
- ❌ Telemetry
- **Reason**: Privacy, offline-first design

**Batch Scripting**:
- ❌ Visual scripting/workflows
- ❌ Macro recording
- **Reason**: Use CLI for scripting; GUI is interactive only

**Multi-User/Collaboration**:
- ❌ Real-time collaboration
- ❌ Locking/conflict resolution
- **Reason**: Single-user tool; use version control for sharing

### 9.2 Why These Exclusions Matter

**Scope Protection**:
- Prevents feature creep
- Maintains GUI as thin client
- Avoids re-implementing CLI logic

**Trust Maintenance**:
- No hidden intelligence
- No GUI-invented behavior
- All features map to SDK

**Future-Proofing**:
- If SDK adds `smart` wrapper → GUI can integrate
- If SDK adds `scan` wrapper → GUI can integrate
- If SDK adds cloud API → GUI can integrate

---

## 10. Final Assessment

### 10.1 Can This GUI Be Safely Shipped?

**YES**, under these conditions:

✅ **Architecture Enforced**:
- IPC gateway prevents direct module access
- SDK worker is the **only** code path
- No GUI-specific business logic

✅ **Contract Honored**:
- GUI calls only whitelisted SDK methods
- All parameters explicit and visible
- Errors propagate verbatim

✅ **Parity Validated**:
- Integration tests prove CLI equivalence
- Audit logs enable replay
- JSON exports match CLI outputs

✅ **Safety Mechanisms**:
- Confidence visualization
- Experimental warnings
- Confirmation dialogs for destructive actions
- No silent failures

### 10.2 Red Flags (v3.0 Territory)

**Do NOT proceed if**:

🚩 **GUI invents new synthesis logic**:
- Example: "Smart wildcard optimizer" not in SDK
- **Impact**: Breaks CLI parity, non-reproducible

🚩 **Hidden defaults**:
- Example: GUI secretly changes `seed_bytes` based on binary size
- **Impact**: Non-deterministic, breaks replayability

🚩 **Pattern mutation**:
- Example: GUI allows editing AoB patterns directly
- **Impact**: Bypasses validation, breaks guarantees

🚩 **SDK bypass**:
- Example: GUI calls `matcher.py` directly for performance
- **Impact**: Diverges from CLI, duplicates code

🚩 **Cloud integration without explicit design**:
- Example: Auto-upload signatures to public repo
- **Impact**: Privacy violation, scope explosion

**If any red flag is observed → STOP. Redesign as v3.0.**

### 10.3 Success Criteria

**Ship v2.3 GUI if**:

1. ✅ **100% SDK-backed**: Every action maps to SDK method
2. ✅ **CLI parity**: Integration tests pass (JSON diff clean)
3. ✅ **Replayability**: Audit logs can be replayed via CLI
4. ✅ **No new logic**: Zero business logic in GUI codebase
5. ✅ **Transparency**: All parameters visible, errors surfaced
6. ✅ **Safety**: Confirmations, warnings, confidence display
7. ✅ **Performance**: IPC latency <100ms, no slower than CLI
8. ✅ **Cross-platform**: Works on Windows, macOS, Linux
9. ✅ **Documentation**: User guide, SDK mapping table
10. ✅ **Team consensus**: Code review approval, QA sign-off

**Acceptance Test**:
- Load pre-existing database (from CLI)
- Generate 10 signatures via GUI
- Export database via GUI
- Import into new database via CLI
- Verify all signatures identical (byte-for-byte)

### 10.4 Go / No-Go Decision

**GO** ✅ if:
- All Phase 0-2 deliverables complete
- Integration tests passing
- No red flags identified
- Team has capacity for maintenance

**NO-GO** ❌ if:
- Architecture shortcuts taken (e.g., direct module calls)
- CLI parity failing (even 1 test)
- Red flags present
- SDK not stable (v2.1+ required)

### 10.5 Maintenance Commitment

**Required for v2.3 GUI**:

1. **Bug Fixes**: Within 48 hours for critical issues
2. **SDK Updates**: GUI updated within 1 week of SDK release
3. **CLI Parity**: Regression suite run on every commit
4. **Documentation**: User guide updated with GUI screenshots
5. **Security**: IPC validation reviewed quarterly

**Team Capacity**:
- 1 frontend engineer (React/TypeScript)
- 1 backend engineer (Python SDK integration)
- 1 QA engineer (testing, validation)
- 1 designer (UX, polish)

**Estimated Effort**: 11 weeks development + 2 weeks QA

---

## 11. Appendix: Reference Materials

### 11.1 CLI → SDK → GUI Mapping Table

| CLI Command | SDK Method | GUI Action | Notes |
|-------------|------------|------------|-------|
| `synth` | `Synthesizer.generate()` | "Generate Signature" form | All parameters explicit |
| `db init` | `SignatureDatabase.init()` | "New Database" action | Idempotent, safe to repeat |
| `db save` | `SignatureDatabase.save_signature()` | "Save Signature" dialog | Confirmation required |
| `db list` | `SignatureDatabase.list_signatures()` | Signature browser | Read-only |
| `db query` | `SignatureDatabase.query_signature()` | Detail view | Read-only |
| `db export` | `SignatureDatabase.export_signatures()` | "Export Database" action | File picker |
| `db import` | `SignatureDatabase.import_signatures()` | "Import Signatures" action | Merge strategy |
| `test` | `SignatureTester.test_all()` | "Run Tests" dialog | Progress view |
| `analyze` | `TemporalAnalyzer.analyze_signature()` | "Analyze Stability" view | Read-only |
| `diagnose` | `database.query_signature()` + lineage | "Show Lineage" view | Read-only |
| `scan` | ❌ No SDK wrapper | ❌ Not in GUI | Use CLI |
| `info` | ❌ No SDK wrapper | ❌ Not in GUI | Use CLI |
| `smart` | ❌ No SDK wrapper | ❌ Not in GUI | Use CLI |

### 11.2 Configuration Schema (TypeScript)

```typescript
interface SynthesisParams {
  base_binary: string;
  anchor_rva?: string;
  anchor_fo?: string;
  anchor_va?: string;
  version_binaries?: string[];
  profile?: "minimal" | "default" | "strict" | "balanced" | "aggressive" | "stack-only" | "global-only" | "memory-heavy";
  align_mode?: "bytespan" | "anchor-rva";
  seed_bytes?: number;
  seed_scan?: "section" | "module";
  seed_allow_multi?: boolean;
  context_before?: number;
  context_after?: number;
  max_context_insns?: number;
  context_variations?: boolean;
  min_insns?: number;
  max_insns?: number;
  require_unique?: boolean;
  require_present_all?: boolean;
  scan_range?: "section" | "module" | null;
  explain?: boolean;
  anchor_mode?: "byte-offset" | "structural";
  anchor_shift?: number;
}
```

### 11.3 Risk Matrix

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **GUI bypasses SDK** | Low | Critical | Code review, IPC gateway enforcement |
| **IPC latency** | Medium | Medium | Async/await, progress indicators |
| **SDK worker crash** | Low | High | Auto-restart, error recovery |
| **CLI divergence** | Medium | Critical | Integration tests, CI enforcement |
| **Scope creep** | High | High | Strict feature freeze after Phase 3 |
| **User edits patterns** | Low | Critical | No pattern editor in UI |
| **Hidden defaults** | Medium | High | All parameters visible in forms |
| **Non-determinism** | Low | Critical | No randomness, audit logs |

### 11.4 Glossary

- **SDK**: Software Development Kit (aobmaster/sdk.py)
- **IPC**: Inter-Process Communication (Electron main ↔ renderer)
- **JSON-RPC**: JSON Remote Procedure Call (protocol for SDK worker)
- **GUI-SAFE**: Operations that call SDK methods only
- **GUI-FORBIDDEN**: Operations that would bypass SDK or duplicate logic
- **CLI Parity**: GUI produces identical results to CLI for same inputs
- **Replayability**: GUI actions can be replayed via CLI (audit log)
- **Audit Log**: Timestamped log of all SDK calls made by GUI
- **Red Flag**: Architectural violation that forces v3.0 redesign

---

## Conclusion

The AoBMaster v2.3 GUI is **implementable as specified** without weakening the core guarantees of determinism, reproducibility, and explainability. The architecture enforces SDK-only access through IPC isolation, preventing GUI-specific logic from entering the codebase.

**Key Success Factors**:
1. Strict adherence to SDK contract (no direct module calls)
2. Comprehensive integration testing (CLI parity validation)
3. Transparent parameter handling (no hidden defaults)
4. Safety mechanisms (confirmations, warnings, confidence display)
5. Replayability guarantees (audit logs, CLI export)

**Recommendation**: **PROCEED with v2.3 GUI implementation**, contingent on:
- Phase 0 validation (IPC gateway, SDK worker)
- Phase 1 validation (read-only operations match CLI)
- Phase 2 validation (synthesis operations match CLI)
- No red flags during development

**Timeline**: 11 weeks development + 2 weeks QA = **13 weeks to production**

**Confidence**: **HIGH** — This design is conservative, testable, and maintainable.

---

**Document Status**: ✅ Complete  
**Next Steps**: Team review → Phase 0 kickoff  
**Owner**: Architecture Team  
**Reviewers**: Engineering Lead, QA Lead, Product Manager