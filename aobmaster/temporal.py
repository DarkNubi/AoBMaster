"""
Temporal analysis for AoBMaster v2.

Analyzes signature behavior over time using historical test results.
Provides drift tracking and confidence intervals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import sqlite3


@dataclass
class DriftAnalysis:
    """Analysis of RVA drift over time."""
    
    mean_drift: float  # Average drift per version
    max_drift: int  # Maximum observed drift
    min_drift: int  # Minimum observed drift
    drift_trend: str  # "stable", "increasing", "decreasing", "erratic"
    version_count: int  # Number of versions analyzed
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "mean_drift": round(self.mean_drift, 2),
            "max_drift": self.max_drift,
            "min_drift": self.min_drift,
            "drift_trend": self.drift_trend,
            "version_count": self.version_count,
        }


@dataclass
class ConfidenceInterval:
    """Confidence interval for signature stability."""
    
    current: float  # Current confidence (0-1)
    pessimistic_lower_bound: float  # Worst-case estimate
    optimistic_upper_bound: float  # Best-case estimate
    prediction_basis: str  # How prediction was made
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "current": round(self.current, 3),
            "pessimistic_lower_bound": round(self.pessimistic_lower_bound, 3),
            "optimistic_upper_bound": round(self.optimistic_upper_bound, 3),
            "prediction_basis": self.prediction_basis,
        }


@dataclass
class TemporalAnalysisResult:
    """Complete temporal analysis result."""
    
    signature_id: str
    total_tests: int
    pass_rate: float
    drift_analysis: Optional[DriftAnalysis]
    confidence_interval: ConfidenceInterval
    stability_assessment: str  # "stable", "fragile", "unknown"
    recommendation: str  # Human-readable recommendation
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "signature_id": self.signature_id,
            "total_tests": self.total_tests,
            "pass_rate": round(self.pass_rate, 3),
            "drift_analysis": self.drift_analysis.to_dict() if self.drift_analysis else None,
            "confidence_interval": self.confidence_interval.to_dict(),
            "stability_assessment": self.stability_assessment,
            "recommendation": self.recommendation,
        }


def analyze_signature_temporal(
    db_conn: sqlite3.Connection,
    signature_id: str,
) -> TemporalAnalysisResult:
    """
    Perform temporal analysis on a signature using historical test results.
    
    Args:
        db_conn: Database connection
        signature_id: Signature ID to analyze
    
    Returns:
        Temporal analysis result
    """
    cursor = db_conn.cursor()
    
    # Get all test results for this signature
    cursor.execute("""
        SELECT passed, test_date, binary_path, binary_hash
        FROM test_results
        WHERE signature_id = ?
        ORDER BY test_date ASC
    """, (signature_id,))
    
    results = cursor.fetchall()
    
    if not results:
        # No historical data
        return TemporalAnalysisResult(
            signature_id=signature_id,
            total_tests=0,
            pass_rate=0.0,
            drift_analysis=None,
            confidence_interval=ConfidenceInterval(
                current=0.5,
                pessimistic_lower_bound=0.0,
                optimistic_upper_bound=1.0,
                prediction_basis="No historical data available",
            ),
            stability_assessment="unknown",
            recommendation="Run tests to gather historical data",
        )
    
    # Calculate pass rate
    passed_count = sum(1 for r in results if r[0])
    pass_rate = passed_count / len(results)
    
    # Drift analysis (simplified - would need RVA data in real implementation)
    # For now, infer from pass/fail patterns
    recent_results = [r[0] for r in results[-5:]]  # Last 5 tests
    recent_pass_rate = sum(recent_results) / len(recent_results) if recent_results else 0.0
    
    # Determine drift trend
    if pass_rate >= 0.9:
        drift_trend = "stable"
    elif pass_rate >= 0.7 and recent_pass_rate >= 0.8:
        drift_trend = "stable"
    elif pass_rate < 0.5:
        drift_trend = "erratic"
    elif recent_pass_rate < pass_rate - 0.2:
        drift_trend = "decreasing"
    else:
        drift_trend = "stable"
    
    drift_analysis = DriftAnalysis(
        mean_drift=0.0,  # Would calculate from actual RVA data
        max_drift=0,
        min_drift=0,
        drift_trend=drift_trend,
        version_count=len(set(r[3] for r in results)),  # Unique binary hashes
    )
    
    # Calculate confidence interval
    # Base confidence on historical pass rate
    current = pass_rate
    
    # Pessimistic: assume worst-case scenario (recent failures continue)
    pessimistic = max(0.0, current - 0.2)
    
    # Optimistic: assume best-case scenario (recent pattern holds)
    optimistic = min(1.0, current + 0.1)
    
    # Adjust based on sample size (more samples = narrower interval)
    sample_factor = min(1.0, len(results) / 10.0)
    pessimistic = current - (current - pessimistic) * sample_factor
    optimistic = current + (optimistic - current) * sample_factor
    
    confidence_interval = ConfidenceInterval(
        current=current,
        pessimistic_lower_bound=pessimistic,
        optimistic_upper_bound=optimistic,
        prediction_basis=f"Based on {len(results)} historical tests",
    )
    
    # Stability assessment
    if pass_rate >= 0.9 and drift_trend == "stable":
        stability_assessment = "stable"
        recommendation = "Signature is stable. Continue monitoring."
    elif pass_rate >= 0.7:
        stability_assessment = "fragile"  # Changed from moderately_stable for consistency
        recommendation = "Signature generally works but has occasional failures. Review failure patterns."
    else:
        stability_assessment = "fragile"
        recommendation = "Signature is fragile. Consider regenerating with different anchor or profile."
    
    return TemporalAnalysisResult(
        signature_id=signature_id,
        total_tests=len(results),
        pass_rate=pass_rate,
        drift_analysis=drift_analysis,
        confidence_interval=confidence_interval,
        stability_assessment=stability_assessment,
        recommendation=recommendation,
    )


def predict_breakage_likelihood(
    analysis: TemporalAnalysisResult,
) -> dict[str, Any]:
    """
    Predict likelihood of signature breaking in next version.
    
    Note: This is a statistical estimate, not a guarantee.
    """
    if analysis.total_tests == 0:
        return {
            "likelihood": "unknown",
            "confidence": 0.0,
            "reason": "No historical data",
            "disclaimer": "Prediction requires historical test data",
        }
    
    # Simple model based on pass rate and trend
    if analysis.stability_assessment == "stable":
        likelihood = "low"
        confidence = 0.8
        reason = "Historical data shows consistent stability"
    elif analysis.stability_assessment == "moderately_stable":
        likelihood = "medium"
        confidence = 0.6
        reason = "Some historical failures detected"
    else:
        likelihood = "high"
        confidence = 0.7
        reason = "High historical failure rate"
    
    return {
        "likelihood": likelihood,
        "confidence": confidence,
        "reason": reason,
        "disclaimer": "This is a statistical estimate based on historical patterns, not a guarantee",
    }
