"""
Enhanced temporal analysis for AoBMaster v2.1 Phase 3.

Adds trend detection, moving averages, confidence calibration, and predictive alerts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Optional, Tuple
import sqlite3
import statistics


@dataclass
class TrendAnalysis:
    """Enhanced trend analysis with moving averages."""
    
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
    """Alert based on temporal analysis."""
    
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


@dataclass
class CalibratedConfidence:
    """Enhanced confidence with calibration factors."""
    
    current: float  # Current confidence
    pessimistic: float  # 95th percentile lower bound
    optimistic: float  # 95th percentile upper bound
    calibration_score: float  # Model calibration quality (0-1)
    factors: dict[str, float]  # Contributing factors
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "current": round(self.current, 3),
            "pessimistic": round(self.pessimistic, 3),
            "optimistic": round(self.optimistic, 3),
            "calibration_score": round(self.calibration_score, 3),
            "factors": {k: round(v, 3) for k, v in self.factors.items()},
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


def calibrate_confidence(
    signature_data: dict[str, Any],
    test_results: List[Tuple[bool, str]],
    global_stats: Optional[dict[str, Any]] = None
) -> CalibratedConfidence:
    """
    Calibrate confidence based on multiple factors.
    
    Factors considered:
    - Test sample size (more tests = higher confidence)
    - Pattern specificity (lower wildcard ratio = higher confidence)
    - Historical volatility (stable history = higher confidence)
    - Pattern length (longer patterns = more stable)
    
    Args:
        signature_data: Signature metadata (pattern, etc.)
        test_results: Historical test results
        global_stats: Optional global statistics for calibration
        
    Returns:
        CalibratedConfidence with calibrated intervals
    """
    # Calculate base confidence from pass rate
    if not test_results:
        return CalibratedConfidence(
            current=0.5,
            pessimistic=0.0,
            optimistic=1.0,
            calibration_score=0.0,
            factors={"sample_size": 0.0},
        )
    
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
    
    return CalibratedConfidence(
        current=current,
        pessimistic=pessimistic,
        optimistic=optimistic,
        calibration_score=calibration_score,
        factors=factors,
    )


def generate_predictive_alerts(
    signature_id: str,
    trend: TrendAnalysis,
    confidence: CalibratedConfidence,
    pass_rate: float,
    total_tests: int
) -> List[PredictiveAlert]:
    """
    Generate actionable alerts based on temporal analysis.
    
    Alert types:
    - breakage_imminent: Pass rate < 70% or rapid decline
    - high_volatility: Large variance in test results
    - regeneration_suggested: Pattern can be improved
    - info: General status update
    
    Args:
        signature_id: Signature identifier
        trend: Trend analysis
        confidence: Calibrated confidence
        pass_rate: Current pass rate
        total_tests: Number of tests
        
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
    if confidence.calibration_score < 0.5:
        if total_tests < 5:
            alerts.append(PredictiveAlert(
                alert_type="insufficient_data",
                severity="info",
                message=f"Signature '{signature_id}' has limited test history ({total_tests} tests)",
                recommendation="Run more tests to improve confidence in stability assessment",
                confidence=0.9,
            ))
        elif confidence.factors.get("specificity", 1.0) < 0.5:
            alerts.append(PredictiveAlert(
                alert_type="regeneration_suggested",
                severity="warning",
                message=f"Signature '{signature_id}' has high wildcard ratio",
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
            confidence=confidence.calibration_score,
        ))
    
    return alerts


def generate_trend_chart(
    test_results: List[Tuple[bool, str]],
    width: int = 60,
    height: int = 10
) -> str:
    """
    Generate ASCII-art chart of pass rate trends.
    
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
