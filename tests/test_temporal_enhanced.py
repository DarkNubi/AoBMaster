"""
Tests for Phase 3 Temporal Analysis Enhancements (v2.1)

Tests trend detection, moving averages, confidence calibration, and predictive alerts.
"""

import pytest
from aobmaster.temporal import (
    calculate_moving_average,
    analyze_trend,
    calibrate_confidence_enhanced,
    generate_predictive_alerts,
    generate_trend_chart,
    TrendAnalysis,
    PredictiveAlert,
)


def test_moving_average_basic():
    """Test basic moving average calculation."""
    values = [1.0, 2.0, 3.0, 4.0, 5.0]
    result = calculate_moving_average(values, window_size=3)
    
    assert len(result) == 5
    assert result[0] == 1.0  # [1.0]
    assert result[1] == 1.5  # [1.0, 2.0]
    assert result[2] == 2.0  # [1.0, 2.0, 3.0]
    assert result[3] == 3.0  # [2.0, 3.0, 4.0]
    assert result[4] == 4.0  # [3.0, 4.0, 5.0]


def test_moving_average_empty():
    """Test moving average with empty input."""
    result = calculate_moving_average([])
    assert result == []


def test_moving_average_single_value():
    """Test moving average with single value."""
    result = calculate_moving_average([5.0], window_size=3)
    assert result == [5.0]


def test_analyze_trend_stable():
    """Test trend analysis with stable data."""
    # Stable pass rate around 95% with consistent pattern
    test_results = [(True, f"2024-01-{i+1:02d}") for i in range(10)]
    test_results[4] = (False, "2024-01-05")  # One failure in the middle
    
    trend = analyze_trend(test_results, window_size=5)
    
    assert trend.trend == "stable"
    assert abs(trend.slope) < 0.05  # Near zero slope
    assert len(trend.moving_average) == 10
    assert trend.volatility < 0.5


def test_analyze_trend_degrading():
    """Test trend analysis with degrading pass rate."""
    # Pass rate declining from 100% to 0%
    test_results = (
        [(True, "2024-01-01")] * 5 +
        [(True, "2024-01-05"), (False, "2024-01-06")] * 3 +
        [(False, "2024-01-10")] * 5
    )
    
    trend = analyze_trend(test_results, window_size=5)
    
    assert trend.trend in ("degrading", "volatile")
    assert trend.slope < 0  # Negative slope


def test_analyze_trend_improving():
    """Test trend analysis with improving pass rate."""
    # Pass rate improving from 0% to 100%
    test_results = (
        [(False, "2024-01-01")] * 5 +
        [(False, "2024-01-05"), (True, "2024-01-06")] * 3 +
        [(True, "2024-01-10")] * 5
    )
    
    trend = analyze_trend(test_results, window_size=5)
    
    assert trend.trend in ("improving", "volatile")
    assert trend.slope > 0  # Positive slope


def test_analyze_trend_volatile():
    """Test trend analysis with volatile data."""
    # Alternating pass/fail
    test_results = [(True if i % 2 == 0 else False, f"2024-01-{i+1:02d}") 
                    for i in range(10)]
    
    trend = analyze_trend(test_results, window_size=5)
    
    assert trend.volatility > 0.3  # High volatility
    assert trend.confidence < 0.7  # Lower confidence due to volatility


def test_analyze_trend_empty():
    """Test trend analysis with no data."""
    trend = analyze_trend([], window_size=5)
    
    assert trend.trend == "unknown"
    assert trend.slope == 0.0
    assert trend.moving_average == []
    assert trend.confidence == 0.0


def test_calibrate_confidence_high_quality():
    """Test confidence calibration with high-quality signature."""
    signature_data = {
        "pattern": "48 8B 05 12 34 56 78 89 C0 C3 48 89 5C 24 08 48 89 74 24 10",  # Long, specific
    }
    
    # Many successful tests
    test_results = [(True, f"2024-01-{i+1:02d}") for i in range(20)]
    
    result = calibrate_confidence_enhanced(signature_data, test_results)
    
    assert result["current"] >= 0.95  # High pass rate
    assert result["calibration_score"] > 0.7  # Good calibration
    assert result["factors"]["sample_size"] == 1.0  # Full sample
    assert result["factors"]["specificity"] == 1.0  # No wildcards


def test_calibrate_confidence_low_quality():
    """Test confidence calibration with low-quality signature."""
    signature_data = {
        "pattern": "?? ?? ?? ??",  # Short, many wildcards
    }
    
    # Few tests
    test_results = [(True, "2024-01-01"), (False, "2024-01-02")]
    
    result = calibrate_confidence_enhanced(signature_data, test_results)
    
    assert result["calibration_score"] < 0.5  # Poor calibration
    assert result["factors"]["sample_size"] < 0.2  # Small sample
    assert result["factors"]["specificity"] == 0.0  # All wildcards


def test_calibrate_confidence_no_data():
    """Test confidence calibration with no test data."""
    signature_data = {"pattern": "48 8B 05"}
    
    result = calibrate_confidence_enhanced(signature_data, [])
    
    assert result["current"] == 0.5
    assert result["calibration_score"] == 0.0


def test_generate_predictive_alerts_critical():
    """Test predictive alert generation for critical situation."""
    trend = TrendAnalysis(
        trend="degrading",
        slope=-0.1,
        moving_average=[1.0, 0.8, 0.6, 0.4, 0.2],
        volatility=0.2,
        confidence=0.7,
    )
    
    alerts = generate_predictive_alerts(
        signature_id="test_sig",
        trend=trend,
        pass_rate=0.4,
        total_tests=10,
        calibration_score=0.6
    )
    
    # Should generate breakage imminent alert
    assert len(alerts) > 0
    alert_types = [a.alert_type for a in alerts]
    assert "breakage_imminent" in alert_types
    
    # Critical alert should exist
    critical_alerts = [a for a in alerts if a.severity == "critical"]
    assert len(critical_alerts) > 0


def test_generate_predictive_alerts_volatile():
    """Test predictive alert generation for high volatility."""
    trend = TrendAnalysis(
        trend="volatile",
        slope=0.0,
        moving_average=[1.0, 0.0, 1.0, 0.0, 1.0],
        volatility=0.5,
        confidence=0.4,
    )
    
    alerts = generate_predictive_alerts(
        signature_id="test_sig",
        trend=trend,
        pass_rate=0.5,
        total_tests=10,
        calibration_score=0.5
    )
    
    # Should generate high volatility alert
    alert_types = [a.alert_type for a in alerts]
    assert "high_volatility" in alert_types


def test_generate_predictive_alerts_stable():
    """Test predictive alert generation for stable signature."""
    trend = TrendAnalysis(
        trend="stable",
        slope=0.0,
        moving_average=[1.0] * 10,
        volatility=0.0,
        confidence=0.9,
    )
    
    alerts = generate_predictive_alerts(
        signature_id="test_sig",
        trend=trend,
        pass_rate=1.0,
        total_tests=10,
        calibration_score=0.9
    )
    
    # Should generate stable/info alert
    alert_types = [a.alert_type for a in alerts]
    assert "stable" in alert_types
    
    # Should be info severity
    stable_alerts = [a for a in alerts if a.alert_type == "stable"]
    assert stable_alerts[0].severity == "info"


def test_generate_predictive_alerts_insufficient_data():
    """Test predictive alert generation with insufficient data."""
    trend = TrendAnalysis(
        trend="stable",
        slope=0.0,
        moving_average=[1.0, 1.0],
        volatility=0.0,
        confidence=0.5,
    )
    
    alerts = generate_predictive_alerts(
        signature_id="test_sig",
        trend=trend,
        pass_rate=1.0,
        total_tests=2,  # Very few tests
        calibration_score=0.3  # Low calibration
    )
    
    # Should recommend more tests
    alert_types = [a.alert_type for a in alerts]
    assert "insufficient_data" in alert_types


def test_generate_trend_chart_basic():
    """Test ASCII trend chart generation."""
    test_results = [(True, f"2024-01-{i+1:02d}") for i in range(10)]
    
    chart = generate_trend_chart(test_results, width=40, height=8)
    
    assert "Pass Rate Over Time" in chart
    assert "10 tests" in chart
    assert "Trend:" in chart
    assert len(chart.split("\n")) > 5  # Multiple lines


def test_generate_trend_chart_degrading():
    """Test trend chart with degrading pattern."""
    # Declining pass rate
    test_results = (
        [(True, f"2024-01-{i+1:02d}") for i in range(5)] +
        [(False, f"2024-01-{i+6:02d}") for i in range(5)]
    )
    
    chart = generate_trend_chart(test_results)
    
    assert "degrading" in chart.lower() or "declining" in chart.lower()
    assert "⚠️" in chart  # Warning symbol


def test_generate_trend_chart_stable():
    """Test trend chart with stable pattern."""
    test_results = [(True, f"2024-01-{i+1:02d}") for i in range(15)]
    
    chart = generate_trend_chart(test_results)
    
    assert "stable" in chart.lower()
    assert "✓" in chart  # Check mark


def test_generate_trend_chart_empty():
    """Test trend chart with no data."""
    chart = generate_trend_chart([])
    
    assert "No test data available" in chart


def test_trend_analysis_to_dict():
    """Test TrendAnalysis serialization."""
    trend = TrendAnalysis(
        trend="stable",
        slope=0.001,
        moving_average=[0.9, 0.95, 1.0],
        volatility=0.05,
        confidence=0.85,
    )
    
    result = trend.to_dict()
    
    assert result["trend"] == "stable"
    assert "slope" in result
    assert "moving_average_latest" in result
    assert "volatility" in result
    assert "confidence" in result
    
    # Check rounding
    assert isinstance(result["slope"], float)
    assert isinstance(result["confidence"], float)


def test_predictive_alert_to_dict():
    """Test PredictiveAlert serialization."""
    alert = PredictiveAlert(
        alert_type="breakage_imminent",
        severity="critical",
        message="Test message",
        recommendation="Test recommendation",
        confidence=0.85,
    )
    
    result = alert.to_dict()
    
    assert result["alert_type"] == "breakage_imminent"
    assert result["severity"] == "critical"
    assert result["message"] == "Test message"
    assert result["recommendation"] == "Test recommendation"
    assert isinstance(result["confidence"], float)


def test_moving_average_window_larger_than_data():
    """Test moving average when window is larger than data."""
    values = [1.0, 2.0, 3.0]
    result = calculate_moving_average(values, window_size=10)
    
    # Should adapt to data size
    assert len(result) == 3
    assert result[0] == 1.0
    assert result[1] == 1.5
    assert result[2] == 2.0


def test_calibrate_confidence_no_pattern():
    """Test confidence calibration without pattern data."""
    signature_data = {}  # No pattern
    test_results = [(True, "2024-01-01")] * 5
    
    result = calibrate_confidence_enhanced(signature_data, test_results)
    
    assert "factors" in result
    assert "specificity" in result["factors"]
    # Should use default values
    assert result["factors"]["specificity"] == 0.5
