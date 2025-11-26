"""
Revolution Alpha Engine - Data Validation Module

Comprehensive validation for:
- DataFrames
- Options chains
- Price data
- Trade signals
- Configuration
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Callable
from datetime import datetime, timedelta
from enum import Enum


class ValidationError(Exception):
    """Raised when validation fails."""

    def __init__(self, message: str, errors: Optional[List[str]] = None):
        self.message = message
        self.errors = errors or []
        super().__init__(self.message)

    def __str__(self):
        if self.errors:
            return f"{self.message}\nErrors:\n" + "\n".join(f"  - {e}" for e in self.errors)
        return self.message


class DataQuality(Enum):
    """Data quality levels."""
    EXCELLENT = "excellent"  # No issues
    GOOD = "good"  # Minor issues
    ACCEPTABLE = "acceptable"  # Some issues but usable
    POOR = "poor"  # Significant issues
    UNUSABLE = "unusable"  # Cannot be used


@dataclass
class ValidationResult:
    """Result of a validation check."""
    is_valid: bool
    quality: DataQuality
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.is_valid

    def raise_if_invalid(self, message: str = "Validation failed"):
        """Raise ValidationError if invalid."""
        if not self.is_valid:
            raise ValidationError(message, self.errors)

    def get_report(self) -> str:
        """Generate validation report."""
        lines = [
            "=" * 50,
            "VALIDATION REPORT",
            "=" * 50,
            f"Valid: {'YES' if self.is_valid else 'NO'}",
            f"Quality: {self.quality.value.upper()}",
        ]

        if self.errors:
            lines.append("\nERRORS:")
            for error in self.errors:
                lines.append(f"  [ERROR] {error}")

        if self.warnings:
            lines.append("\nWARNINGS:")
            for warning in self.warnings:
                lines.append(f"  [WARN] {warning}")

        if self.stats:
            lines.append("\nSTATISTICS:")
            for key, value in self.stats.items():
                lines.append(f"  {key}: {value}")

        lines.append("=" * 50)
        return "\n".join(lines)


def validate_dataframe(
    df: pd.DataFrame,
    required_columns: Optional[List[str]] = None,
    min_rows: int = 1,
    max_null_pct: float = 10.0,
    check_duplicates: bool = True
) -> ValidationResult:
    """
    Validate a pandas DataFrame.

    Args:
        df: DataFrame to validate
        required_columns: List of required column names
        min_rows: Minimum number of rows required
        max_null_pct: Maximum percentage of null values allowed
        check_duplicates: Whether to check for duplicate rows

    Returns:
        ValidationResult
    """
    errors = []
    warnings = []
    stats = {}

    # Check if DataFrame
    if not isinstance(df, pd.DataFrame):
        return ValidationResult(
            is_valid=False,
            quality=DataQuality.UNUSABLE,
            errors=["Input is not a DataFrame"]
        )

    # Check empty
    if df.empty:
        return ValidationResult(
            is_valid=False,
            quality=DataQuality.UNUSABLE,
            errors=["DataFrame is empty"]
        )

    stats['rows'] = len(df)
    stats['columns'] = len(df.columns)

    # Check minimum rows
    if len(df) < min_rows:
        errors.append(f"Insufficient rows: {len(df)} < {min_rows}")

    # Check required columns
    if required_columns:
        missing = set(required_columns) - set(df.columns)
        if missing:
            errors.append(f"Missing required columns: {missing}")

    # Check null values
    null_pcts = (df.isnull().sum() / len(df) * 100).to_dict()
    high_null_cols = {col: pct for col, pct in null_pcts.items() if pct > max_null_pct}
    if high_null_cols:
        errors.append(f"High null percentage in columns: {high_null_cols}")
    stats['null_percentages'] = null_pcts

    # Check duplicates
    if check_duplicates:
        dup_count = df.duplicated().sum()
        if dup_count > 0:
            warnings.append(f"Found {dup_count} duplicate rows")
        stats['duplicate_rows'] = dup_count

    # Determine quality
    if errors:
        quality = DataQuality.UNUSABLE if len(errors) > 2 else DataQuality.POOR
    elif warnings:
        quality = DataQuality.ACCEPTABLE
    else:
        quality = DataQuality.EXCELLENT

    return ValidationResult(
        is_valid=len(errors) == 0,
        quality=quality,
        errors=errors,
        warnings=warnings,
        stats=stats
    )


def validate_options_chain(
    df: pd.DataFrame,
    underlying_price: Optional[float] = None
) -> ValidationResult:
    """
    Validate an options chain DataFrame.

    Args:
        df: Options chain DataFrame
        underlying_price: Current underlying price for sanity checks

    Returns:
        ValidationResult
    """
    errors = []
    warnings = []
    stats = {}

    # Required columns for options
    required = ['strike', 'type', 'bid', 'ask']
    optional = ['delta', 'gamma', 'theta', 'vega', 'iv', 'volume', 'open_interest']

    # Basic DataFrame validation
    base_result = validate_dataframe(df, required_columns=required)
    if not base_result.is_valid:
        return base_result

    # Validate option types
    if 'type' in df.columns:
        valid_types = {'call', 'put', 'c', 'p'}
        invalid_types = set(df['type'].str.lower().unique()) - valid_types
        if invalid_types:
            errors.append(f"Invalid option types: {invalid_types}")

    # Validate strikes
    if 'strike' in df.columns:
        if df['strike'].min() <= 0:
            errors.append("Strike prices must be positive")

        if underlying_price:
            # Check for reasonable strike range
            min_strike_pct = (df['strike'].min() / underlying_price - 1) * 100
            max_strike_pct = (df['strike'].max() / underlying_price - 1) * 100
            stats['strike_range_pct'] = f"{min_strike_pct:.1f}% to {max_strike_pct:.1f}%"

    # Validate bid/ask
    if 'bid' in df.columns and 'ask' in df.columns:
        # Bid should be <= Ask
        invalid_spreads = df[df['bid'] > df['ask']]
        if len(invalid_spreads) > 0:
            errors.append(f"Found {len(invalid_spreads)} rows where bid > ask")

        # Calculate spread statistics
        df_valid = df[df['ask'] > 0]
        if len(df_valid) > 0:
            spreads = ((df_valid['ask'] - df_valid['bid']) / df_valid['ask'] * 100)
            stats['avg_spread_pct'] = f"{spreads.mean():.2f}%"
            stats['max_spread_pct'] = f"{spreads.max():.2f}%"

            if spreads.mean() > 20:
                warnings.append(f"High average spread: {spreads.mean():.1f}%")

    # Validate Greeks if present
    if 'delta' in df.columns:
        calls = df[df['type'].str.lower().isin(['call', 'c'])]
        puts = df[df['type'].str.lower().isin(['put', 'p'])]

        # Call deltas should be 0-1, put deltas should be -1-0
        if len(calls) > 0:
            invalid_call_deltas = calls[(calls['delta'] < 0) | (calls['delta'] > 1)]
            if len(invalid_call_deltas) > 0:
                warnings.append(f"Found {len(invalid_call_deltas)} calls with invalid delta")

        if len(puts) > 0:
            invalid_put_deltas = puts[(puts['delta'] > 0) | (puts['delta'] < -1)]
            if len(invalid_put_deltas) > 0:
                warnings.append(f"Found {len(invalid_put_deltas)} puts with invalid delta")

    # Validate IV if present
    if 'iv' in df.columns:
        if df['iv'].min() < 0:
            errors.append("Implied volatility cannot be negative")
        if df['iv'].max() > 5:  # 500% IV
            warnings.append(f"Very high IV detected: {df['iv'].max()*100:.0f}%")

    # Statistics
    stats['total_contracts'] = len(df)
    stats['calls'] = len(df[df['type'].str.lower().isin(['call', 'c'])]) if 'type' in df.columns else 0
    stats['puts'] = len(df[df['type'].str.lower().isin(['put', 'p'])]) if 'type' in df.columns else 0

    # Determine quality
    if errors:
        quality = DataQuality.POOR
    elif len(warnings) > 2:
        quality = DataQuality.ACCEPTABLE
    elif warnings:
        quality = DataQuality.GOOD
    else:
        quality = DataQuality.EXCELLENT

    return ValidationResult(
        is_valid=len(errors) == 0,
        quality=quality,
        errors=errors,
        warnings=warnings,
        stats=stats
    )


def validate_price_data(
    df: pd.DataFrame,
    check_gaps: bool = True,
    max_gap_pct: float = 10.0
) -> ValidationResult:
    """
    Validate OHLCV price data.

    Args:
        df: Price data DataFrame
        check_gaps: Whether to check for price gaps
        max_gap_pct: Maximum allowed gap percentage

    Returns:
        ValidationResult
    """
    errors = []
    warnings = []
    stats = {}

    required = ['open', 'high', 'low', 'close']
    optional = ['volume', 'timestamp', 'date']

    # Basic validation
    base_result = validate_dataframe(df, required_columns=required, min_rows=2)
    if not base_result.is_valid:
        return base_result

    # Validate OHLC relationships
    # High should be >= Open, Close, Low
    invalid_high = df[(df['high'] < df['open']) | (df['high'] < df['close']) | (df['high'] < df['low'])]
    if len(invalid_high) > 0:
        errors.append(f"Found {len(invalid_high)} rows where high is not the highest")

    # Low should be <= Open, Close, High
    invalid_low = df[(df['low'] > df['open']) | (df['low'] > df['close']) | (df['low'] > df['high'])]
    if len(invalid_low) > 0:
        errors.append(f"Found {len(invalid_low)} rows where low is not the lowest")

    # Check for zero/negative prices
    for col in ['open', 'high', 'low', 'close']:
        if (df[col] <= 0).any():
            errors.append(f"Found zero or negative values in {col}")

    # Check for price gaps
    if check_gaps:
        close_series = df['close'].values
        returns = np.abs(np.diff(close_series) / close_series[:-1] * 100)
        large_gaps = returns[returns > max_gap_pct]

        if len(large_gaps) > 0:
            warnings.append(f"Found {len(large_gaps)} gaps > {max_gap_pct}%")
            stats['max_gap_pct'] = f"{returns.max():.2f}%"

    # Check volume if present
    if 'volume' in df.columns:
        zero_volume = (df['volume'] == 0).sum()
        if zero_volume > 0:
            warnings.append(f"Found {zero_volume} bars with zero volume")
        stats['avg_volume'] = f"{df['volume'].mean():,.0f}"

    # Statistics
    stats['bars'] = len(df)
    stats['price_range'] = f"{df['low'].min():.2f} - {df['high'].max():.2f}"
    stats['avg_range_pct'] = f"{((df['high'] - df['low']) / df['close'] * 100).mean():.2f}%"

    # Determine quality
    if errors:
        quality = DataQuality.POOR
    elif len(warnings) > 2:
        quality = DataQuality.ACCEPTABLE
    elif warnings:
        quality = DataQuality.GOOD
    else:
        quality = DataQuality.EXCELLENT

    return ValidationResult(
        is_valid=len(errors) == 0,
        quality=quality,
        errors=errors,
        warnings=warnings,
        stats=stats
    )


def validate_trade_signal(
    signal: Dict[str, Any],
    underlying_price: Optional[float] = None
) -> ValidationResult:
    """
    Validate a trade signal.

    Args:
        signal: Trade signal dictionary
        underlying_price: Current underlying price

    Returns:
        ValidationResult
    """
    errors = []
    warnings = []
    stats = {}

    required_fields = ['direction', 'entry_price', 'stop_loss', 'confidence']
    optional_fields = ['strike', 'target_1', 'target_2', 'target_3', 'contracts', 'reasoning']

    # Check required fields
    missing = [f for f in required_fields if f not in signal]
    if missing:
        errors.append(f"Missing required fields: {missing}")
        return ValidationResult(
            is_valid=False,
            quality=DataQuality.UNUSABLE,
            errors=errors
        )

    # Validate direction
    valid_directions = {'LONG_CALL', 'LONG_PUT', 'SHORT_CALL', 'SHORT_PUT', 'BUY', 'SELL', 'HOLD'}
    if signal['direction'].upper() not in valid_directions:
        errors.append(f"Invalid direction: {signal['direction']}")

    # Validate prices
    if signal['entry_price'] <= 0:
        errors.append("Entry price must be positive")

    if signal['stop_loss'] <= 0:
        errors.append("Stop loss must be positive")

    # Validate stop loss makes sense
    is_long = signal['direction'].upper() in ['LONG_CALL', 'LONG_PUT', 'BUY']
    if is_long and signal['stop_loss'] >= signal['entry_price']:
        warnings.append("Stop loss >= entry price for long position")
    elif not is_long and signal['stop_loss'] <= signal['entry_price']:
        warnings.append("Stop loss <= entry price for short position")

    # Validate confidence
    if not 0 <= signal['confidence'] <= 100:
        errors.append(f"Confidence must be 0-100, got {signal['confidence']}")
    elif signal['confidence'] < 50:
        warnings.append(f"Low confidence: {signal['confidence']:.1f}%")

    # Validate targets if present
    for target_field in ['target_1', 'target_2', 'target_3']:
        if target_field in signal:
            if signal[target_field] <= 0:
                errors.append(f"{target_field} must be positive")
            elif is_long and signal[target_field] <= signal['entry_price']:
                warnings.append(f"{target_field} <= entry price for long position")

    # Calculate risk/reward if possible
    if 'target_1' in signal and signal['entry_price'] > 0 and signal['stop_loss'] > 0:
        risk = abs(signal['entry_price'] - signal['stop_loss'])
        reward = abs(signal['target_1'] - signal['entry_price'])
        if risk > 0:
            rr_ratio = reward / risk
            stats['risk_reward'] = f"1:{rr_ratio:.1f}"
            if rr_ratio < 1:
                warnings.append(f"Poor risk/reward ratio: 1:{rr_ratio:.1f}")

    # Statistics
    stats['direction'] = signal['direction']
    stats['confidence'] = f"{signal['confidence']:.1f}%"
    stats['entry'] = f"${signal['entry_price']:.2f}"
    stats['stop'] = f"${signal['stop_loss']:.2f}"

    # Determine quality
    if errors:
        quality = DataQuality.UNUSABLE
    elif len(warnings) > 2:
        quality = DataQuality.ACCEPTABLE
    elif warnings:
        quality = DataQuality.GOOD
    else:
        quality = DataQuality.EXCELLENT

    return ValidationResult(
        is_valid=len(errors) == 0,
        quality=quality,
        errors=errors,
        warnings=warnings,
        stats=stats
    )


class DataQualityChecker:
    """
    Comprehensive data quality checker.

    Tracks data quality over time and provides reports.
    """

    def __init__(self):
        self.checks: List[ValidationResult] = []
        self.failed_checks: int = 0
        self.passed_checks: int = 0

    def check(
        self,
        data: Any,
        data_type: str = "dataframe",
        **kwargs
    ) -> ValidationResult:
        """
        Run validation check based on data type.

        Args:
            data: Data to validate
            data_type: Type of data (dataframe, options_chain, price_data, trade_signal)
            **kwargs: Additional arguments for specific validators

        Returns:
            ValidationResult
        """
        validators = {
            'dataframe': validate_dataframe,
            'options_chain': validate_options_chain,
            'price_data': validate_price_data,
            'trade_signal': validate_trade_signal
        }

        if data_type not in validators:
            raise ValueError(f"Unknown data type: {data_type}")

        result = validators[data_type](data, **kwargs)
        self.checks.append(result)

        if result.is_valid:
            self.passed_checks += 1
        else:
            self.failed_checks += 1

        return result

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all checks."""
        return {
            'total_checks': len(self.checks),
            'passed': self.passed_checks,
            'failed': self.failed_checks,
            'pass_rate': f"{self.passed_checks / max(1, len(self.checks)) * 100:.1f}%",
            'quality_distribution': self._get_quality_distribution()
        }

    def _get_quality_distribution(self) -> Dict[str, int]:
        """Get distribution of quality levels."""
        distribution = {q.value: 0 for q in DataQuality}
        for check in self.checks:
            distribution[check.quality.value] += 1
        return distribution

    def reset(self):
        """Reset all checks."""
        self.checks.clear()
        self.failed_checks = 0
        self.passed_checks = 0
