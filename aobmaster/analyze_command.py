"""
Analyze command for temporal analysis.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .database import SignatureDatabase
from .errors import AoBMasterError, ExitCode
from .output import emit_json, emit_text
from .temporal import analyze_signature_temporal, predict_breakage_likelihood


def run_analyze(args: Any) -> int:
    """
    Analyze signature stability using historical test data.
    
    Usage:
        aobmaster analyze --db signatures.db --signature sig_abc
        aobmaster analyze --db signatures.db  # Analyze all
    """
    db_path = Path(args.db)
    
    if not db_path.exists():
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "database_not_found",
            f"Database not found: {db_path}",
            {"path": str(db_path)},
        )
    
    db = SignatureDatabase(db_path)
    db.init_database()
    conn = db._connect()
    
    # Get signatures to analyze
    if hasattr(args, 'signature_id') and args.signature_id:
        sig = db.get_signature(args.signature_id)
        if not sig:
            db.close()
            raise AoBMasterError(
                ExitCode.INVALID_ARGS,
                "signature_not_found",
                f"Signature not found: {args.signature_id}",
            )
        signatures = [sig]
    else:
        signatures = db.list_signatures()
    
    if not signatures:
        db.close()
        raise AoBMasterError(
            ExitCode.INVALID_ARGS,
            "no_signatures",
            "No signatures found in database",
        )
    
    # Analyze each signature
    analyses = []
    for sig in signatures:
        analysis = analyze_signature_temporal(conn, sig.id)
        prediction = predict_breakage_likelihood(analysis)
        analyses.append({
            "signature": sig.to_dict(),
            "analysis": analysis.to_dict(),
            "breakage_prediction": prediction,
        })
    
    db.close()
    
    # Output results
    if args.format == "json":
        emit_json({
            "ok": True,
            "analyses": analyses,
        })
    else:
        lines = []
        for item in analyses:
            sig = item["signature"]
            analysis = item["analysis"]
            prediction = item["breakage_prediction"]
            
            lines.append(f"Signature: {sig['name']} ({sig['id']})")
            lines.append(f"  Pattern: {sig['pattern']}")
            lines.append(f"  Historical Tests: {analysis['total_tests']}")
            lines.append(f"  Pass Rate: {analysis['pass_rate']:.1%}")
            lines.append(f"  Stability: {analysis['stability_assessment']}")
            
            ci = analysis['confidence_interval']
            lines.append(f"  Confidence Interval:")
            lines.append(f"    Current: {ci['current']:.3f}")
            lines.append(f"    Pessimistic: {ci['pessimistic_lower_bound']:.3f}")
            lines.append(f"    Optimistic: {ci['optimistic_upper_bound']:.3f}")
            
            lines.append(f"  Breakage Prediction: {prediction['likelihood']} (confidence: {prediction['confidence']:.1%})")
            lines.append(f"  Recommendation: {analysis['recommendation']}")
            lines.append("")
        
        emit_text(lines)
    
    return 0
