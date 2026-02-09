"""
Revolution Alpha Engine - Fractal & Information Theory Scanner

Institutional-grade scanner applying fractal geometry and information theory
to detect regime changes, persistence shifts, and complexity transitions
in financial time series.

Implements:
    - Hurst exponent estimation (R/S analysis, DFA)
    - Fractal dimension estimation (box-counting, Higuchi)
    - Entropy measures (Shannon, permutation, sample, approximate, spectral)
    - Transfer entropy for lead-lag causality detection
    - Multifractal DFA for spectrum analysis
    - Composite scanner producing AdvancedScanResult signals

Mathematical foundations:
    - Mandelbrot (1963): Fractal geometry of market prices
    - Hurst (1951): Long-range dependence via R/S analysis
    - Peng et al. (1994): Detrended Fluctuation Analysis
    - Bandt & Pompe (2002): Permutation entropy
    - Schreiber (2000): Transfer entropy
    - Kantelhardt et al. (2002): Multifractal DFA
"""

import numpy as np
from typing import Optional, List, Dict, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from itertools import permutations
import logging
import uuid

from .base import BaseScanner, ScanContext, MarketData, HistoricalData
from .models import (
    ScanResult,
    ScanMode,
    SignalDirection,
    ScannerConfig,
)
from .advanced_models import (
    AdvancedScanResult,
    ScanCategory,
    RegimeContext,
    ExpectedTimeframe,
    FractalAnalysis,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Hurst Exponent Estimators
# =============================================================================

class HurstExponent:
    """
    Hurst exponent estimation for detecting long-range dependence.

    The Hurst exponent H characterises the scaling behaviour of a time series:
        - H > 0.5 : persistent (trending) -- past increments positively
          correlated with future increments.
        - H = 0.5 : memoryless random walk (geometric Brownian motion).
        - H < 0.5 : anti-persistent (mean-reverting) -- past increments
          negatively correlated with future increments.

    Two complementary estimators are provided:
        1. R/S (Rescaled Range) analysis -- the classical estimator.
        2. DFA (Detrended Fluctuation Analysis) -- more robust to
           non-stationarity and short-range correlations.
    """

    @staticmethod
    def rs_analysis(
        series: np.ndarray,
        min_window: int = 10,
        max_window: Optional[int] = None,
    ) -> float:
        """
        Estimate the Hurst exponent via Rescaled Range (R/S) analysis.

        Algorithm
        ---------
        For each window size n in a geometrically-spaced grid:
            1. Partition the series into k = floor(N/n) non-overlapping blocks
               of length n.
            2. For each block:
               a. Compute the mean and standard deviation.
               b. Form the mean-adjusted cumulative deviation series
                  Y_t = sum_{i=1}^{t} (x_i - mean).
               c. R = max(Y) - min(Y)  (range of cumulative deviations).
               d. S = std(block).
               e. (R/S)_block = R / S  (rescaled range for the block).
            3. Average (R/S) over all k blocks to obtain <R/S>(n).
        Fit log(<R/S>) vs log(n) by OLS; the slope is the Hurst exponent H.

        Parameters
        ----------
        series : np.ndarray
            1-D array of observations (e.g. log-returns or prices).
        min_window : int
            Smallest block size to consider.
        max_window : int or None
            Largest block size.  Defaults to N // 4.

        Returns
        -------
        float
            Estimated Hurst exponent, clamped to (0, 1).
        """
        series = np.asarray(series, dtype=np.float64)
        n_total = len(series)

        if n_total < max(20, 2 * min_window):
            return 0.5  # insufficient data -- return neutral

        if max_window is None:
            max_window = n_total // 4
        max_window = max(max_window, min_window + 1)

        # Build a geometrically-spaced set of window sizes
        n_sizes = np.unique(
            np.geomspace(min_window, max_window, num=20).astype(int)
        )
        n_sizes = n_sizes[n_sizes >= min_window]
        if len(n_sizes) < 3:
            return 0.5

        log_n = []
        log_rs = []

        for n in n_sizes:
            k = n_total // n
            if k < 1:
                continue

            rs_values = []
            for i in range(k):
                block = series[i * n : (i + 1) * n]
                std = np.std(block, ddof=1)
                if std < 1e-12:
                    continue  # skip constant blocks
                mean = np.mean(block)
                cumdev = np.cumsum(block - mean)
                r = np.max(cumdev) - np.min(cumdev)
                rs_values.append(r / std)

            if len(rs_values) == 0:
                continue

            avg_rs = np.mean(rs_values)
            if avg_rs > 0:
                log_n.append(np.log(n))
                log_rs.append(np.log(avg_rs))

        if len(log_n) < 3:
            return 0.5

        log_n = np.array(log_n)
        log_rs = np.array(log_rs)

        # OLS fit: log(R/S) = H * log(n) + c
        coeffs = np.polyfit(log_n, log_rs, 1)
        h = float(coeffs[0])

        return float(np.clip(h, 0.01, 0.99))

    @staticmethod
    def dfa(
        series: np.ndarray,
        min_window: int = 10,
        max_window: Optional[int] = None,
    ) -> float:
        """
        Estimate the Hurst exponent via Detrended Fluctuation Analysis (DFA).

        DFA is more robust than R/S analysis in the presence of
        non-stationarities (trends, level shifts) and short-range
        auto-correlations.

        Algorithm
        ---------
        1. Integrate the mean-subtracted series:
              Y_t = sum_{i=1}^{t} (x_i - <x>).
        2. For each window size n:
           a. Divide Y into non-overlapping segments of length n.
           b. In each segment, fit a linear trend (OLS) and compute the
              root-mean-square (RMS) of the residuals.
           c. Average the RMS values over all segments to obtain F(n).
        3. Fit log(F(n)) vs log(n); the slope is the DFA exponent alpha,
           which for stationary series equals the Hurst exponent H.

        Parameters
        ----------
        series : np.ndarray
            1-D array of observations.
        min_window : int
            Smallest window size.
        max_window : int or None
            Largest window size.  Defaults to N // 4.

        Returns
        -------
        float
            Estimated Hurst exponent, clamped to (0, 1).
        """
        series = np.asarray(series, dtype=np.float64)
        n_total = len(series)

        if n_total < max(20, 2 * min_window):
            return 0.5

        if max_window is None:
            max_window = n_total // 4
        max_window = max(max_window, min_window + 1)

        # Step 1: integrate the mean-subtracted series
        y = np.cumsum(series - np.mean(series))

        n_sizes = np.unique(
            np.geomspace(min_window, max_window, num=20).astype(int)
        )
        n_sizes = n_sizes[n_sizes >= min_window]
        if len(n_sizes) < 3:
            return 0.5

        log_n = []
        log_f = []

        for n in n_sizes:
            k = n_total // n
            if k < 1:
                continue

            rms_list = []
            t_local = np.arange(n, dtype=np.float64)

            for i in range(k):
                segment = y[i * n : (i + 1) * n]
                # Linear detrending via polyfit
                coeffs = np.polyfit(t_local, segment, 1)
                trend = np.polyval(coeffs, t_local)
                residuals = segment - trend
                rms = np.sqrt(np.mean(residuals ** 2))
                rms_list.append(rms)

            if len(rms_list) == 0:
                continue

            f_n = np.mean(rms_list)
            if f_n > 1e-12:
                log_n.append(np.log(n))
                log_f.append(np.log(f_n))

        if len(log_n) < 3:
            return 0.5

        log_n = np.array(log_n)
        log_f = np.array(log_f)

        coeffs = np.polyfit(log_n, log_f, 1)
        h = float(coeffs[0])

        return float(np.clip(h, 0.01, 0.99))


# =============================================================================
# Fractal Dimension Estimators
# =============================================================================

class FractalDimension:
    """
    Fractal dimension estimation for financial time series.

    The fractal dimension D quantifies the space-filling complexity of a
    curve.  For a 1-D time series embedded in 2-D (time x price):
        - D = 1.0 : smooth curve (straight line).
        - D = 1.5 : typical random walk.
        - D = 2.0 : space-filling (extremely rough / noisy).

    Relationship with the Hurst exponent (for self-affine series):
        D = 2 - H
    """

    @staticmethod
    def box_counting(
        series: np.ndarray,
        n_boxes_range: Optional[Tuple[int, int]] = None,
    ) -> float:
        """
        Estimate the fractal dimension via the box-counting method.

        The 2-D plane (time, value) is covered with a grid of boxes of
        side length epsilon.  Let N(epsilon) be the number of boxes that
        contain at least one point of the graph.  Then:

            D = -lim_{epsilon -> 0} log(N(epsilon)) / log(epsilon)

        We estimate D as the negative slope of the log(N) vs log(epsilon)
        regression.

        Parameters
        ----------
        series : np.ndarray
            1-D array of observations.
        n_boxes_range : tuple(int, int) or None
            (min_boxes, max_boxes) for the number of grid divisions along
            each axis.  Defaults to (5, min(100, N//2)).

        Returns
        -------
        float
            Estimated box-counting fractal dimension, typically in [1, 2].
        """
        series = np.asarray(series, dtype=np.float64)
        n_total = len(series)

        if n_total < 10:
            return 1.5  # insufficient data

        # Normalise to [0, 1] x [0, 1]
        t = np.linspace(0.0, 1.0, n_total)
        s_min, s_max = np.min(series), np.max(series)
        s_range = s_max - s_min
        if s_range < 1e-12:
            return 1.0  # constant series -> dimension 1

        s_norm = (series - s_min) / s_range

        if n_boxes_range is None:
            min_boxes = 5
            max_boxes = min(100, n_total // 2)
        else:
            min_boxes, max_boxes = n_boxes_range

        if max_boxes <= min_boxes:
            max_boxes = min_boxes + 10

        box_counts_list: List[int] = []
        epsilons: List[float] = []

        grid_sizes = np.unique(
            np.geomspace(min_boxes, max_boxes, num=20).astype(int)
        )

        for n_div in grid_sizes:
            epsilon = 1.0 / n_div

            # Determine which boxes are occupied
            # Box indices for each point in the time series
            t_idx = np.clip((t / epsilon).astype(int), 0, n_div - 1)
            s_idx = np.clip((s_norm / epsilon).astype(int), 0, n_div - 1)

            # Count unique (t_idx, s_idx) pairs
            occupied = set(zip(t_idx.tolist(), s_idx.tolist()))
            n_boxes = len(occupied)

            if n_boxes > 0:
                box_counts_list.append(n_boxes)
                epsilons.append(epsilon)

        if len(epsilons) < 3:
            return 1.5

        log_eps = np.log(np.array(epsilons))
        log_n = np.log(np.array(box_counts_list, dtype=np.float64))

        # D = -slope of log(N) vs log(epsilon)
        coeffs = np.polyfit(log_eps, log_n, 1)
        d = -float(coeffs[0])

        return float(np.clip(d, 1.0, 2.0))

    @staticmethod
    def higuchi(series: np.ndarray, k_max: int = 10) -> float:
        """
        Estimate the fractal dimension via the Higuchi (1988) method.

        For each scale k = 1, ..., k_max:
            1. Construct k new time series by taking every k-th sample
               starting at offsets m = 0, 1, ..., k-1:
                  X_m^k = { x[m], x[m+k], x[m+2k], ... }
            2. For each constructed series, compute its "length":
                  L_m(k) = (1/k) * [ (N-1) / (floor((N-m-1)/k) * k) ]
                           * sum |x[m+ik] - x[m+(i-1)k]|
            3. Average L(k) = mean_m(L_m(k)).
        Fit log(L(k)) vs log(1/k); the slope is the Higuchi fractal
        dimension D.

        Parameters
        ----------
        series : np.ndarray
            1-D array of observations.
        k_max : int
            Maximum scale parameter.

        Returns
        -------
        float
            Estimated Higuchi fractal dimension, typically in [1, 2].
        """
        series = np.asarray(series, dtype=np.float64)
        n = len(series)

        if n < 2 * k_max:
            k_max = max(2, n // 2)

        if n < 4:
            return 1.5  # insufficient data

        log_k_inv = []
        log_length = []

        for k in range(1, k_max + 1):
            lengths = []
            for m in range(k):
                # Indices: m, m+k, m+2k, ...
                idx = np.arange(m, n, k)
                if len(idx) < 2:
                    continue
                # Absolute first differences of the sub-sampled series
                diffs = np.abs(np.diff(series[idx]))
                n_segments = len(diffs)
                # Normalisation factor
                norm = (n - 1) / (n_segments * k * k)
                length = np.sum(diffs) * norm
                lengths.append(length)

            if len(lengths) == 0:
                continue

            avg_length = np.mean(lengths)
            if avg_length > 1e-12:
                log_k_inv.append(np.log(1.0 / k))
                log_length.append(np.log(avg_length))

        if len(log_k_inv) < 3:
            return 1.5

        log_k_inv = np.array(log_k_inv)
        log_length = np.array(log_length)

        coeffs = np.polyfit(log_k_inv, log_length, 1)
        d = float(coeffs[0])

        return float(np.clip(d, 1.0, 2.0))


# =============================================================================
# Entropy Measures
# =============================================================================

class EntropyMeasures:
    """
    Information-theoretic entropy estimators for financial time series.

    Entropy quantifies the degree of uncertainty, randomness, or
    "information content" in a signal.  Lower entropy implies more
    predictable (ordered) behaviour; higher entropy implies greater
    randomness.
    """

    @staticmethod
    def shannon_entropy(series: np.ndarray, n_bins: int = 50) -> float:
        """
        Shannon entropy of a discretised time series.

        H = -sum_i p(x_i) * log2(p(x_i))

        The continuous series is discretised into n_bins equal-width bins
        using a histogram.  Empty bins are excluded.

        Parameters
        ----------
        series : np.ndarray
            1-D array of observations.
        n_bins : int
            Number of histogram bins for discretisation.

        Returns
        -------
        float
            Shannon entropy in bits (base 2).  Returns 0.0 for constant
            or empty series.
        """
        series = np.asarray(series, dtype=np.float64)
        if len(series) < 2:
            return 0.0

        counts, _ = np.histogram(series, bins=n_bins)
        # Remove zero-count bins
        counts = counts[counts > 0]
        if len(counts) == 0:
            return 0.0

        probs = counts / counts.sum()

        # H = -sum p * log2(p)
        entropy = -np.sum(probs * np.log2(probs))
        return float(entropy)

    @staticmethod
    def permutation_entropy(
        series: np.ndarray,
        order: int = 3,
        delay: int = 1,
    ) -> float:
        """
        Normalised permutation entropy (Bandt & Pompe, 2002).

        Extracts ordinal patterns of length `order` from the time series
        and computes the Shannon entropy of their empirical distribution,
        normalised by the maximum possible entropy (log2(order!)).

        The result lies in [0, 1]:
            - 0 : completely deterministic / ordered.
            - 1 : completely random.

        Parameters
        ----------
        series : np.ndarray
            1-D array of observations.
        order : int
            Embedding dimension (pattern length).  Typical values: 3-7.
        delay : int
            Embedding delay (time step between pattern elements).

        Returns
        -------
        float
            Normalised permutation entropy in [0, 1].
        """
        series = np.asarray(series, dtype=np.float64)
        n = len(series)
        n_patterns = n - (order - 1) * delay

        if n_patterns < 1 or order < 2:
            return 0.0

        # Extract ordinal patterns
        pattern_counts: Dict[Tuple[int, ...], int] = {}
        for i in range(n_patterns):
            indices = [i + j * delay for j in range(order)]
            window = series[indices]
            # The ordinal pattern is the rank order of the elements
            pattern = tuple(np.argsort(np.argsort(window)).tolist())
            pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1

        total = sum(pattern_counts.values())
        if total == 0:
            return 0.0

        probs = np.array(list(pattern_counts.values()), dtype=np.float64) / total
        h = -np.sum(probs * np.log2(probs))

        # Normalise by maximum entropy: log2(order!)
        import math
        h_max = np.log2(float(math.factorial(order)))
        if h_max < 1e-12:
            return 0.0

        return float(np.clip(h / h_max, 0.0, 1.0))

    @staticmethod
    def sample_entropy(
        series: np.ndarray,
        m: int = 2,
        r: Optional[float] = None,
    ) -> float:
        """
        Sample entropy (SampEn) -- Richman & Moorman (2000).

        SampEn measures the conditional probability that two sequences
        that are similar for m consecutive points remain similar when
        one more point is added.

        SampEn(m, r, N) = -ln(A / B)

        where:
            B = number of template matches of length m within tolerance r.
            A = number of template matches of length m+1 within tolerance r.

        Lower SampEn indicates more self-similarity (regularity).
        Higher SampEn indicates more complexity (randomness).

        Parameters
        ----------
        series : np.ndarray
            1-D array of observations.
        m : int
            Embedding dimension (template length).
        r : float or None
            Tolerance (matching threshold).  Defaults to 0.2 * std(series).

        Returns
        -------
        float
            Sample entropy.  Returns 0.0 if undefined (e.g. A=0 or B=0).
        """
        series = np.asarray(series, dtype=np.float64)
        n = len(series)

        if n < m + 2:
            return 0.0

        if r is None:
            std = np.std(series, ddof=1)
            if std < 1e-12:
                return 0.0
            r = 0.2 * std

        def _count_matches(template_len: int) -> int:
            """Count pairs of matching templates of given length."""
            count = 0
            n_templates = n - template_len
            if n_templates < 2:
                return 0
            # Build templates as rows of a matrix for vectorised comparison
            templates = np.array([
                series[i : i + template_len]
                for i in range(n_templates)
            ])
            for i in range(n_templates):
                # Chebyshev distance (max absolute difference) to all others
                # Exclude self-match by starting from i+1
                if i + 1 >= n_templates:
                    break
                dists = np.max(
                    np.abs(templates[i + 1 :] - templates[i]), axis=1
                )
                count += int(np.sum(dists <= r))
            return count

        b = _count_matches(m)
        a = _count_matches(m + 1)

        if b == 0 or a == 0:
            return 0.0

        return float(-np.log(a / b))

    @staticmethod
    def approximate_entropy(
        series: np.ndarray,
        m: int = 2,
        r: Optional[float] = None,
    ) -> float:
        """
        Approximate entropy (ApEn) -- Pincus (1991).

        ApEn(m, r, N) = phi_m(r) - phi_{m+1}(r)

        where phi_m(r) is the average of log(C_i^m(r)) over all templates,
        and C_i^m(r) is the fraction of templates within tolerance r of
        template i (including self-match).

        ApEn is a predecessor to SampEn.  It includes self-matches and
        therefore has a slight positive bias, but is more robust for
        very short series.

        Parameters
        ----------
        series : np.ndarray
            1-D array of observations.
        m : int
            Embedding dimension.
        r : float or None
            Tolerance.  Defaults to 0.2 * std(series).

        Returns
        -------
        float
            Approximate entropy (non-negative).
        """
        series = np.asarray(series, dtype=np.float64)
        n = len(series)

        if n < m + 2:
            return 0.0

        if r is None:
            std = np.std(series, ddof=1)
            if std < 1e-12:
                return 0.0
            r = 0.2 * std

        def _phi(template_len: int) -> float:
            """Compute phi(m) for the given template length."""
            n_templates = n - template_len + 1
            if n_templates < 1:
                return 0.0

            templates = np.array([
                series[i : i + template_len]
                for i in range(n_templates)
            ])

            log_counts = np.zeros(n_templates)
            for i in range(n_templates):
                # Chebyshev distance including self-match
                dists = np.max(np.abs(templates - templates[i]), axis=1)
                count = np.sum(dists <= r)
                log_counts[i] = np.log(count / n_templates)

            return float(np.mean(log_counts))

        phi_m = _phi(m)
        phi_m1 = _phi(m + 1)

        apen = phi_m - phi_m1
        return float(max(0.0, apen))

    @staticmethod
    def spectral_entropy(
        series: np.ndarray,
        sf: float = 1.0,
        normalize: bool = True,
    ) -> float:
        """
        Spectral entropy computed from the power spectral density (PSD).

        The PSD is estimated via the FFT.  The normalised PSD is treated
        as a probability distribution and its Shannon entropy is computed.

        Low spectral entropy  -> dominated by a few frequencies (periodic).
        High spectral entropy -> energy spread across frequencies (noisy).

        Parameters
        ----------
        series : np.ndarray
            1-D array of observations.
        sf : float
            Sampling frequency (used only for context; does not affect
            the normalised entropy value).
        normalize : bool
            If True, normalise by log2(N_freq) so the result lies in [0, 1].

        Returns
        -------
        float
            Spectral entropy.  If normalised, lies in [0, 1].
        """
        series = np.asarray(series, dtype=np.float64)
        n = len(series)

        if n < 4:
            return 0.0

        # Compute one-sided power spectrum
        fft_vals = np.fft.rfft(series - np.mean(series))
        psd = np.abs(fft_vals) ** 2

        # Exclude DC component
        psd = psd[1:]
        if len(psd) == 0 or np.sum(psd) < 1e-12:
            return 0.0

        # Normalise to a probability distribution
        psd_norm = psd / np.sum(psd)

        # Remove zeros to avoid log(0)
        psd_norm = psd_norm[psd_norm > 0]

        entropy = -np.sum(psd_norm * np.log2(psd_norm))

        if normalize and len(psd_norm) > 1:
            entropy /= np.log2(len(psd_norm))

        return float(np.clip(entropy, 0.0, 1.0) if normalize else max(0.0, entropy))


# =============================================================================
# Transfer Entropy
# =============================================================================

class TransferEntropy:
    """
    Transfer entropy for detecting directional information flow between
    time series.

    Transfer entropy from X to Y quantifies the reduction in uncertainty
    about Y's future given knowledge of X's past, beyond what Y's own
    past provides:

        TE(X -> Y) = H(Y_t | Y_{t-1}) - H(Y_t | Y_{t-1}, X_{t-lag})

    A significant TE(X -> Y) implies X Granger-causes Y in an
    information-theoretic sense.
    """

    @staticmethod
    def _discretise(series: np.ndarray, n_bins: int) -> np.ndarray:
        """Discretise a continuous series into integer bin indices."""
        s_min, s_max = np.min(series), np.max(series)
        s_range = s_max - s_min
        if s_range < 1e-12:
            return np.zeros(len(series), dtype=int)
        normalised = (series - s_min) / s_range
        binned = np.clip((normalised * n_bins).astype(int), 0, n_bins - 1)
        return binned

    @staticmethod
    def _joint_entropy(*arrays: np.ndarray) -> float:
        """Compute joint Shannon entropy from co-occurring integer arrays."""
        stacked = np.column_stack(arrays)
        # Encode each row as a unique integer tuple
        n = stacked.shape[0]
        if n < 1:
            return 0.0
        # Use structured hashing for joint states
        keys = [tuple(row) for row in stacked.tolist()]
        counts: Dict[Any, int] = {}
        for k in keys:
            counts[k] = counts.get(k, 0) + 1
        probs = np.array(list(counts.values()), dtype=np.float64) / n
        return float(-np.sum(probs * np.log2(probs)))

    @classmethod
    def calculate(
        cls,
        source: np.ndarray,
        target: np.ndarray,
        lag: int = 1,
        n_bins: int = 10,
    ) -> float:
        """
        Compute transfer entropy TE(source -> target).

        TE(X -> Y) = H(Y_t, Y_{t-1}) - H(Y_{t-1})
                    - H(Y_t, Y_{t-1}, X_{t-lag}) + H(Y_{t-1}, X_{t-lag})

        This is the four-entropy formulation (equivalent to the conditional
        entropy definition but numerically more convenient).

        Parameters
        ----------
        source : np.ndarray
            Source (driver) series.
        target : np.ndarray
            Target (response) series.
        lag : int
            Number of time steps to lag the source.
        n_bins : int
            Number of bins for discretisation.

        Returns
        -------
        float
            Transfer entropy in bits.  Non-negative in expectation;
            small negative values can arise from finite-sample bias.
        """
        source = np.asarray(source, dtype=np.float64)
        target = np.asarray(target, dtype=np.float64)

        n = min(len(source), len(target))
        if n < lag + 2:
            return 0.0

        # Discretise
        x_binned = cls._discretise(source[:n], n_bins)
        y_binned = cls._discretise(target[:n], n_bins)

        # Construct aligned arrays
        # Y_t : target at time t
        # Y_{t-1} : target at time t-1
        # X_{t-lag} : source at time t-lag
        start = max(1, lag)
        y_t = y_binned[start:]
        y_prev = y_binned[start - 1 : -1] if start >= 1 else y_binned[: -1]
        x_lag = x_binned[start - lag : n - lag] if lag > 0 else x_binned[start:]

        # Trim to equal length
        min_len = min(len(y_t), len(y_prev), len(x_lag))
        if min_len < 2:
            return 0.0
        y_t = y_t[:min_len]
        y_prev = y_prev[:min_len]
        x_lag = x_lag[:min_len]

        # Four-entropy formulation:
        # TE = H(Y_t, Y_{t-1}) + H(Y_{t-1}, X_{t-lag})
        #    - H(Y_{t-1})       - H(Y_t, Y_{t-1}, X_{t-lag})
        h_yt_yprev = cls._joint_entropy(y_t, y_prev)
        h_yprev_xlag = cls._joint_entropy(y_prev, x_lag)
        h_yprev = cls._joint_entropy(y_prev)
        h_yt_yprev_xlag = cls._joint_entropy(y_t, y_prev, x_lag)

        te = h_yt_yprev + h_yprev_xlag - h_yprev - h_yt_yprev_xlag
        return float(max(0.0, te))

    @classmethod
    def significance_test(
        cls,
        source: np.ndarray,
        target: np.ndarray,
        lag: int = 1,
        n_bins: int = 10,
        n_surrogates: int = 100,
    ) -> Dict[str, float]:
        """
        Permutation test for transfer entropy significance.

        The null hypothesis is that the source has no directional
        information about the target.  Surrogates are generated by
        randomly shuffling the source series, which destroys temporal
        dependence between source and target while preserving marginal
        distributions.

        Parameters
        ----------
        source : np.ndarray
            Source series.
        target : np.ndarray
            Target series.
        lag : int
            Lag for TE computation.
        n_bins : int
            Number of discretisation bins.
        n_surrogates : int
            Number of surrogate realisations for the null distribution.

        Returns
        -------
        dict
            {
                "te_observed": float,  -- observed transfer entropy
                "te_mean_null": float, -- mean TE under the null
                "te_std_null": float,  -- std of TE under the null
                "z_score": float,      -- z-score of observed vs null
                "p_value": float,      -- one-sided p-value
            }
        """
        source = np.asarray(source, dtype=np.float64)
        target = np.asarray(target, dtype=np.float64)

        te_observed = cls.calculate(source, target, lag=lag, n_bins=n_bins)

        null_tes = np.zeros(n_surrogates)
        rng = np.random.default_rng(42)
        for i in range(n_surrogates):
            shuffled_source = rng.permutation(source)
            null_tes[i] = cls.calculate(
                shuffled_source, target, lag=lag, n_bins=n_bins
            )

        te_mean_null = float(np.mean(null_tes))
        te_std_null = float(np.std(null_tes, ddof=1))

        if te_std_null < 1e-12:
            z_score = 0.0
            p_value = 1.0
        else:
            z_score = (te_observed - te_mean_null) / te_std_null
            # One-sided p-value: fraction of surrogates >= observed
            p_value = float(np.mean(null_tes >= te_observed))

        return {
            "te_observed": te_observed,
            "te_mean_null": te_mean_null,
            "te_std_null": te_std_null,
            "z_score": z_score,
            "p_value": p_value,
        }


# =============================================================================
# Multifractal Analysis
# =============================================================================

class MultifractalAnalysis:
    """
    Multifractal Detrended Fluctuation Analysis (MF-DFA).

    Kantelhardt et al. (2002) extended DFA to characterise the full
    multifractal spectrum of a time series.

    The key idea is to compute a generalised fluctuation function F(n, q)
    for varying moment order q:
        - q > 0 emphasises large fluctuations.
        - q < 0 emphasises small fluctuations.
        - q = 2 recovers standard DFA.

    The generalised Hurst exponent h(q) is obtained from the scaling
    F(n, q) ~ n^{h(q)}.  Monofractal signals have h(q) = const for
    all q; multifractal signals show h(q) varying with q.

    The multifractal spectrum is obtained via Legendre transform:
        tau(q) = q * h(q) - 1
        alpha  = d(tau) / d(q)           (Holder / singularity exponent)
        f(alpha) = q * alpha - tau(q)    (singularity spectrum)

    The width Delta(alpha) = alpha_max - alpha_min quantifies the
    degree of multifractality.
    """

    def __init__(self) -> None:
        self._q_values: Optional[np.ndarray] = None
        self._hq: Optional[np.ndarray] = None
        self._tau: Optional[np.ndarray] = None
        self._alpha: Optional[np.ndarray] = None
        self._f_alpha: Optional[np.ndarray] = None

    def mf_dfa(
        self,
        series: np.ndarray,
        q_range: Tuple[float, float] = (-5.0, 5.0),
        n_q: int = 11,
        min_window: int = 10,
        max_window: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Perform Multifractal DFA on the given series.

        Parameters
        ----------
        series : np.ndarray
            1-D array of observations (typically log-returns).
        q_range : tuple(float, float)
            Range of moment orders q.
        n_q : int
            Number of q values (linearly spaced in q_range).
        min_window : int
            Smallest segment size.
        max_window : int or None
            Largest segment size.  Defaults to N // 4.

        Returns
        -------
        dict
            {
                "q": np.ndarray,            -- q values used
                "hq": np.ndarray,           -- generalised Hurst h(q)
                "tau": np.ndarray,          -- scaling exponent tau(q)
                "alpha": np.ndarray,        -- singularity exponents
                "f_alpha": np.ndarray,      -- singularity spectrum f(alpha)
                "spectrum_width": float,    -- Delta(alpha)
                "hurst_q2": float,          -- h(q=2), classical Hurst
            }
        """
        series = np.asarray(series, dtype=np.float64)
        n_total = len(series)

        if n_total < max(20, 2 * min_window):
            # Insufficient data -- return trivial monofractal result
            q_vals = np.linspace(q_range[0], q_range[1], n_q)
            trivial_hq = np.full(n_q, 0.5)
            self._q_values = q_vals
            self._hq = trivial_hq
            self._tau = q_vals * 0.5 - 1.0
            self._alpha = np.full(n_q, 0.5)
            self._f_alpha = np.full(n_q, 0.0)
            return {
                "q": q_vals,
                "hq": trivial_hq,
                "tau": self._tau,
                "alpha": self._alpha,
                "f_alpha": self._f_alpha,
                "spectrum_width": 0.0,
                "hurst_q2": 0.5,
            }

        if max_window is None:
            max_window = n_total // 4
        max_window = max(max_window, min_window + 1)

        # Step 1: integrate the mean-subtracted series
        y = np.cumsum(series - np.mean(series))

        # Window sizes
        n_sizes = np.unique(
            np.geomspace(min_window, max_window, num=15).astype(int)
        )
        n_sizes = n_sizes[n_sizes >= min_window]

        if len(n_sizes) < 3:
            n_sizes = np.array([min_window, (min_window + max_window) // 2, max_window])

        # q values (exclude q=0 which requires special treatment)
        q_vals = np.linspace(q_range[0], q_range[1], n_q)
        # Replace exact zero with a tiny value to avoid division issues
        q_vals[np.abs(q_vals) < 1e-6] = 1e-6

        # Step 2: compute F^2(s, v) for each segment size s
        # fq_n[i_q, i_n] will hold F(n, q)
        fq_n = np.zeros((len(q_vals), len(n_sizes)))

        for j, n_seg in enumerate(n_sizes):
            k = n_total // n_seg
            if k < 1:
                continue

            t_local = np.arange(n_seg, dtype=np.float64)
            f2_segments = np.zeros(k)

            for v in range(k):
                segment = y[v * n_seg : (v + 1) * n_seg]
                # Linear detrend
                coeffs = np.polyfit(t_local, segment, 1)
                trend = np.polyval(coeffs, t_local)
                residuals = segment - trend
                f2_segments[v] = np.mean(residuals ** 2)

            # Remove zero-variance segments
            f2_valid = f2_segments[f2_segments > 1e-20]
            if len(f2_valid) == 0:
                continue

            for i, q in enumerate(q_vals):
                # Generalised fluctuation function
                # F(n, q) = [ (1/k) sum_v F^2(v,n)^(q/2) ]^(1/q)
                if abs(q) < 1e-6:
                    # For q -> 0, use exp of mean of log
                    fq_n[i, j] = np.exp(0.5 * np.mean(np.log(f2_valid)))
                else:
                    fq_n[i, j] = np.power(
                        np.mean(np.power(f2_valid, q / 2.0)),
                        1.0 / q
                    )

        # Step 3: for each q, fit log(F(n,q)) vs log(n) to get h(q)
        log_n = np.log(n_sizes.astype(np.float64))
        hq = np.zeros(len(q_vals))

        for i in range(len(q_vals)):
            log_f = np.log(np.maximum(fq_n[i], 1e-20))
            # Filter out invalid entries
            valid = np.isfinite(log_f) & (fq_n[i] > 1e-20)
            if np.sum(valid) < 3:
                hq[i] = 0.5
                continue
            coeffs = np.polyfit(log_n[valid], log_f[valid], 1)
            hq[i] = coeffs[0]

        # Step 4: multifractal spectrum via Legendre transform
        tau = q_vals * hq - 1.0

        # Numerical differentiation: alpha = dtau/dq
        alpha = np.gradient(tau, q_vals)

        # f(alpha) = q * alpha - tau
        f_alpha = q_vals * alpha - tau

        # Store for later access
        self._q_values = q_vals
        self._hq = hq
        self._tau = tau
        self._alpha = alpha
        self._f_alpha = f_alpha

        # Spectrum width
        width = float(np.max(alpha) - np.min(alpha))

        # h(q=2) as the classical Hurst exponent
        idx_q2 = np.argmin(np.abs(q_vals - 2.0))
        hurst_q2 = float(hq[idx_q2])

        return {
            "q": q_vals,
            "hq": hq,
            "tau": tau,
            "alpha": alpha,
            "f_alpha": f_alpha,
            "spectrum_width": width,
            "hurst_q2": hurst_q2,
        }

    def spectrum_width(self) -> float:
        """
        Return the width of the multifractal spectrum Delta(alpha).

        Delta(alpha) = alpha_max - alpha_min

        A wider spectrum indicates stronger multifractality (richer
        scaling structure); a narrow spectrum indicates near-monofractal
        behaviour.

        Must be called after mf_dfa().

        Returns
        -------
        float
            Spectrum width, or 0.0 if mf_dfa() has not been run.
        """
        if self._alpha is None:
            return 0.0
        return float(np.max(self._alpha) - np.min(self._alpha))


# =============================================================================
# Composite Scanner
# =============================================================================

class FractalInformationScanner(BaseScanner[AdvancedScanResult]):
    """
    Fractal & Information Theory Scanner (Category F: Advanced Math).

    Scans the universe for regime changes and complexity transitions
    by computing:
        1. Hurst exponent (R/S + DFA) -- trend persistence detection.
        2. Fractal dimension (Higuchi) -- roughness / complexity.
        3. Shannon, permutation, and sample entropy -- disorder measures.
        4. Multifractal spectrum width -- scaling richness.
        5. Transfer entropy from sector/index to stock -- lead-lag flow.

    Signal generation criteria:
        - Hurst regime shift: persistent <-> anti-persistent transition.
        - Entropy drop: sharp decrease in complexity (market becoming
          ordered / predictable -- often precedes breakouts).
        - Spectrum narrowing: reduced multifractality signals regime
          simplification and an imminent structural change.
        - Transfer entropy spike: significant information inflow from
          a related series (leading indicator).
    """

    # Thresholds for signal generation
    HURST_PERSISTENT_THRESHOLD = 0.6
    HURST_ANTI_PERSISTENT_THRESHOLD = 0.4
    HURST_SHIFT_THRESHOLD = 0.12
    ENTROPY_DROP_THRESHOLD = 0.20
    SPECTRUM_NARROW_THRESHOLD = 0.15
    TRANSFER_ENTROPY_Z_THRESHOLD = 2.0

    # Default lookback periods (number of bars)
    SHORT_LOOKBACK = 50
    LONG_LOOKBACK = 200
    ENTROPY_WINDOW = 100

    def __init__(
        self,
        config: Optional[ScannerConfig] = None,
    ) -> None:
        super().__init__(
            name="fractal_information",
            scan_mode=ScanMode.ALL,
            config=config,
        )
        self._hurst = HurstExponent()
        self._fractal_dim = FractalDimension()
        self._entropy = EntropyMeasures()
        self._transfer = TransferEntropy()
        self._mf = MultifractalAnalysis()

    async def scan(self, context: ScanContext) -> List[AdvancedScanResult]:
        """
        Execute the fractal & information theory scan across the universe.

        For each symbol with sufficient historical data, computes fractal
        and entropy metrics over short and long lookback windows, detects
        regime shifts, and emits AdvancedScanResult signals when thresholds
        are breached.

        Parameters
        ----------
        context : ScanContext
            Scan context containing the universe, market data, and
            historical data.

        Returns
        -------
        list[AdvancedScanResult]
            List of signals generated.
        """
        results: List[AdvancedScanResult] = []

        for symbol in context.universe:
            try:
                hist = context.historical_data.get(symbol)
                if hist is None or len(hist.bars) < self.SHORT_LOOKBACK:
                    continue

                mkt = context.market_data.get(symbol)
                if mkt is not None and not self.apply_filters(mkt):
                    continue

                closes = np.array(hist.closes, dtype=np.float64)
                if len(closes) < self.SHORT_LOOKBACK:
                    continue

                # Log-returns for stationarity
                log_returns = np.diff(np.log(np.maximum(closes, 1e-8)))

                symbol_results = self._analyse_symbol(
                    symbol=symbol,
                    closes=closes,
                    log_returns=log_returns,
                    context=context,
                )
                results.extend(symbol_results)

            except Exception as e:
                self._logger.warning(
                    f"Error scanning {symbol}: {e}", exc_info=True
                )

        return results

    def validate_signal(
        self, result: AdvancedScanResult, context: ScanContext
    ) -> bool:
        """
        Validate a fractal/entropy signal against current conditions.

        A signal is valid if it has reasonable confidence and the
        underlying data is not stale.

        Parameters
        ----------
        result : AdvancedScanResult
            The scan result to validate.
        context : ScanContext
            Current scan context.

        Returns
        -------
        bool
            True if valid.
        """
        if result.confidence < 0.3:
            return False

        # Verify data freshness: the symbol should still be in the universe
        if result.symbol not in context.universe:
            return False

        return True

    # -----------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------

    def _analyse_symbol(
        self,
        symbol: str,
        closes: np.ndarray,
        log_returns: np.ndarray,
        context: ScanContext,
    ) -> List[AdvancedScanResult]:
        """Run all fractal/entropy analyses on a single symbol."""
        results: List[AdvancedScanResult] = []

        n = len(log_returns)
        short = log_returns[-self.SHORT_LOOKBACK :] if n >= self.SHORT_LOOKBACK else log_returns
        long = log_returns[-self.LONG_LOOKBACK :] if n >= self.LONG_LOOKBACK else log_returns

        # ---- 1. Hurst exponent ----
        h_short_rs = HurstExponent.rs_analysis(short)
        h_long_rs = HurstExponent.rs_analysis(long)
        h_short_dfa = HurstExponent.dfa(short)
        h_long_dfa = HurstExponent.dfa(long)

        # Average the two estimators for robustness
        h_short = 0.5 * (h_short_rs + h_short_dfa)
        h_long = 0.5 * (h_long_rs + h_long_dfa)
        hurst_shift = h_short - h_long

        # ---- 2. Fractal dimension ----
        fd_short = FractalDimension.higuchi(
            closes[-self.SHORT_LOOKBACK :] if len(closes) >= self.SHORT_LOOKBACK else closes
        )
        fd_long = FractalDimension.higuchi(
            closes[-self.LONG_LOOKBACK :] if len(closes) >= self.LONG_LOOKBACK else closes
        )

        # ---- 3. Entropy measures ----
        ent_window = log_returns[-self.ENTROPY_WINDOW :] if n >= self.ENTROPY_WINDOW else log_returns
        shannon = EntropyMeasures.shannon_entropy(ent_window)
        perm_ent = EntropyMeasures.permutation_entropy(ent_window, order=3, delay=1)
        samp_ent = EntropyMeasures.sample_entropy(ent_window, m=2)

        # Compute entropy on two halves to detect drop
        half = len(ent_window) // 2
        if half >= 10:
            perm_ent_first = EntropyMeasures.permutation_entropy(
                ent_window[:half], order=3, delay=1
            )
            perm_ent_second = EntropyMeasures.permutation_entropy(
                ent_window[half:], order=3, delay=1
            )
            entropy_change = perm_ent_second - perm_ent_first
        else:
            entropy_change = 0.0

        # ---- 4. Multifractal spectrum ----
        mf_analysis = MultifractalAnalysis()
        mf_result = mf_analysis.mf_dfa(long)
        spectrum_width = mf_result["spectrum_width"]

        # Also compute on short window for comparison
        mf_short = MultifractalAnalysis()
        mf_short_result = mf_short.mf_dfa(short)
        spectrum_width_short = mf_short_result["spectrum_width"]
        spectrum_narrowing = spectrum_width - spectrum_width_short

        # ---- 5. Transfer entropy (sector/index -> stock) ----
        te_signal = self._compute_transfer_entropy(symbol, log_returns, context)

        # ---- Build FractalAnalysis model ----
        hurst_interp = (
            "persistent" if h_short > 0.55
            else "anti_persistent" if h_short < 0.45
            else "random_walk"
        )

        complexity = float(np.clip(perm_ent, 0.0, 1.0))

        fractal_info = FractalAnalysis(
            symbol=symbol,
            hurst_exponent=round(h_short, 4),
            hurst_interpretation=hurst_interp,
            fractal_dimension=round(fd_short, 4),
            shannon_entropy=round(shannon, 4),
            permutation_entropy=round(perm_ent, 4),
            sample_entropy=round(samp_ent, 4),
            complexity_score=round(complexity, 4),
        )

        current_price = float(closes[-1])

        # ---- Signal generation ----

        # Signal A: Hurst regime shift
        if abs(hurst_shift) >= self.HURST_SHIFT_THRESHOLD:
            direction, evidence, signal = self._hurst_shift_signal(
                symbol, h_short, h_long, hurst_shift, current_price, fractal_info
            )
            if signal is not None:
                results.append(signal)

        # Signal B: Entropy drop (market becoming ordered)
        if entropy_change < -self.ENTROPY_DROP_THRESHOLD:
            signal = self._entropy_drop_signal(
                symbol, entropy_change, perm_ent, h_short,
                current_price, fractal_info
            )
            if signal is not None:
                results.append(signal)

        # Signal C: Multifractal spectrum narrowing
        if spectrum_narrowing > self.SPECTRUM_NARROW_THRESHOLD:
            signal = self._spectrum_narrow_signal(
                symbol, spectrum_width, spectrum_width_short,
                spectrum_narrowing, h_short, current_price, fractal_info
            )
            if signal is not None:
                results.append(signal)

        # Signal D: Transfer entropy spike
        if te_signal is not None:
            results.append(te_signal)

        return results

    def _compute_transfer_entropy(
        self,
        symbol: str,
        log_returns: np.ndarray,
        context: ScanContext,
    ) -> Optional[AdvancedScanResult]:
        """
        Compute transfer entropy from a reference series (e.g. sector ETF
        or market index) to the stock, and generate a signal if significant.

        The reference series is looked up in context.metadata under the key
        "reference_returns_{symbol}" or "index_returns".
        """
        # Try to find a reference series
        ref_key = f"reference_returns_{symbol}"
        ref_returns = context.metadata.get(ref_key)
        if ref_returns is None:
            ref_returns = context.metadata.get("index_returns")
        if ref_returns is None:
            return None

        ref_returns = np.asarray(ref_returns, dtype=np.float64)
        min_len = min(len(ref_returns), len(log_returns))
        if min_len < 30:
            return None

        ref = ref_returns[-min_len:]
        tgt = log_returns[-min_len:]

        result = TransferEntropy.significance_test(
            source=ref, target=tgt, lag=1, n_bins=10, n_surrogates=100
        )

        if result["z_score"] >= self.TRANSFER_ENTROPY_Z_THRESHOLD and result["p_value"] < 0.05:
            te_val = result["te_observed"]
            z = result["z_score"]
            p = result["p_value"]

            confidence = float(np.clip(0.5 + 0.1 * (z - 2.0), 0.4, 0.85))

            closes_arr = np.exp(np.cumsum(log_returns))
            current_price = float(closes_arr[-1]) if len(closes_arr) > 0 else 0.0

            return AdvancedScanResult(
                scan_id=str(uuid.uuid4()),
                scan_name="fractal_transfer_entropy_spike",
                category=ScanCategory.ADVANCED_MATH,
                symbol=symbol,
                signal_direction="BULLISH",  # direction TBD from context
                signal_strength=float(np.clip(z / 5.0, 0.3, 0.9)),
                confidence=confidence,
                expected_move_pct=0.0,
                expected_timeframe=ExpectedTimeframe.SWING,
                entry_price=current_price if current_price > 0 else None,
                supporting_evidence=[
                    f"Transfer entropy z-score {z:.2f} (p={p:.4f})",
                    f"TE = {te_val:.4f} bits",
                    "Significant information flow from reference to stock",
                ],
                contradicting_evidence=[],
                regime_context=self._map_regime(None),
                mathematical_basis=(
                    "Transfer entropy TE(X->Y) = H(Y_t|Y_{t-1}) "
                    "- H(Y_t|Y_{t-1},X_{t-lag}); significance via "
                    "permutation test."
                ),
                metadata={
                    "te_observed": te_val,
                    "te_z_score": z,
                    "te_p_value": p,
                    "te_mean_null": result["te_mean_null"],
                },
            )

        return None

    def _hurst_shift_signal(
        self,
        symbol: str,
        h_short: float,
        h_long: float,
        hurst_shift: float,
        current_price: float,
        fractal: FractalAnalysis,
    ) -> Tuple[Optional[str], List[str], Optional[AdvancedScanResult]]:
        """Generate signal for Hurst exponent regime shift."""
        supporting = []
        contradicting = []

        if hurst_shift > 0:
            # Shift towards persistence (trending)
            direction = "BULLISH" if h_short > 0.55 else "NEUTRAL"
            supporting.append(
                f"Hurst shifted +{hurst_shift:.3f} toward persistence "
                f"(short={h_short:.3f}, long={h_long:.3f})"
            )
            supporting.append("Market transitioning from mean-reversion to trending regime")
            if h_short < self.HURST_PERSISTENT_THRESHOLD:
                contradicting.append(
                    f"Short Hurst {h_short:.3f} not yet clearly persistent (>{self.HURST_PERSISTENT_THRESHOLD})"
                )
        else:
            # Shift towards anti-persistence (mean-reverting)
            direction = "BEARISH" if h_short < 0.45 else "NEUTRAL"
            supporting.append(
                f"Hurst shifted {hurst_shift:.3f} toward anti-persistence "
                f"(short={h_short:.3f}, long={h_long:.3f})"
            )
            supporting.append("Market transitioning from trending to mean-reverting regime")
            if h_short > self.HURST_ANTI_PERSISTENT_THRESHOLD:
                contradicting.append(
                    f"Short Hurst {h_short:.3f} not yet clearly anti-persistent (<{self.HURST_ANTI_PERSISTENT_THRESHOLD})"
                )

        confidence = float(np.clip(
            0.4 + abs(hurst_shift) * 2.0 + abs(h_short - 0.5) * 0.5,
            0.35, 0.85
        ))

        signal = AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="fractal_hurst_regime_shift",
            category=ScanCategory.ADVANCED_MATH,
            symbol=symbol,
            signal_direction=direction,
            signal_strength=float(np.clip(abs(hurst_shift) / 0.2, 0.3, 0.95)),
            confidence=confidence,
            expected_move_pct=0.0,
            expected_timeframe=ExpectedTimeframe.SWING,
            entry_price=current_price if current_price > 0 else None,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            regime_context=self._regime_from_hurst(h_short),
            mathematical_basis=(
                "Hurst exponent via R/S and DFA: H>0.5 persistent, "
                "H<0.5 anti-persistent, H=0.5 random walk. "
                "Regime shift detected as |H_short - H_long| > threshold."
            ),
            metadata={
                "hurst_short": h_short,
                "hurst_long": h_long,
                "hurst_shift": hurst_shift,
                "fractal_dimension": fractal.fractal_dimension,
                "complexity_score": fractal.complexity_score,
            },
        )

        return direction, supporting, signal

    def _entropy_drop_signal(
        self,
        symbol: str,
        entropy_change: float,
        perm_entropy: float,
        hurst: float,
        current_price: float,
        fractal: FractalAnalysis,
    ) -> Optional[AdvancedScanResult]:
        """Generate signal for sharp entropy drop (increasing order)."""
        # A drop in entropy means the market is becoming more ordered /
        # predictable, often preceding a directional breakout.
        direction = "BULLISH" if hurst > 0.5 else "BEARISH" if hurst < 0.45 else "NEUTRAL"

        confidence = float(np.clip(
            0.4 + abs(entropy_change) * 1.5,
            0.35, 0.80
        ))

        supporting = [
            f"Permutation entropy dropped {entropy_change:.3f} "
            f"(current={perm_entropy:.3f})",
            "Market complexity decreasing -- structure becoming more ordered",
            "Entropy drops often precede directional breakouts",
        ]

        contradicting = []
        if abs(hurst - 0.5) < 0.05:
            contradicting.append(
                f"Hurst near random walk ({hurst:.3f}); breakout direction uncertain"
            )

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="fractal_entropy_drop",
            category=ScanCategory.ADVANCED_MATH,
            symbol=symbol,
            signal_direction=direction,
            signal_strength=float(np.clip(abs(entropy_change) / 0.3, 0.3, 0.9)),
            confidence=confidence,
            expected_move_pct=0.0,
            expected_timeframe=ExpectedTimeframe.SWING,
            entry_price=current_price if current_price > 0 else None,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            regime_context=self._regime_from_hurst(hurst),
            mathematical_basis=(
                "Permutation entropy (Bandt-Pompe) on ordinal patterns; "
                "normalised to [0,1]. Sharp entropy decrease indicates "
                "transition from disordered to ordered dynamics."
            ),
            metadata={
                "entropy_change": entropy_change,
                "permutation_entropy": perm_entropy,
                "shannon_entropy": fractal.shannon_entropy,
                "sample_entropy": fractal.sample_entropy,
                "hurst": hurst,
            },
        )

    def _spectrum_narrow_signal(
        self,
        symbol: str,
        width_long: float,
        width_short: float,
        narrowing: float,
        hurst: float,
        current_price: float,
        fractal: FractalAnalysis,
    ) -> Optional[AdvancedScanResult]:
        """Generate signal for multifractal spectrum narrowing."""
        direction = "NEUTRAL"
        if hurst > 0.55:
            direction = "BULLISH"
        elif hurst < 0.45:
            direction = "BEARISH"

        confidence = float(np.clip(
            0.35 + narrowing * 1.0,
            0.3, 0.75
        ))

        supporting = [
            f"Multifractal spectrum narrowed by {narrowing:.3f} "
            f"(long width={width_long:.3f}, short width={width_short:.3f})",
            "Reduced multifractality signals regime simplification",
            "Structural change likely as scaling behaviour homogenises",
        ]

        contradicting = []
        if width_short > 0.3:
            contradicting.append(
                f"Short-window spectrum still relatively wide ({width_short:.3f})"
            )

        return AdvancedScanResult(
            scan_id=str(uuid.uuid4()),
            scan_name="fractal_spectrum_narrowing",
            category=ScanCategory.ADVANCED_MATH,
            symbol=symbol,
            signal_direction=direction,
            signal_strength=float(np.clip(narrowing / 0.3, 0.25, 0.85)),
            confidence=confidence,
            expected_move_pct=0.0,
            expected_timeframe=ExpectedTimeframe.POSITION,
            entry_price=current_price if current_price > 0 else None,
            supporting_evidence=supporting,
            contradicting_evidence=contradicting,
            regime_context=RegimeContext.TRANSITION,
            mathematical_basis=(
                "MF-DFA spectrum width Delta(alpha) = alpha_max - alpha_min "
                "from Legendre transform of generalised Hurst h(q). "
                "Narrowing indicates loss of multifractal richness."
            ),
            metadata={
                "spectrum_width_long": width_long,
                "spectrum_width_short": width_short,
                "spectrum_narrowing": narrowing,
                "hurst": hurst,
                "fractal_dimension": fractal.fractal_dimension,
            },
        )

    @staticmethod
    def _regime_from_hurst(h: float) -> RegimeContext:
        """Map Hurst exponent to a regime context."""
        if h > 0.6:
            return RegimeContext.TRENDING_UP
        elif h > 0.55:
            return RegimeContext.TRENDING_UP
        elif h < 0.4:
            return RegimeContext.RANGING
        elif h < 0.45:
            return RegimeContext.RANGING
        else:
            return RegimeContext.QUIET

    @staticmethod
    def _map_regime(regime) -> RegimeContext:
        """Map a market regime or None to RegimeContext."""
        if regime is None:
            return RegimeContext.RANGING
        return RegimeContext.RANGING
