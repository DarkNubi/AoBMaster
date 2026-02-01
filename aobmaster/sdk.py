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
        db.init()
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
        from .database import SignatureDatabase as DB
        self.db_path = Path(db_path)
        self._db = DB(self.db_path)
    
    def init(self) -> None:
        """Initialize database schema."""
        self._db.init_database()
    
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
        from .database import SignatureRecord
        from datetime import datetime, timezone
        
        record = SignatureRecord(
            id=signature_id,
            name=name,
            pattern=pattern,
            anchor_rva=int(anchor_rva, 16) if anchor_rva else 0,
            binary_hash=binary_hash or "",
            created_at=datetime.now(timezone.utc).isoformat(),
            author=author,
            version_range=version_range,
            metadata=metadata or {},
            parent_id=parent_id,
        )
        self._db.save_signature(record)
    
    def query_signature(self, signature_id: str) -> Optional[Dict[str, Any]]:
        """
        Query signature by ID.
        
        Args:
            signature_id: Signature ID to query
            
        Returns:
            Signature dict or None if not found
        """
        record = self._db.get_signature(signature_id)
        return record.to_dict() if record else None
    
    def list_signatures(self, filter_text: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all signatures in database.
        
        Args:
            filter_text: Optional filter substring (matches id or name)
            
        Returns:
            List of signature dicts
        """
        records = self._db.list_signatures(name_filter=filter_text)
        return [r.to_dict() for r in records]
    
    def export_signatures(self, output_path: Union[str, Path]) -> None:
        """
        Export all signatures to JSON file.
        
        Args:
            output_path: Path to output JSON file
        """
        self._db.export_to_json(Path(output_path))
    
    def import_signatures(self, input_path: Union[str, Path]) -> None:
        """
        Import signatures from JSON file.
        
        Args:
            input_path: Path to input JSON file
        """
        self._db.import_from_json(Path(input_path))

    def deprecate_signature(self, signature_id: str, reason: str) -> None:
        """
        Deprecate a signature in the database.

        Args:
            signature_id: Signature ID to deprecate
            reason: Deprecation reason
        """
        self._db.deprecate_signature(signature_id, reason)


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
        from .database import SignatureDatabase as DB
        self.db_path = Path(db_path)
        self._db = DB(self.db_path)
    
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
        from .test_command import _test_signature_against_binary
        
        # Get signature from database
        sig_record = self._db.get_signature(signature_id)
        if not sig_record:
            return {
                "signature_id": signature_id,
                "binary_path": str(binary_path),
                "passed": False,
                "match_count": 0,
                "failure_reason": f"Signature '{signature_id}' not found in database"
            }
        
        # Test signature
        result = _test_signature_against_binary(
            signature_id=signature_id,
            pattern_string=sig_record.pattern,
            binary_path=Path(binary_path),
            expected_unique=True
        )
        
        # Record result if requested
        if record:
            self._db.record_test_result(
                signature_id=signature_id,
                binary_path=str(binary_path),
                binary_hash=result["binary_hash"],
                passed=result["passed"],
                failure_reason=result.get("failure_reason")
            )
        
        return result
    
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
        from pathlib import Path
        import glob
        
        # Get signatures to test
        if signature_id:
            sig_record = self._db.get_signature(signature_id)
            if not sig_record:
                return {
                    "summary": {"passed": 0, "failed": 1, "total": 1},
                    "results": [{
                        "signature_id": signature_id,
                        "error": f"Signature '{signature_id}' not found"
                    }]
                }
            signatures = [sig_record]
        else:
            signatures = self._db.list_signatures()
        
        # Get binaries from corpus
        binaries = list(Path().glob(corpus_pattern))
        
        # Test all combinations
        results = []
        for sig_record in signatures:
            for binary_path in binaries:
                result = self.test_signature(
                    signature_id=sig_record.id,
                    binary_path=binary_path,
                    record=record
                )
                results.append(result)
        
        # Compute summary
        passed = sum(1 for r in results if r.get("passed"))
        failed = len(results) - passed
        
        return {
            "summary": {
                "passed": passed,
                "failed": failed,
                "total": len(results)
            },
            "results": results
        }


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
        from .database import SignatureDatabase as DB
        
        db = DB(self.db_path)
        conn = db._connect()
        
        result = analyze_signature_temporal(conn, signature_id)
        return result.to_dict()
    
    def analyze_all(self) -> List[Dict[str, Any]]:
        """
        Analyze all signatures in database.
        
        Returns:
            List of analysis dicts (one per signature)
        """
        from .database import SignatureDatabase as DB
        
        db = DB(self.db_path)
        signatures = db.list_signatures()
        
        results = []
        for sig in signatures:
            try:
                analysis = self.analyze_signature(sig.id)
                results.append(analysis)
            except Exception as e:
                # Skip signatures that can't be analyzed
                results.append({
                    "signature_id": sig.id,
                    "error": str(e)
                })
        
        return results


# Internal function (called by SDK)
def _run_synthesis(config: SynthesisConfig) -> SynthesisResult:
    """
    Internal synthesis function that bridges SDK to core logic.
    
    This function calls run_synthesis_core() and converts the result
    to a SynthesisResult object.
    """
    # Import here to avoid circular dependency
    from .synth import run_synthesis_core
    
    # Call core synthesis function
    result_dict = run_synthesis_core(
        base_binary=Path(config.base_binary),
        anchor_rva=int(config.anchor_rva, 16) if config.anchor_rva else None,
        anchor_fo=int(config.anchor_fo, 16) if config.anchor_fo else None,
        anchor_va=int(config.anchor_va, 16) if config.anchor_va else None,
        version_binaries=[Path(p) for p in config.version_binaries] if config.version_binaries else None,
        align_mode=config.align_mode,
        seed_bytes=config.seed_bytes,
        seed_scan=config.seed_scan,
        seed_allow_multi=config.seed_allow_multi,
        context_before=config.context_before,
        context_after=config.context_after,
        max_context_insns=config.max_context_insns,
        context_variations=config.context_variations,
        profile=config.profile,
        min_insns=config.min_insns,
        max_insns=config.max_insns,
        require_unique=config.require_unique,
        require_present_all=config.require_present_all,
        scan_range_base=config.scan_range,
        scan_range_versions=config.scan_range,
        explain=config.explain,
        anchor_mode=config.anchor_mode,
        structural_min_confidence=config.structural_min_confidence,
        anchor_shift=config.anchor_shift,
    )
    
    # Convert dict to SynthesisResult
    return SynthesisResult(
        ok=result_dict.get("ok", False),
        version=result_dict.get("version", "2.0.0"),
        candidates=result_dict.get("candidates", []),
        warnings=result_dict.get("warnings", []),
        errors=result_dict.get("errors", []),
        anchor=result_dict.get("anchor", {}),
        alignment=result_dict.get("alignment", []),
        hashes=result_dict.get("hashes", {}),
        trace=result_dict.get("trace"),
        signature_ir=result_dict.get("signature_ir"),
        structural_anchor=result_dict.get("structural_anchor"),
    )
