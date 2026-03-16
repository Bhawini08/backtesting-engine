"""
Example strategy implementations demonstrating the backtesting framework.
Shows momentum, mean reversion, and factor-based approaches.
"""

import numpy as np
import pandas as pd
from backtester import BaseStrategy, BacktestConfig
from typing import Dict, Optional


class MomentumStrategy(BaseStrategy):
    """
    Trend-following momentum strategy.
    
    Long assets with positive 3-month momentum, short those with negative momentum.
    Rebalances monthly. Classic risk factor that exploits trending behavior.
    """
    
    def __init__(self, config: BacktestConfig, lookback_days: int = 63):
        super().__init__(config)
        self.lookback_days = lookback_days
    
    def generate_signals(self, prices: pd.DataFrame, features: Optional[Dict] = None) -> pd.DataFrame:
        """
        Signal = sign(momentum over lookback period)
        """
        # Calculate cumulative returns over lookback window
        momentum = prices.pct_change(self.lookback_days)
        
        # Convert to signals: 1 for positive, -1 for negative, 0 for neutral
        signals = np.sign(momentum).fillna(0)
        
        return signals


class MeanReversionStrategy(BaseStrategy):
    """
    Mean reversion strategy based on rolling Z-scores.
    
    Assumes assets that deviate significantly from their rolling mean will revert.
    Goes long on Z-scores < -1 (oversold), short on Z-scores > 1 (overbought).
    """
    
    def __init__(self, config: BacktestConfig, lookback_days: int = 20, z_threshold: float = 1.0):
        super().__init__(config)
        self.lookback_days = lookback_days
        self.z_threshold = z_threshold
    
    def generate_signals(self, prices: pd.DataFrame, features: Optional[Dict] = None) -> pd.DataFrame:
        """
        Signal based on rolling mean and volatility.
        """
        rolling_mean = prices.rolling(self.lookback_days).mean()
        rolling_std = prices.rolling(self.lookback_days).std()
        
        # Z-score normalized distance from mean
        z_scores = (prices - rolling_mean) / rolling_std
        
        # Threshold-based signals
        signals = pd.DataFrame(0, index=prices.index, columns=prices.columns)
        signals[z_scores < -self.z_threshold] = 1   # Oversold
        signals[z_scores > self.z_threshold] = -1   # Overbought
        
        return signals.fillna(0)


class FactorStrategy(BaseStrategy):
    """
    Multi-factor strategy using Fama-French style factors.
    
    Constructs synthetic factors (value, momentum, quality) from price and volume data.
    Scores each asset and generates long/short signals.
    
    Factors:
    - Value: Price-to-Book proxy (inverse of recent price strength)
    - Momentum: 12-month returns
    - Quality: Volatility-adjusted returns (Sharpe-like)
    """
    
    def __init__(self, config: BacktestConfig):
        super().__init__(config)
    
    def generate_signals(self, prices: pd.DataFrame, features: Optional[Dict] = None) -> pd.DataFrame:
        """
        Multi-factor scoring approach.
        """
        # Factor 1: Momentum (long-term trend)
        momentum = prices.pct_change(252)  # 1-year return
        momentum_score = momentum.rank(axis=1) / len(prices.columns)
        
        # Factor 2: Mean reversion (short-term reversal)
        short_momentum = prices.pct_change(20)  # 20-day return
        reversion_score = -short_momentum.rank(axis=1) / len(prices.columns)  # Negative of short-term
        
        # Factor 3: Volatility (quality as low volatility)
        volatility = prices.pct_change().rolling(60).std()
        quality_score = -volatility.rank(axis=1) / len(prices.columns)  # Lower vol = higher score
        
        # Weighted combination
        combined_score = (
            0.5 * momentum_score +
            0.3 * reversion_score +
            0.2 * quality_score
        )
        
        # Convert scores to signals: top 30% long, bottom 30% short
        threshold_long = combined_score.quantile(0.7, axis=1)
        threshold_short = combined_score.quantile(0.3, axis=1)
        
        signals = pd.DataFrame(0, index=prices.index, columns=prices.columns)
        for date in prices.index:
            if pd.notna(threshold_long[date]):
                signals.loc[date, combined_score.loc[date] > threshold_long[date]] = 1
                signals.loc[date, combined_score.loc[date] < threshold_short[date]] = -1
        
        return signals
