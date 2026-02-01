"""
Temporal analysis for AoBMaster v2.

Analyzes signature behavior over time using historical test results.
Provides drift tracking and confidence intervals.

v2.1 Phase 3: Enhanced with trend detection, moving averages, confidence calibration,
and predictive alerts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, List, Tuple
import statistics

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
        stability_assessment = "moderately_stable"
        recommendation = "Signature generally works but has occasional failures. Review failure patterns."
    elif pass_rate >= 0.5:
        stability_assessment = "fragile"
        recommendation = "Signature is fragile. Consider regenerating with different anchor or profile."
    else:
        stability_assessment = "unstable"
        recommendation = "Signature is highly unstable. Regenerate immediately with different anchor or profile."
    
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


# ============================================================================
# Phase 3 Enhancements: Trend Analysis, Confidence Calibration, Alerts
# ============================================================================

@dataclass
class TrendAnalysis:
    """Enhanced trend analysis with moving averages (v2.1 Phase 3)."""
    
    trend: str  # "stable", "improving", "degrading", "volatile"
    slope: float  # Change in pass rate per test
    moving_average: List[float]  # Moving average of pass rates
    volatility: float  # Standard deviation of recent pass rates
    confidence: float  # Confidence in trend prediction (0-1)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "trend": self.trend,
            "slope": round(self.slope, 4),
            "moving_average_latest": round(self.moving_average[-1], 3) if self.moving_average else 0.0,
            "volatility": round(self.volatility, 3),
            "confidence": round(self.confidence, 3),
        }


@dataclass
class PredictiveAlert:
    """Alert based on temporal analysis (v2.1 Phase 3)."""
    
    alert_type: str  # "breakage_imminent", "high_volatility", "regeneration_suggested", "info"
    severity: str  # "critical", "warning", "info"
    message: str  # Human-readable message
    recommendation: str  # Actionable recommendation
    confidence: float  # Confidence in alert (0-1)
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_type": self.alert_type,
            "severity": self.severity,
            "message": self.message,
            "recommendation": self.recommendation,
            "confidence": round(self.confidence, 3),
        }


def calculate_moving_average(
    values: List[float],
    window_size: int = 5
) -> List[float]:
    """
    Calculate moving average of values.
    
    Args:
        values: List of values to average
        window_size: Size of moving window (default: 5)
        
    Returns:
        List of moving averages
    """
    if not values:
        return []
    
    if len(values) < window_size:
        window_size = len(values)
    
    moving_avg = []
    for i in range(len(values)):
        start_idx = max(0, i - window_size + 1)
        window = values[start_idx:i + 1]
        moving_avg.append(sum(window) / len(window))
    
    return moving_avg


def analyze_trend(
    test_results: List[Tuple[bool, str]],  # (passed, test_date)
    window_size: int = 5
) -> TrendAnalysis:
    """
    Analyze trend in test results with moving averages.
    
    Args:
        test_results: List of (passed, test_date) tuples
        window_size: Window size for moving average
        
    Returns:
        TrendAnalysis with trend information
    """
    if not test_results:
        return TrendAnalysis(
            trend="unknown",
            slope=0.0,
            moving_average=[],
            volatility=0.0,
            confidence=0.0,
        )
    
    # Convert pass/fail to numerical values
    pass_values = [1.0 if r[0] else 0.0 for r in test_results]
    
    # Calculate moving average
    moving_avg = calculate_moving_average(pass_values, window_size)
    
    # Calculate slope (trend direction)
    if len(moving_avg) >= 2:
        # Use simple linear regression on moving average
        n = len(moving_avg)
        x = list(range(n))
        y = moving_avg
        
        # Calculate slope: (n*Σxy - Σx*Σy) / (n*Σx² - (Σx)²)
        sum_x = sum(x)
        sum_y = sum(y)
        sum_xy = sum(x[i] * y[i] for i in range(n))
        sum_x_squared = sum(xi * xi for xi in x)
        
        denominator = n * sum_x_squared - sum_x * sum_x
        if denominator != 0:
            slope = (n * sum_xy - sum_x * sum_y) / denominator
        else:
            slope = 0.0
    else:
        slope = 0.0
    
    # Calculate volatility (standard deviation of recent results)
    recent_window = pass_values[-window_size:] if len(pass_values) >= window_size else pass_values
    if len(recent_window) > 1:
        volatility = statistics.stdev(recent_window)
    else:
        volatility = 0.0
    
    # Determine trend category
    if volatility > 0.4:
        trend = "volatile"
        confidence = 0.4
    elif slope > 0.02:
        trend = "improving"
        confidence = 0.7
    elif slope < -0.02:
        trend = "degrading"
        confidence = 0.7
    else:
        trend = "stable"
        confidence = 0.8
    
    # Adjust confidence based on sample size
    sample_factor = min(1.0, len(test_results) / 10.0)
    confidence = confidence * (0.5 + 0.5 * sample_factor)
    
    return TrendAnalysis(
        trend=trend,
        slope=slope,
        moving_average=moving_avg,
        volatility=volatility,
        confidence=confidence,
    )


def calibrate_confidence_enhanced(
    signature_data: dict[str, Any],
    test_results: List[Tuple[bool, str]]
) -> dict[str, Any]:
    """
    Calibrate confidence based on multiple factors (v2.1 Phase 3).
    
    Factors considered:
    - Test sample size (more tests = higher confidence)
    - Pattern specificity (lower wildcard ratio = higher confidence)
    - Historical volatility (stable history = higher confidence)
    - Pattern length (longer patterns = more stable)
    
    Args:
        signature_data: Signature metadata (pattern, etc.)
        test_results: Historical test results
        
    Returns:
        Dict with calibrated confidence intervals and factors
    """
    # Calculate base confidence from pass rate
    if not test_results:
        return {
            "current": 0.5,
            "pessimistic": 0.0,
            "optimistic": 1.0,
            "calibration_score": 0.0,
            "factors": {"sample_size": 0.0},
        }
    
    pass_values = [1.0 if r[0] else 0.0 for r in test_results]
    pass_rate = sum(pass_values) / len(pass_values)
    
    # Factor 1: Sample size (more data = higher confidence)
    sample_size_factor = min(1.0, len(test_results) / 20.0)
    
    # Factor 2: Pattern specificity (from wildcard ratio if available)
    pattern = signature_data.get("pattern", "")
    if pattern:
        wildcard_count = pattern.count("??")
        total_bytes = len(pattern.split())
        wildcard_ratio = wildcard_count / max(1, total_bytes)
        specificity_factor = 1.0 - wildcard_ratio
    else:
        specificity_factor = 0.5
    
    # Factor 3: Historical volatility
    if len(pass_values) > 1:
        volatility = statistics.stdev(pass_values)
        stability_factor = 1.0 - min(1.0, volatility)
    else:
        stability_factor = 0.5
    
    # Factor 4: Pattern length
    pattern_length = len(pattern.split()) if pattern else 0
    length_factor = min(1.0, pattern_length / 20.0)  # 20 bytes = 1.0
    
    # Combine factors (weighted average)
    factors = {
        "sample_size": sample_size_factor,
        "specificity": specificity_factor,
        "stability": stability_factor,
        "pattern_length": length_factor,
    }
    
    # Calculate calibration score (average of factors)
    calibration_score = sum(factors.values()) / len(factors)
    
    # Calculate confidence intervals
    # Base interval width on calibration score (better calibration = narrower interval)
    interval_width = 0.3 * (1.0 - calibration_score * 0.5)
    
    current = pass_rate
    pessimistic = max(0.0, current - interval_width)
    optimistic = min(1.0, current + interval_width * 0.5)
    
    return {
        "current": round(current, 3),
        "pessimistic": round(pessimistic, 3),
        "optimistic": round(optimistic, 3),
        "calibration_score": round(calibration_score, 3),
        "factors": {k: round(v, 3) for k, v in factors.items()},
    }


def generate_predictive_alerts(
    signature_id: str,
    trend: TrendAnalysis,
    pass_rate: float,
    total_tests: int,
    calibration_score: float = 0.5
) -> List[PredictiveAlert]:
    """
    Generate actionable alerts based on temporal analysis (v2.1 Phase 3).
    
    Alert types:
    - breakage_imminent: Pass rate < 70% or rapid decline
    - high_volatility: Large variance in test results
    - regeneration_suggested: Pattern can be improved
    - info: General status update
    
    Args:
        signature_id: Signature identifier
        trend: Trend analysis
        pass_rate: Current pass rate
        total_tests: Number of tests
        calibration_score: Confidence calibration score
        
    Returns:
        List of predictive alerts
    """
    alerts = []
    
    # Alert 1: Breakage imminent
    if pass_rate < 0.7 or (trend.trend == "degrading" and trend.slope < -0.05):
        alerts.append(PredictiveAlert(
            alert_type="breakage_imminent",
            severity="critical",
            message=f"Signature '{signature_id}' showing signs of instability",
            recommendation="Regenerate signature with different anchor point or use 'balanced' profile",
            confidence=0.8 if pass_rate < 0.5 else 0.6,
        ))
    
    # Alert 2: High volatility
    if trend.volatility > 0.4:
        alerts.append(PredictiveAlert(
            alert_type="high_volatility",
            severity="warning",
            message=f"Signature '{signature_id}' has high test result volatility",
            recommendation="Review test corpus for version-specific issues or consider multi-version synthesis",
            confidence=trend.confidence,
        ))
    
    # Alert 3: Low confidence/calibration
    if calibration_score < 0.5:
        if total_tests < 5:
            alerts.append(PredictiveAlert(
                alert_type="insufficient_data",
                severity="info",
                message=f"Signature '{signature_id}' has limited test history ({total_tests} tests)",
                recommendation="Run more tests to improve confidence in stability assessment",
                confidence=0.9,
            ))
        else:
            alerts.append(PredictiveAlert(
                alert_type="regeneration_suggested",
                severity="warning",
                message=f"Signature '{signature_id}' has low confidence score",
                recommendation="Regenerate with 'specific' profile for better stability",
                confidence=0.7,
            ))
    
    # Alert 4: Positive stability (only if doing well)
    if pass_rate >= 0.9 and trend.trend in ("stable", "improving") and total_tests >= 5:
        alerts.append(PredictiveAlert(
            alert_type="stable",
            severity="info",
            message=f"Signature '{signature_id}' is stable with {pass_rate*100:.1f}% pass rate",
            recommendation="Continue monitoring. No action needed.",
            confidence=calibration_score,
        ))
    
    return alerts


def generate_trend_chart(
    test_results: List[Tuple[bool, str]],
    width: int = 60,
    height: int = 10
) -> str:
    """
    Generate ASCII-art chart of pass rate trends (v2.1 Phase 3).
    
    Args:
        test_results: List of (passed, test_date) tuples
        width: Chart width in characters
        height: Chart height in lines
        
    Returns:
        ASCII chart string
    """
    if not test_results:
        return "No test data available for visualization."
    
    # Convert to pass rate values
    pass_values = [1.0 if r[0] else 0.0 for r in test_results]
    
    # Calculate moving average for smoother visualization
    moving_avg = calculate_moving_average(pass_values, window_size=3)
    
    # Prepare chart
    chart_lines = []
    
    # Title
    chart_lines.append(f"Pass Rate Over Time ({len(test_results)} tests)")
    chart_lines.append("")
    
    # Scale values to chart height
    max_val = 1.0
    min_val = 0.0
    
    # Create chart grid
    for row in range(height):
        # Calculate percentage for this row
        pct = max_val - (row / (height - 1)) * (max_val - min_val)
        label = f"{pct*100:3.0f}%"
        
        # Build row
        line = label + " "
        
        # Add vertical axis
        if row == 0:
            line += "┬"
        elif row == height - 1:
            line += "┴"
        else:
            line += "┤"
        
        # Plot data points
        for i, val in enumerate(moving_avg):
            col = int((i / max(1, len(moving_avg) - 1)) * (width - 1))
            if col >= len(line) - 6:
                # Determine if point should be plotted at this height
                val_row = int((max_val - val) / (max_val - min_val) * (height - 1))
                if val_row == row:
                    # Extend line to this position if needed
                    while len(line) < col + 6:
                        line += " "
                    if len(line) == col + 6:
                        line += "●"
                    else:
                        if line[col + 5] == " ":
                            line = line[:col + 5] + "●" + line[col + 6:]
        
        chart_lines.append(line)
    
    # Add horizontal axis labels
    chart_lines.append("     " + "└" + "─" * (width - 1))
    
    # Add trend summary
    trend_analysis = analyze_trend(test_results)
    chart_lines.append("")
    chart_lines.append(f"Trend: {trend_analysis.trend.capitalize()} (slope: {trend_analysis.slope:.4f})")
    
    if trend_analysis.trend == "degrading":
        chart_lines.append("⚠️  Warning: Signature stability is declining")
    elif trend_analysis.trend == "volatile":
        chart_lines.append("⚠️  Warning: High volatility detected")
    elif trend_analysis.trend == "stable":
        chart_lines.append("✓  Signature appears stable")
    
    return "\n".join(chart_lines)
