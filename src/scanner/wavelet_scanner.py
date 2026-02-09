"""
Revolution Alpha Engine - Wavelet & Fourier Analysis Scanner

Frequency-domain analysis of financial time series using:
- Fast Fourier Transform (FFT) for cycle detection
- Discrete Wavelet Transform (DWT) for multi-resolution analysis
- Continuous Wavelet Transform (CWT) for time-frequency representation
- Wavelet coherence for cross-asset frequency analysis
- Hilbert-Huang Transform (EMD) for nonlinear/non-stationary data
- Spectral entropy for complexity measurement

Category F7 from the scan taxonomy.
"""

import numpy as np
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging
import uuid

from .base import BaseScanner, ScanContext, MarketData, HistoricalData
from .models import (
    ScanResult,
    ScanMode,
    SignalDirection,
    ScannerConfig,
    TimeFrame,
)
from .advanced_models import (
    AdvancedScanResult,
    ScanCategory,
    RegimeContext,
    ExpectedTimeframe,
)

logger = logging.getLogger(__name__)


# =============================================================================
# FFT Spectral Analysis
# =============================================================================

class SpectralAnalyzer:
    """
    FFT-based spectral analysis for identifying dominant cycles.

    Applies windowing (Hann) to reduce spectral leakage, computes
    the power spectral density, and identifies statistically
    significant periodicities.
    """

    @staticmethod
    def compute_psd(
        series: np.ndarray,
        sampling_rate: float = 1.0,
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Compute Power Spectral Density using FFT with Hann window.

        Args:
            series: Input time series
            sampling_rate: Samples per unit time (e.g., 1 for daily)

        Returns:
            (frequencies, power) arrays
        """
        n = len(series)
        if n < 8:
            return np.array([]), np.array([])

        detrended = series - np.mean(series)

        window = np.hanning(n)
        windowed = detrended * window

        fft_vals = np.fft.rfft(windowed)
        power = np.abs(fft_vals) ** 2 / n

        power[1:-1] *= 2

        freqs = np.fft.rfftfreq(n, d=1.0 / sampling_rate)

        return freqs, power

    @staticmethod
    def find_dominant_cycles(
        freqs: np.ndarray,
        power: np.ndarray,
        n_cycles: int = 5,
        min_period: int = 5,
        max_period: int = 252,
    ) -> List[Dict[str, float]]:
        """
        Identify dominant cycles from the power spectrum.

        Args:
            freqs: Frequency array from PSD
            power: Power array from PSD
            n_cycles: Number of top cycles to return
            min_period: Minimum period in bars
            max_period: Maximum period in bars

        Returns:
            List of dicts with 'period', 'frequency', 'power', 'relative_power'
        """
        if len(freqs) == 0 or len(power) == 0:
            return []

        valid_mask = freqs > 0
        valid_freqs = freqs[valid_mask]
        valid_power = power[valid_mask]

        if len(valid_freqs) == 0:
            return []

        periods = 1.0 / valid_freqs

        period_mask = (periods >= min_period) & (periods <= max_period)
        filtered_periods = periods[period_mask]
        filtered_power = valid_power[period_mask]
        filtered_freqs = valid_freqs[period_mask]

        if len(filtered_power) == 0:
            return []

        total_power = np.sum(filtered_power)
        if total_power == 0:
            return []

        sorted_idx = np.argsort(filtered_power)[::-1]
        n_return = min(n_cycles, len(sorted_idx))

        cycles = []
        for i in range(n_return):
            idx = sorted_idx[i]
            cycles.append({
                "period": float(filtered_periods[idx]),
                "frequency": float(filtered_freqs[idx]),
                "power": float(filtered_power[idx]),
                "relative_power": float(filtered_power[idx] / total_power),
            })

        return cycles

    @staticmethod
    def spectral_entropy(power: np.ndarray) -> float:
        """
        Compute spectral entropy from the power spectrum.

        Normalized Shannon entropy of the power spectral density.
        Low entropy = few dominant frequencies (periodic).
        High entropy = many frequencies (noise-like/complex).

        Returns value in [0, 1].
        """
        if len(power) == 0:
            return 1.0

        total = np.sum(power)
        if total <= 0:
            return 1.0

        p = power / total
        p = p[p > 0]

        entropy = -np.sum(p * np.log2(p))
        max_entropy = np.log2(len(power))

        if max_entropy <= 0:
            return 1.0

        return float(entropy / max_entropy)


# =============================================================================
# Discrete Wavelet Transform
# =============================================================================

class DiscreteWaveletAnalyzer:
    """
    Discrete Wavelet Transform for multi-resolution analysis.

    Decomposes a time series into approximation (low-freq trend)
    and detail (high-freq noise) components at multiple scales.

    Uses Haar wavelets (simplest orthogonal wavelet) to avoid
    external dependencies while maintaining mathematical rigor.
    """

    @staticmethod
    def haar_decompose(
        series: np.ndarray,
        max_level: Optional[int] = None,
    ) -> Tuple[np.ndarray, List[np.ndarray]]:
        """
        Perform Haar wavelet decomposition.

        Args:
            series: Input time series
            max_level: Maximum decomposition level (default: log2(n))

        Returns:
            (approximation_coeffs, [detail_coeffs_level1, detail_coeffs_level2, ...])
        """
        n = len(series)
        if max_level is None:
            max_level = int(np.log2(max(n, 2)))

        max_level = min(max_level, int(np.log2(max(n, 2))))

        current = series.copy().astype(float)
        details = []

        for level in range(max_level):
            length = len(current)
            if length < 2:
                break

            if length % 2 != 0:
                current = current[:-1]
                length -= 1

            half = length // 2
            approx = np.zeros(half)
            detail = np.zeros(half)

            for i in range(half):
                approx[i] = (current[2 * i] + current[2 * i + 1]) / np.sqrt(2)
                detail[i] = (current[2 * i] - current[2 * i + 1]) / np.sqrt(2)

            details.append(detail)
            current = approx

        return current, details

    @staticmethod
    def energy_by_level(details: List[np.ndarray]) -> List[float]:
        """
        Compute wavelet energy at each decomposition level.

        Energy at level j = Σ |d_j[k]|² / N_j
        """
        energies = []
        for d in details:
            if len(d) > 0:
                energies.append(float(np.sum(d ** 2) / len(d)))
            else:
                energies.append(0.0)
        return energies

    @staticmethod
    def denoise(
        series: np.ndarray,
        threshold_pct: float = 0.1,
        max_level: int = 4,
    ) -> np.ndarray:
        """
        Denoise time series using wavelet thresholding.

        Applies soft thresholding to detail coefficients
        to remove high-frequency noise while preserving signal.

        Args:
            series: Input time series
            threshold_pct: Fraction of max coefficient to use as threshold
            max_level: Decomposition level

        Returns:
            Denoised series (same length as input)
        """
        approx, details = DiscreteWaveletAnalyzer.haar_decompose(series, max_level)

        thresholded_details = []
        for d in details:
            if len(d) == 0:
                thresholded_details.append(d)
                continue
            threshold = threshold_pct * np.max(np.abs(d))
            d_thresh = np.sign(d) * np.maximum(np.abs(d) - threshold, 0)
            thresholded_details.append(d_thresh)

        current = approx
        for detail in reversed(thresholded_details):
            length = len(detail)
            reconstructed = np.zeros(length * 2)
            for i in range(length):
                reconstructed[2 * i] = (current[i] + detail[i]) / np.sqrt(2)
                reconstructed[2 * i + 1] = (current[i] - detail[i]) / np.sqrt(2)
            current = reconstructed

        result = current[:len(series)]
        return result


# =============================================================================
# Empirical Mode Decomposition (Hilbert-Huang Transform)
# =============================================================================

class EMDAnalyzer:
    """
    Empirical Mode Decomposition for nonlinear, non-stationary analysis.

    Decomposes a signal into Intrinsic Mode Functions (IMFs) through
    the sifting process. Unlike Fourier/wavelet methods, EMD is adaptive
    and data-driven — it doesn't assume any basis functions.
    """

    @staticmethod
    def decompose(
        series: np.ndarray,
        max_imfs: int = 8,
        max_sifting: int = 100,
        threshold: float = 0.05,
    ) -> List[np.ndarray]:
        """
        Perform EMD to extract Intrinsic Mode Functions.

        Args:
            series: Input time series
            max_imfs: Maximum number of IMFs to extract
            max_sifting: Maximum sifting iterations per IMF
            threshold: Convergence threshold for sifting

        Returns:
            List of IMFs (high frequency first) + residual
        """
        n = len(series)
        if n < 10:
            return [series.copy()]

        imfs = []
        residual = series.copy().astype(float)

        for _ in range(max_imfs):
            if np.std(residual) < 1e-10:
                break

            imf = EMDAnalyzer._extract_imf(residual, max_sifting, threshold)
            if imf is None:
                break

            imfs.append(imf)
            residual = residual - imf

            if len(EMDAnalyzer._find_extrema(residual)[0]) < 3:
                break

        imfs.append(residual)
        return imfs

    @staticmethod
    def _extract_imf(
        signal: np.ndarray,
        max_iter: int,
        threshold: float,
    ) -> Optional[np.ndarray]:
        """Extract a single IMF using the sifting process."""
        h = signal.copy()
        n = len(h)

        for _ in range(max_iter):
            maxima_idx, minima_idx = EMDAnalyzer._find_extrema(h)

            if len(maxima_idx) < 2 or len(minima_idx) < 2:
                return None

            upper = EMDAnalyzer._interpolate_envelope(maxima_idx, h[maxima_idx], n)
            lower = EMDAnalyzer._interpolate_envelope(minima_idx, h[minima_idx], n)

            mean_env = (upper + lower) / 2.0

            prev_h = h.copy()
            h = h - mean_env

            if np.sum(prev_h ** 2) > 0:
                sd = np.sum((h - prev_h) ** 2) / np.sum(prev_h ** 2)
                if sd < threshold:
                    break

        return h

    @staticmethod
    def _find_extrema(signal: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Find local maxima and minima indices."""
        n = len(signal)
        if n < 3:
            return np.array([]), np.array([])

        diff = np.diff(signal)

        maxima = []
        minima = []

        for i in range(1, len(diff)):
            if diff[i - 1] > 0 and diff[i] <= 0:
                maxima.append(i)
            elif diff[i - 1] < 0 and diff[i] >= 0:
                minima.append(i)

        return np.array(maxima), np.array(minima)

    @staticmethod
    def _interpolate_envelope(
        indices: np.ndarray,
        values: np.ndarray,
        n: int,
    ) -> np.ndarray:
        """Linear interpolation to create envelope from extrema."""
        if len(indices) < 2:
            return np.full(n, np.mean(values) if len(values) > 0 else 0.0)

        x = np.arange(n)

        ext_indices = np.concatenate([[0], indices, [n - 1]])
        ext_values = np.concatenate([[values[0]], values, [values[-1]]])

        return np.interp(x, ext_indices, ext_values)

    @staticmethod
    def instantaneous_frequency(imf: np.ndarray) -> np.ndarray:
        """
        Compute instantaneous frequency of an IMF using the
        analytic signal (Hilbert transform approximation).

        Uses finite differences on the phase of the analytic signal.
        """
        n = len(imf)
        if n < 4:
            return np.zeros(n)

        analytic = EMDAnalyzer._hilbert_transform(imf)
        phase = np.unwrap(np.angle(analytic))
        inst_freq = np.diff(phase) / (2.0 * np.pi)

        return np.concatenate([inst_freq, [inst_freq[-1]]])

    @staticmethod
    def _hilbert_transform(signal: np.ndarray) -> np.ndarray:
        """Compute analytic signal using FFT-based Hilbert transform."""
        n = len(signal)
        fft = np.fft.fft(signal)

        h = np.zeros(n)
        if n > 0:
            h[0] = 1
            if n % 2 == 0:
                h[n // 2] = 1
                h[1:n // 2] = 2
            else:
                h[1:(n + 1) // 2] = 2

        analytic = np.fft.ifft(fft * h)
        return analytic


# =============================================================================
# Wavelet Coherence
# =============================================================================

class WaveletCoherence:
    """
    Wavelet coherence for measuring time-varying co-movement
    between two time series at different frequencies.

    Identifies lead-lag relationships at different scales.
    """

    @staticmethod
    def compute_coherence(
        series1: np.ndarray,
        series2: np.ndarray,
        scales: Optional[np.ndarray] = None,
    ) -> Dict[str, np.ndarray]:
        """
        Compute wavelet coherence between two series.

        Uses a simplified CWT approach with Morlet-like wavelets.

        Args:
            series1: First time series
            series2: Second time series
            scales: Array of scales (periods) to analyze

        Returns:
            Dict with 'scales', 'coherence', 'phase_diff' arrays
        """
        n = min(len(series1), len(series2))
        if n < 20:
            return {"scales": np.array([]), "coherence": np.array([]), "phase_diff": np.array([])}

        s1 = (series1[:n] - np.mean(series1[:n])) / (np.std(series1[:n]) + 1e-10)
        s2 = (series2[:n] - np.mean(series2[:n])) / (np.std(series2[:n]) + 1e-10)

        if scales is None:
            scales = np.array([5, 10, 20, 40, 60, 120])
            scales = scales[scales < n // 2]

        if len(scales) == 0:
            return {"scales": np.array([]), "coherence": np.array([]), "phase_diff": np.array([])}

        coherence = np.zeros(len(scales))
        phase_diff = np.zeros(len(scales))

        for i, scale in enumerate(scales):
            scale = int(scale)
            if scale < 2 or scale >= n:
                continue

            n_windows = n - scale + 1
            if n_windows < 1:
                continue

            cross_corrs = np.zeros(n_windows)
            for j in range(n_windows):
                w1 = s1[j:j + scale]
                w2 = s2[j:j + scale]
                std1 = np.std(w1)
                std2 = np.std(w2)
                if std1 > 1e-10 and std2 > 1e-10:
                    cross_corrs[j] = np.corrcoef(w1, w2)[0, 1]

            coherence[i] = np.mean(np.abs(cross_corrs))

            fft1 = np.fft.rfft(s1[:scale])
            fft2 = np.fft.rfft(s2[:scale])
            cross = fft1 * np.conj(fft2)
            if len(cross) > 1:
                dominant_idx = np.argmax(np.abs(cross[1:])) + 1
                phase_diff[i] = np.angle(cross[dominant_idx])

        return {
            "scales": scales,
            "coherence": coherence,
            "phase_diff": phase_diff,
        }

    @staticmethod
    def detect_lead_lag(
        phase_diff: np.ndarray,
        scales: np.ndarray,
    ) -> Dict[str, Any]:
        """
        Interpret phase differences as lead-lag relationships.

        Phase > 0: series1 leads series2
        Phase < 0: series2 leads series1
        Phase ≈ 0: in-phase (co-movement)
        Phase ≈ π: anti-phase (inverse movement)
        """
        if len(phase_diff) == 0:
            return {"relationship": "unknown", "lead_lag_days": 0}

        avg_phase = np.mean(phase_diff[np.abs(phase_diff) > 0.1])

        if np.abs(avg_phase) < 0.3:
            relationship = "in_phase"
        elif np.abs(avg_phase - np.pi) < 0.3 or np.abs(avg_phase + np.pi) < 0.3:
            relationship = "anti_phase"
        elif avg_phase > 0:
            relationship = "series1_leads"
        else:
            relationship = "series2_leads"

        avg_scale = np.mean(scales) if len(scales) > 0 else 1
        lead_lag_days = avg_phase / (2 * np.pi) * avg_scale

        return {
            "relationship": relationship,
            "lead_lag_days": float(lead_lag_days),
            "avg_phase": float(avg_phase),
        }


# =============================================================================
# Wavelet & Fourier Scanner
# =============================================================================

class WaveletFourierScanner(BaseScanner):
    """
    Scanner combining Fourier and wavelet analysis for:
    - Dominant cycle detection (timing entries with cycle phase)
    - Multi-resolution trend/noise separation
    - Regime change detection via spectral entropy shifts
    - Cross-asset frequency-domain lead-lag analysis
    - EMD-based adaptive trend extraction

    Category F7 from the scan taxonomy.
    """

    def __init__(self, config: Optional[ScannerConfig] = None):
        super().__init__(
            name="wavelet_fourier",
            scan_mode=ScanMode.ALL,
            config=config,
        )
        self.spectral = SpectralAnalyzer()
        self.dwt = DiscreteWaveletAnalyzer()
        self.emd = EMDAnalyzer()
        self.coherence = WaveletCoherence()

        self.entropy_lookback = 60
        self.entropy_threshold = 0.15

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        """Run frequency-domain analysis on the universe."""
        results: List[AdvancedScanResult] = []

        for symbol in context.universe:
            try:
                result = self._analyze_symbol(symbol, context)
                if result is not None:
                    results.append(result)
            except Exception as e:
                self._logger.warning(f"Wavelet analysis failed for {symbol}: {e}")

        return results

    def _analyze_symbol(
        self,
        symbol: str,
        context: ScanContext,
    ) -> Optional[AdvancedScanResult]:
        """Full frequency-domain analysis for a single symbol."""
        hist = context.historical_data.get(symbol)
        if not hist or len(hist.bars) < 60:
            return None

        closes = np.array(hist.closes, dtype=float)
        returns = np.diff(np.log(np.maximum(closes, 1e-10)))

        if len(returns) < 30:
            return None

        freqs, power = self.spectral.compute_psd(returns)
        dominant_cycles = self.spectral.find_dominant_cycles(freqs, power)
        current_entropy = self.spectral.spectral_entropy(power)

        if len(returns) >= self.entropy_lookback * 2:
            old_returns = returns[-self.entropy_lookback * 2:-self.entropy_lookback]
            new_returns = returns[-self.entropy_lookback:]
            _, old_power = self.spectral.compute_psd(old_returns)
            _, new_power = self.spectral.compute_psd(new_returns)
            old_entropy = self.spectral.spectral_entropy(old_power)
            new_entropy = self.spectral.spectral_entropy(new_power)
            entropy_change = new_entropy - old_entropy
        else:
            entropy_change = 0.0
            old_entropy = current_entropy
            new_entropy = current_entropy

        approx, details = self.dwt.haar_decompose(closes, max_level=4)
        wavelet_energies = self.dwt.energy_by_level(details)

        imfs = self.emd.decompose(closes[-min(200, len(closes)):], max_imfs=5)

        signals = []
        supporting = []
        contradicting = []

        if dominant_cycles:
            best_cycle = dominant_cycles[0]
            if best_cycle["relative_power"] > 0.15:
                period = best_cycle["period"]
                phase_position = (len(closes) % period) / period
                if phase_position < 0.25:
                    signals.append(("cycle_trough", 1.0))
                    supporting.append(f"Near cycle trough (period={period:.0f}d, power={best_cycle['relative_power']:.1%})")
                elif 0.45 < phase_position < 0.55:
                    signals.append(("cycle_peak", -1.0))
                    supporting.append(f"Near cycle peak (period={period:.0f}d)")

        if abs(entropy_change) > self.entropy_threshold:
            if entropy_change < -self.entropy_threshold:
                signals.append(("entropy_drop", 0.5))
                supporting.append(f"Spectral entropy dropping ({old_entropy:.3f} → {new_entropy:.3f}): market becoming more structured")
            else:
                signals.append(("entropy_rise", -0.5))
                contradicting.append(f"Spectral entropy rising: market becoming more chaotic")

        if wavelet_energies:
            high_freq_energy = sum(wavelet_energies[:2]) if len(wavelet_energies) >= 2 else 0
            low_freq_energy = sum(wavelet_energies[2:]) if len(wavelet_energies) > 2 else 1
            if low_freq_energy > 0:
                noise_ratio = high_freq_energy / (low_freq_energy + 1e-10)
                if noise_ratio < 0.3:
                    supporting.append(f"Low noise regime (HF/LF energy ratio: {noise_ratio:.2f})")
                    signals.append(("clean_trend", 0.3))
                elif noise_ratio > 3.0:
                    contradicting.append(f"High noise regime (HF/LF energy ratio: {noise_ratio:.2f})")

        if len(imfs) >= 3:
            trend = imfs[-1]
            if len(trend) >= 5:
                trend_slope = (trend[-1] - trend[-5]) / (np.std(trend) + 1e-10)
                if trend_slope > 1.0:
                    signals.append(("emd_trend_up", 0.4))
                    supporting.append(f"EMD trend component rising (slope z={trend_slope:.2f})")
                elif trend_slope < -1.0:
                    signals.append(("emd_trend_down", -0.4))
                    supporting.append(f"EMD trend component falling (slope z={trend_slope:.2f})")

        if not signals:
            return None

        combined_score = sum(s[1] for s in signals) / len(signals)

        if abs(combined_score) < 0.15:
            return None

        if combined_score > 0:
            direction = "BULLISH"
        else:
            direction = "BEARISH"

        confidence = min(0.85, abs(combined_score) * 0.6 + 0.3)
        current_price = closes[-1]

        market_data = context.market_data.get(symbol)
        atr = market_data.atr if market_data and market_data.atr else current_price * 0.02

        if direction == "BULLISH":
            stop_loss = current_price - 2 * atr
            target = current_price + 3 * atr
        else:
            stop_loss = current_price + 2 * atr
            target = current_price - 3 * atr

        risk = abs(current_price - stop_loss)
        reward = abs(target - current_price)
        rr = reward / risk if risk > 0 else 0

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="Wavelet & Fourier Analysis",
            category=ScanCategory.ADVANCED_MATH,
            symbol=symbol,
            signal_direction=direction,
            signal_strength=abs(combined_score),
            confidence=confidence,
            expected_move_pct=abs(combined_score) * 3.0,
            expected_timeframe=ExpectedTimeframe.SWING,
            risk_reward_ratio=rr,
            entry_price=current_price,
            stop_loss_level=stop_loss,
            target_level=target,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            regime_context=RegimeContext.RANGING if current_entropy > 0.8 else RegimeContext.TRENDING_UP,
            mathematical_basis=(
                f"FFT spectral analysis identified {len(dominant_cycles)} dominant cycles. "
                f"Spectral entropy = {current_entropy:.3f} (Δ={entropy_change:+.3f}). "
                f"Haar DWT {len(details)}-level decomposition with energy analysis. "
                f"EMD extracted {len(imfs)} IMFs for adaptive trend/noise separation."
            ),
            false_positive_rate=max(0.1, 1.0 - confidence),
            decay_halflife_days=int(dominant_cycles[0]["period"]) if dominant_cycles else 20,
            metadata={
                "dominant_cycles": dominant_cycles[:3],
                "spectral_entropy": current_entropy,
                "entropy_change": entropy_change,
                "wavelet_energies": wavelet_energies,
                "n_imfs": len(imfs),
                "signal_components": [(name, round(score, 3)) for name, score in signals],
            },
        )

    def validate_signal(self, result, context: ScanContext) -> bool:
        """Validate wavelet/fourier signal."""
        if not isinstance(result, AdvancedScanResult):
            return False
        if result.confidence < 0.35:
            return False
        if len(result.supporting_evidence) < 1:
            return False
        return True
