"""
Revolution Alpha Engine - Market Regime Detection

Advanced regime detection for adaptive trading:
- Hidden Markov Models for regime identification
- Gaussian Mixture Models for regime clustering
- Change point detection for regime transitions
- Combined multi-method detection
- Real-time regime monitoring
"""

from .detection import (
    RegimeDetector,
    HiddenMarkovModel,
    GaussianMixtureRegime,
    ChangePointDetector,
    RegimeState,
    RegimeTransition,
)

__all__ = [
    "RegimeDetector",
    "HiddenMarkovModel",
    "GaussianMixtureRegime",
    "ChangePointDetector",
    "RegimeState",
    "RegimeTransition",
]

__version__ = "0.1.0"
