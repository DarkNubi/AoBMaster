"""
AoBMaster v2 SDK - Phase 7

Python SDK providing programmatic access to AoBMaster functionality.
The CLI is a thin wrapper over this SDK.

Design Principles:
- API-first: SDK is the primary interface, CLI calls SDK
- Type-safe: Full type hints for IDE support
- Backward compatible: SDK matches v1.x behavior by default
- Opt-in v2 features: Explainability, database, testing, etc.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import json


@dataclass
class SynthesisConfig:
    """Configuration for signature synthesis."""
    # Required
    base_binary: Union[str, Path]
    anchor_rva: Optional[str] = None
    anchor_fo: Optional[str] = None
    anchor_va: Optional[str] = None
    
    # Version alignment
    version_binaries: Optional[List[Union[str, Path]]] = None
    align_mode: str = "bytespan"
    seed_bytes: int = 32
    seed_scan: str = "section"
    seed_allow_multi: bool = False
    
    # Context window
    context_before: int = 8
    context_after: int = 8
    max_context_insns: int = 32
    context_variations: bool = False
    
    # Wildcarding
    profile: str = "default"
    
    # Candidate generation
    min_insns: int = 6
    max_insns: int = 14
    top_n: int = 5
    
    # Validation
    require_unique: bool = True
    require_present_all: bool = True
    scan_range: Optional[str] = None
    
    # v2 Features (opt-in)
    explain: bool = False
    anchor_mode: str = "byte-offset"  # "byte-offset" | "structural"
    structural_min_confidence: float = 0.60
    anchor_shift: int = 0


@dataclass
class SynthesisResult:
    """Result from signature synthesis."""
    ok: bool
    version: str
    candidates: List[Dict[str, Any]]
    warnings: List[Dict[str, Any]]
    errors: List[Dict[str, Any]]
    
    # Additional metadata
    anchor: Dict[str, Any]
    alignment: List[Dict[str, Any]]
    hashes: Dict[str, Dict[str, str]]
    
    # v2 features
    trace: Optional[Dict[str, Any]] = None
    signature_ir: Optional[Dict[str, Any]] = None
    structural_anchor: Optional[Dict[str, Any]] = None
    
    def get_top_candidate(self) -> Optional[Dict[str, Any]]:
        """Get the top-ranked valid candidate, or None if none exist."""
        valid = [c for c in self.candidates if c.get("valid")]
        return valid[0] if valid else None
    
    def get_top_pattern(self) -> Optional[str]:
        """Get the AoB pattern string of the top candidate, or None."""
        top = self.get_top_candidate()
        return top.get("aob") if top else None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary (JSON-serializable)."""
        return {
            "ok": self.ok,
            "version": self.version,
            "candidates": self.candidates,
            "warnings": self.warnings,
            "errors": self.errors,
            "anchor": self.anchor,
            "alignment": self.alignment,
            "hashes": self.hashes,
            "trace": self.trace,
            "signature_ir": self.signature_ir,
            "structural_anchor": self.structural_anchor,
        }


class Synthesizer:
    """
    High-level interface for signature synthesis.
    
    Usage:
        synth = Synthesizer("game.exe")
        result = synth.generate(anchor_rva="0x123456", profile="balanced")
        print(result.get_top_pattern())
    """
    
    def __init__(self, base_binary: Union[str, Path]):
        """
        Initialize synthesizer with base binary.
        
        Args:
            base_binary: Path to base PE executable
        """
        self.base_binary = Path(base_binary)
        if not self.base_binary.exists():
            raise FileNotFoundError(f"Binary not found: {self.base_binary}")
    
    def generate(
        self,
        anchor_rva: Optional[str] = None,
        anchor_fo: Optional[str] = None,
        anchor_va: Optional[str] = None,
        version_binaries: Optional[List[Union[str, Path]]] = None,
        profile: str = "default",
        explain: bool = False,
        **kwargs
    ) -> SynthesisResult:
        """
        Generate signatures for the given anchor.
        
        Args:
            anchor_rva: Anchor RVA (hex string, e.g., "0x123456")
            anchor_fo: Anchor file offset (hex string)
            anchor_va: Anchor virtual address (hex string)
            version_binaries: List of additional binary versions for alignment
            profile: Wildcarding profile ("minimal", "default", "strict", etc.)
            explain: Enable explainability mode (v2 feature)
            **kwargs: Additional config options (see SynthesisConfig)
            
        Returns:
            SynthesisResult object
            
        Raises:
            ValueError: If anchor not specified or invalid
            RuntimeError: If synthesis fails
        """
        # Build config
        config = SynthesisConfig(
            base_binary=self.base_binary,
            anchor_rva=anchor_rva,
            anchor_fo=anchor_fo,
            anchor_va=anchor_va,
            version_binaries=version_binaries or [],
            profile=profile,
            explain=explain,
            **kwargs
        )
        
        # Call internal synthesis function
        return _run_synthesis(config)


class SignatureDatabase:
    """
    Interface to signature database (v2 Phase 2).
    
    Usage:
        db = SignatureDatabase("signatures.db")
        db.save_signature(
            signature_id="sig1",
            name="player_health",
            pattern="48 8B ?? ?? ?? ?? 85 C0",
            metadata={"version_range": "1.0-1.5"}
        )
        sig = db.query_signature("sig1")
    """
    
    def __init__(self, db_path: Union[str, Path]):
        """
        Initialize database connection.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
    
    def init(self) -> None:
        """Initialize database schema."""
        from .database import init_database
        init_database(str(self.db_path))
    
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
        parent_id: Optional[str] = None,
    ) -> None:
        """
        Save signature to database.
        
        Args:
            signature_id: Unique signature identifier
            name: Human-readable name
            pattern: AoB pattern string
            anchor_rva: Anchor RVA (hex string)
            binary_hash: SHA256 hash of binary
            author: Author name
            version_range: Version range string (e.g., "1.0-1.5")
            metadata: Additional metadata (JSON-serializable dict)
            parent_id: Parent signature ID for families (v2 Phase 5)
        """
        from .database import save_signature_to_db
        save_signature_to_db(
            db_path=str(self.db_path),
            signature_id=signature_id,
            name=name,
            pattern=pattern,
            anchor_rva=anchor_rva,
            binary_hash=binary_hash,
            author=author,
            version_range=version_range,
            metadata_json=json.dumps(metadata) if metadata else None,
            parent_id=parent_id,
        )
    
    def query_signature(self, signature_id: str) -> Optional[Dict[str, Any]]:
        """
        Query signature by ID.
        
        Args:
            signature_id: Signature ID to query
            
        Returns:
            Signature dict or None if not found
        """
        from .database import query_signature_by_id
        return query_signature_by_id(str(self.db_path), signature_id)
    
    def list_signatures(self, filter_text: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all signatures in database.
        
        Args:
            filter_text: Optional filter substring (matches id or name)
            
        Returns:
            List of signature dicts
        """
        from .database import list_all_signatures
        return list_all_signatures(str(self.db_path), filter_text)
    
    def export_signatures(self, output_path: Union[str, Path]) -> None:
        """
        Export all signatures to JSON file.
        
        Args:
            output_path: Path to output JSON file
        """
        from .database import export_database
        export_database(str(self.db_path), str(output_path))
    
    def import_signatures(self, input_path: Union[str, Path]) -> None:
        """
        Import signatures from JSON file.
        
        Args:
            input_path: Path to input JSON file
        """
        from .database import import_database
        import_database(str(self.db_path), str(input_path))


class SignatureTester:
    """
    Interface to signature testing (v2 Phase 3).
    
    Usage:
        tester = SignatureTester("signatures.db")
        results = tester.test_all(corpus_pattern="binaries/*.exe", parallel=4)
        print(f"Passed: {results['summary']['passed']}")
    """
    
    def __init__(self, db_path: Union[str, Path]):
        """
        Initialize tester with database.
        
        Args:
            db_path: Path to signature database
        """
        self.db_path = Path(db_path)
    
    def test_signature(
        self,
        signature_id: str,
        binary_path: Union[str, Path],
        record: bool = False
    ) -> Dict[str, Any]:
        """
        Test single signature against single binary.
        
        Args:
            signature_id: Signature ID to test
            binary_path: Path to binary to test against
            record: Whether to record result in database
            
        Returns:
            Test result dict with 'passed', 'match_count', 'failure_reason'
        """
        from .test_command import test_single_signature
        return test_single_signature(
            db_path=str(self.db_path),
            signature_id=signature_id,
            binary_path=str(binary_path),
            record=record
        )
    
    def test_all(
        self,
        corpus_pattern: str,
        signature_id: Optional[str] = None,
        parallel: int = 1,
        record: bool = False
    ) -> Dict[str, Any]:
        """
        Test signature(s) against corpus of binaries.
        
        Args:
            corpus_pattern: Glob pattern for binary corpus (e.g., "*.exe")
            signature_id: Test specific signature, or None for all
            parallel: Number of parallel workers (default: 1)
            record: Whether to record results in database
            
        Returns:
            Test results dict with 'summary' and 'results' lists
        """
        from .test_command import test_corpus
        return test_corpus(
            db_path=str(self.db_path),
            corpus_pattern=corpus_pattern,
            signature_id=signature_id,
            parallel=parallel,
            record=record
        )


class TemporalAnalyzer:
    """
    Interface to temporal analysis (v2 Phase 4).
    
    Usage:
        analyzer = TemporalAnalyzer("signatures.db")
        analysis = analyzer.analyze_signature("sig1")
        print(f"Confidence: {analysis['confidence_interval']}")
    """
    
    def __init__(self, db_path: Union[str, Path]):
        """
        Initialize analyzer with database.
        
        Args:
            db_path: Path to signature database
        """
        self.db_path = Path(db_path)
    
    def analyze_signature(self, signature_id: str) -> Dict[str, Any]:
        """
        Perform temporal analysis on signature.
        
        Args:
            signature_id: Signature ID to analyze
            
        Returns:
            Analysis dict with:
            - pass_rate: Historical success rate
            - drift_analysis: RVA drift trends
            - confidence_interval: (current, pessimistic, optimistic)
            - stability_assessment: "stable" | "fragile" | "unknown"
            - recommendation: Actionable advice
        """
        from .temporal import analyze_signature_temporal
        return analyze_signature_temporal(str(self.db_path), signature_id)
    
    def analyze_all(self) -> List[Dict[str, Any]]:
        """
        Analyze all signatures in database.
        
        Returns:
            List of analysis dicts (one per signature)
        """
        from .temporal import analyze_all_signatures
        return analyze_all_signatures(str(self.db_path))


# Internal function (called by SDK)
def _run_synthesis(config: SynthesisConfig) -> SynthesisResult:
    """
    Internal synthesis function. Calls CLI argument parser and run_synth.
    
    This is a bridge between SDK API and CLI implementation.
    In a future refactor, CLI would call SDK directly (not vice versa).
    """
    # For now, this is a placeholder that would call the actual synth logic
    # In production, we'd refactor synth.py to be library-first
    
    # Import here to avoid circular dependency
    from .synth import run_synth
    from argparse import Namespace
    
    # Convert config to argparse Namespace (CLI format)
    args = Namespace(
        base=config.base_binary,
        anchor_rva=config.anchor_rva,
        anchor_fo=config.anchor_fo,
        anchor_va=config.anchor_va,
        versions=config.version_binaries,
        align=config.align_mode,
        seed_bytes=config.seed_bytes,
        seed_scan=config.seed_scan,
        seed_allow_multi="true" if config.seed_allow_multi else "false",
        context_before=config.context_before,
        context_after=config.context_after,
        max_context_insns=config.max_context_insns,
        context_variations="on" if config.context_variations else "off",
        profile=config.profile,
        min_insns=config.min_insns,
        max_insns=config.max_insns,
        top_n=config.top_n,
        require_unique="true" if config.require_unique else "false",
        require_present_all="true" if config.require_present_all else "false",
        scan_range=config.scan_range,
        explain=config.explain,
        anchor_mode=config.anchor_mode,
        structural_min_confidence=config.structural_min_confidence,
        anchor_shift=config.anchor_shift,
        format="json",  # Always JSON for SDK
    )
    
    # Run synthesis (would need to capture JSON output, not write to stdout)
    # This is a simplification - in production we'd refactor synth.py
    # to return data instead of printing
    
    # For now, raise NotImplementedError to indicate refactoring needed
    raise NotImplementedError(
        "SDK is currently a placeholder. To use SDK functionality, "
        "synth.py needs to be refactored to return data instead of printing. "
        "This is a v2.1 task. For now, use CLI directly."
    )
