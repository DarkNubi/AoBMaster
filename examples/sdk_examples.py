"""
Example: Using AoBMaster SDK

This example demonstrates how to use the AoBMaster Python SDK
to programmatically generate, store, test, and analyze signatures.
"""

from pathlib import Path
from aobmaster.sdk import Synthesizer, SignatureDatabase, SignatureTester, TemporalAnalyzer


def example_basic_synthesis():
    """Example 1: Basic signature synthesis."""
    print("=== Example 1: Basic Synthesis ===")
    
    # Initialize synthesizer
    synth = Synthesizer("game.exe")
    
    # Generate signatures
    result = synth.generate(
        anchor_rva="0x123456",
        profile="balanced",
        explain=False  # Set to True for detailed trace
    )
    
    # Get top signature
    if result.ok:
        top_pattern = result.get_top_pattern()
        print(f"Top signature: {top_pattern}")
        
        # Access full candidate data
        top = result.get_top_candidate()
        if top:
            print(f"Score: {top['score']['score']:.2f}")
            print(f"Confidence: {top['score']['confidence']:.2f}")
    else:
        print(f"Synthesis failed: {result.errors}")


def example_multi_version_synthesis():
    """Example 2: Multi-version alignment."""
    print("\n=== Example 2: Multi-Version Synthesis ===")
    
    synth = Synthesizer("game_v1.0.exe")
    
    result = synth.generate(
        anchor_rva="0x123456",
        version_binaries=["game_v1.1.exe", "game_v1.2.exe", "game_v1.3.exe"],
        profile="balanced",
        align_mode="bytespan"
    )
    
    if result.ok:
        print(f"Tested against {len(result.alignment)} versions")
        print(f"Top pattern: {result.get_top_pattern()}")


def example_structural_anchoring():
    """Example 3: Structural anchoring (v2 Phase 6)."""
    print("\n=== Example 3: Structural Anchoring ===")
    
    synth = Synthesizer("game.exe")
    
    # Use structural anchoring (HIGH RISK - opt-in)
    result = synth.generate(
        anchor_rva="0x123456",
        anchor_mode="structural",
        structural_min_confidence=0.70,
        explain=True  # Always use explain mode with structural anchoring
    )
    
    if result.ok:
        if result.structural_anchor:
            print(f"Function detected: {result.structural_anchor['function_detected']}")
            print(f"Confidence: {result.structural_anchor['confidence']:.2f}")
            print(f"Prologue: {result.structural_anchor['prologue_pattern']}")
        print(f"Top pattern: {result.get_top_pattern()}")


def example_database_workflow():
    """Example 4: Complete database workflow."""
    print("\n=== Example 4: Database Workflow ===")
    
    # Initialize database
    db = SignatureDatabase("signatures.db")
    db.init()
    
    # Generate and save signature
    synth = Synthesizer("game.exe")
    result = synth.generate(anchor_rva="0x123456")
    
    if result.ok:
        top = result.get_top_candidate()
        if top:
            db.save_signature(
                signature_id="player_health_v1",
                name="Player Health Offset",
                pattern=top["aob"],
                anchor_rva="0x123456",
                binary_hash=result.hashes["game.exe"]["sha256"],
                author="developer@example.com",
                version_range="1.0-1.5",
                metadata={
                    "score": top["score"]["score"],
                    "confidence": top["score"]["confidence"],
                    "description": "Signature for player health variable access"
                }
            )
            print("Signature saved to database")
    
    # Query signature
    sig = db.query_signature("player_health_v1")
    if sig:
        print(f"Retrieved signature: {sig['name']}")
        print(f"Pattern: {sig['pattern']}")
    
    # List all signatures
    all_sigs = db.list_signatures()
    print(f"Total signatures in database: {len(all_sigs)}")
    
    # Export database
    db.export_signatures("signatures_backup.json")
    print("Database exported to JSON")


def example_testing_workflow():
    """Example 5: Testing signatures against corpus."""
    print("\n=== Example 5: Testing Workflow ===")
    
    # Initialize tester
    tester = SignatureTester("signatures.db")
    
    # Test single signature against single binary
    result = tester.test_signature(
        signature_id="player_health_v1",
        binary_path="game_v1.3.exe",
        record=True  # Record result in database
    )
    
    print(f"Test result: {'PASS' if result['passed'] else 'FAIL'}")
    if not result['passed']:
        print(f"Failure reason: {result['failure_reason']}")
    
    # Test all signatures against corpus
    corpus_results = tester.test_all(
        corpus_pattern="binaries/*.exe",
        parallel=4,  # Use 4 worker processes
        record=True
    )
    
    summary = corpus_results['summary']
    print(f"Tested {summary['total']} signatures")
    print(f"Passed: {summary['passed']}")
    print(f"Failed: {summary['failed']}")


def example_temporal_analysis():
    """Example 6: Temporal analysis and predictions."""
    print("\n=== Example 6: Temporal Analysis ===")
    
    # Initialize analyzer
    analyzer = TemporalAnalyzer("signatures.db")
    
    # Analyze single signature
    analysis = analyzer.analyze_signature("player_health_v1")
    
    print(f"Pass Rate: {analysis['pass_rate']:.1%}")
    print(f"Stability: {analysis['stability_assessment']}")
    print(f"Confidence Interval:")
    print(f"  Current: {analysis['confidence_interval']['current']:.2f}")
    print(f"  Pessimistic: {analysis['confidence_interval']['pessimistic']:.2f}")
    print(f"  Optimistic: {analysis['confidence_interval']['optimistic']:.2f}")
    print(f"Recommendation: {analysis['recommendation']}")
    
    # Analyze all signatures
    all_analyses = analyzer.analyze_all()
    
    # Find fragile signatures
    fragile = [a for a in all_analyses if a['stability_assessment'] == 'fragile']
    print(f"\nFragile signatures: {len(fragile)}")
    for a in fragile:
        print(f"  - {a['signature_id']} (pass rate: {a['pass_rate']:.1%})")


def example_complete_workflow():
    """Example 7: Complete end-to-end workflow."""
    print("\n=== Example 7: Complete Workflow ===")
    
    # Step 1: Generate signatures for multiple versions
    print("Step 1: Generating signatures...")
    synth = Synthesizer("game_v1.0.exe")
    result = synth.generate(
        anchor_rva="0x123456",
        version_binaries=["game_v1.1.exe", "game_v1.2.exe"],
        profile="balanced",
        explain=True
    )
    
    if not result.ok:
        print("Synthesis failed!")
        return
    
    # Step 2: Save to database
    print("Step 2: Saving to database...")
    db = SignatureDatabase("signatures.db")
    db.init()
    
    top = result.get_top_candidate()
    if top:
        db.save_signature(
            signature_id="example_sig_001",
            name="Example Signature",
            pattern=top["aob"],
            anchor_rva="0x123456",
            metadata={"score": top["score"]["score"]}
        )
    
    # Step 3: Test against corpus
    print("Step 3: Testing against corpus...")
    tester = SignatureTester("signatures.db")
    test_results = tester.test_all(
        corpus_pattern="binaries/*.exe",
        signature_id="example_sig_001",
        record=True
    )
    
    if test_results['summary']['failed'] > 0:
        print("Some tests failed!")
        for failure in test_results['results']:
            if not failure['passed']:
                print(f"  {failure['binary_path']}: {failure['failure_reason']}")
    
    # Step 4: Analyze temporal trends
    print("Step 4: Analyzing temporal trends...")
    analyzer = TemporalAnalyzer("signatures.db")
    analysis = analyzer.analyze_signature("example_sig_001")
    
    print(f"Stability: {analysis['stability_assessment']}")
    print(f"Pass Rate: {analysis['pass_rate']:.1%}")
    print(f"Recommendation: {analysis['recommendation']}")
    
    # Step 5: Export for sharing
    print("Step 5: Exporting database...")
    db.export_signatures("signatures_export.json")
    
    print("\nWorkflow complete!")


if __name__ == "__main__":
    print("AoBMaster SDK Examples")
    print("=" * 60)
    
    # Note: These examples assume binaries exist
    # Comment out examples as needed for testing
    
    try:
        # example_basic_synthesis()
        # example_multi_version_synthesis()
        # example_structural_anchoring()
        # example_database_workflow()
        # example_testing_workflow()
        # example_temporal_analysis()
        # example_complete_workflow()
        
        print("\n" + "=" * 60)
        print("SDK examples complete!")
        print("Note: SDK is currently a placeholder.")
        print("Full SDK implementation requires refactoring synth.py")
        print("to return data instead of printing to stdout.")
    except NotImplementedError as e:
        print(f"\n{e}")
    except Exception as e:
        print(f"\nError: {e}")
