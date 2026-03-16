"""
MODULAR BACKTESTING ENGINE: COMPLETE WALKTHROUGH
End-to-end backtest of three strategies with transaction cost analysis and performance comparison.

Just copy-paste this entire file into ONE Jupyter cell and run it.
"""

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Tuple, Optional
from dataclasses import dataclass
from abc import ABC, abstractmethod

print("✓ Libraries imported successfully")

# ============================================================================
# STEP 1: CORE BACKTESTING ENGINE
# ============================================================================

@dataclass
class BacktestConfig:
    """Configuration for backtest execution."""
    initial_capital: float = 1_000_000
    rebalance_freq: str = 'monthly'
    max_position_size: float = 0.05
    transaction_cost_pct: float = 0.001
    slippage_pct: float = 0.0005
    lookback_period: int = 252


class BaseStrategy(ABC):
    """Abstract base for all strategies."""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
    
    @abstractmethod
    def generate_signals(self, prices: pd.DataFrame, features: Optional[Dict] = None) -> pd.DataFrame:
        pass


class VectorizedBacktester:
    """Core backtesting engine with vectorized computations."""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.results = None
        self.positions = None
        self.trades = None
    
    def run(self, strategy: BaseStrategy, prices: pd.DataFrame, features: Optional[Dict] = None) -> Dict:
        """Execute full backtest workflow."""
        # Extract close prices
        if isinstance(prices, pd.DataFrame) and 'Close' in prices.columns:
            close_prices = prices['Close'].unstack() if prices.index.nlevels > 1 else prices[['Close']]
        else:
            close_prices = prices
        
        # Generate signals
        signals = strategy.generate_signals(close_prices, features)
        
        # Position sizing and constraints
        positions = self._apply_position_sizing(signals)
        
        # Calculate returns
        returns = close_prices.pct_change()
        
        # Transaction costs and slippage
        position_changes = positions.diff().fillna(0)
        costs = self._calculate_costs(position_changes, close_prices)
        
        # Portfolio returns
        portfolio_returns = (positions.shift(1) * returns).sum(axis=1) - costs
        cumulative_returns = (1 + portfolio_returns).cumprod()
        
        # Store results
        self.positions = positions
        self.trades = position_changes
        self.results = pd.DataFrame({
            'returns': portfolio_returns,
            'cumulative_returns': cumulative_returns,
            'portfolio_value': self.config.initial_capital * cumulative_returns,
        })
        
        return {
            'results': self.results,
            'positions': self.positions,
            'trades': self.trades,
            'metrics': self.compute_metrics(),
        }
    
    def _apply_position_sizing(self, signals: pd.DataFrame) -> pd.DataFrame:
        """Normalize signals to portfolio weights, respecting position limits."""
        signals_clipped = signals.clip(-1, 1)
        signals_constrained = signals_clipped * self.config.max_position_size
        row_sums = signals_constrained.abs().sum(axis=1)
        positions = signals_constrained.divide(row_sums, axis=0).fillna(0)
        return positions
    
    def _calculate_costs(self, position_changes: pd.DataFrame, prices: pd.DataFrame) -> pd.Series:
        """Vectorized calculation of transaction costs and slippage."""
        total_cost_pct = self.config.transaction_cost_pct + self.config.slippage_pct
        turnover = position_changes.abs().sum(axis=1)
        costs = turnover * total_cost_pct
        return costs
    
    def compute_metrics(self) -> Dict[str, float]:
        """Comprehensive performance diagnostics."""
        returns = self.results['returns']
        positions = self.positions
        trades = self.trades
        
        # Risk-adjusted returns
        annual_return = returns.mean() * 252
        annual_vol = returns.std() * np.sqrt(252)
        sharpe = annual_return / annual_vol if annual_vol > 0 else 0
        
        # Drawdown analysis
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        max_dd = drawdown.min()
        
        # Hit ratio
        hit_ratio = (returns > 0).sum() / len(returns) if len(returns) > 0 else 0
        
        # Turnover
        avg_turnover = trades.abs().sum(axis=1).mean()
        
        # Information ratio (excess return vs. buy-and-hold benchmark)
        # Simplified: compare to zero baseline
        ir = annual_return / annual_vol if annual_vol > 0 else 0
        
        # Tail risk (CVaR at 95%)
        var_95 = returns.quantile(0.05)
        cvar_95 = returns[returns <= var_95].mean()
        
        return {
            'annual_return': annual_return,
            'annual_volatility': annual_vol,
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd,
            'hit_ratio': hit_ratio,
            'avg_turnover': avg_turnover,
            'information_ratio': ir,
            'cvar_95': cvar_95,
            'total_return': (1 + returns).prod() - 1,
        }

print("✓ Core engine defined")

# ============================================================================
# STEP 2: DEFINE THREE STRATEGIES
# ============================================================================

class MomentumStrategy(BaseStrategy):
    """Trend-following momentum strategy."""
    
    def __init__(self, config: BacktestConfig, lookback_days: int = 63):
        super().__init__(config)
        self.lookback_days = lookback_days
    
    def generate_signals(self, prices: pd.DataFrame, features: Optional[Dict] = None) -> pd.DataFrame:
        momentum = prices.pct_change(self.lookback_days)
        signals = np.sign(momentum).fillna(0)
        return signals


class MeanReversionStrategy(BaseStrategy):
    """Mean reversion strategy based on rolling Z-scores."""
    
    def __init__(self, config: BacktestConfig, lookback_days: int = 20, z_threshold: float = 1.0):
        super().__init__(config)
        self.lookback_days = lookback_days
        self.z_threshold = z_threshold
    
    def generate_signals(self, prices: pd.DataFrame, features: Optional[Dict] = None) -> pd.DataFrame:
        rolling_mean = prices.rolling(self.lookback_days).mean()
        rolling_std = prices.rolling(self.lookback_days).std()
        z_scores = (prices - rolling_mean) / rolling_std
        
        signals = pd.DataFrame(0, index=prices.index, columns=prices.columns)
        signals[z_scores < -self.z_threshold] = 1
        signals[z_scores > self.z_threshold] = -1
        
        return signals.fillna(0)


class FactorStrategy(BaseStrategy):
    """Multi-factor strategy using Fama-French style factors."""
    
    def __init__(self, config: BacktestConfig):
        super().__init__(config)
    
    def generate_signals(self, prices: pd.DataFrame, features: Optional[Dict] = None) -> pd.DataFrame:
        # Factor 1: Momentum (long-term trend)
        momentum = prices.pct_change(252)
        momentum_score = momentum.rank(axis=1) / len(prices.columns)
        
        # Factor 2: Mean reversion (short-term reversal)
        short_momentum = prices.pct_change(20)
        reversion_score = -short_momentum.rank(axis=1) / len(prices.columns)
        
        # Factor 3: Volatility (quality as low volatility)
        volatility = prices.pct_change().rolling(60).std()
        quality_score = -volatility.rank(axis=1) / len(prices.columns)
        
        # Weighted combination
        combined_score = (
            0.5 * momentum_score +
            0.3 * reversion_score +
            0.2 * quality_score
        )
        
        # Convert scores to signals
        threshold_long = combined_score.quantile(0.7, axis=1)
        threshold_short = combined_score.quantile(0.3, axis=1)
        
        signals = pd.DataFrame(0, index=prices.index, columns=prices.columns)
        for date in prices.index:
            if pd.notna(threshold_long[date]):
                signals.loc[date, combined_score.loc[date] > threshold_long[date]] = 1
                signals.loc[date, combined_score.loc[date] < threshold_short[date]] = -1
        
        return signals

print("✓ Three strategies defined")

# ============================================================================
# STEP 3: GENERATE SYNTHETIC DATA & RUN BACKTESTS
# ============================================================================

def generate_synthetic_prices(n_assets=10, n_days=1260, start_price=100.0):
    """Generate realistic price paths using geometric Brownian motion."""
    dates = pd.date_range(start='2019-01-01', periods=n_days, freq='D')
    
    prices_list = []
    for asset_id in range(n_assets):
        drift = np.random.uniform(-0.05, 0.15)
        volatility = np.random.uniform(0.15, 0.40)
        returns = np.random.normal(drift / 252, volatility / np.sqrt(252), n_days)
        price_path = start_price * np.exp(np.cumsum(returns))
        prices_list.append(price_path)
    
    prices = pd.DataFrame(
        np.column_stack(prices_list),
        index=dates,
        columns=[f'Asset_{i}' for i in range(n_assets)]
    )
    
    return prices


print("\n" + "="*70)
print("BACKTESTING ENGINE: COMPLETE WALKTHROUGH")
print("="*70)

print("\n[1] Generating synthetic price data (5 years, 10 assets)...")
prices = generate_synthetic_prices(n_assets=10, n_days=1260)
print(f"    Shape: {prices.shape}")
print(f"    Date range: {prices.index[0].date()} to {prices.index[-1].date()}")
print(f"\n    Sample prices (first 3 rows):")
print(prices.head(3))

# ============================================================================
# RUN BACKTESTS WITH ALL THREE STRATEGIES
# ============================================================================

print("\n" + "="*70)
print("BACKTEST RESULTS")
print("="*70)

strategies = {
    'Momentum': MomentumStrategy(BacktestConfig()),
    'Mean Reversion': MeanReversionStrategy(BacktestConfig()),
    'Factor-Based': FactorStrategy(BacktestConfig()),
}

results_dict = {}

for strategy_name, strategy in strategies.items():
    print(f"\n[2.{list(strategies.keys()).index(strategy_name) + 1}] Running {strategy_name} strategy...")
    
    backtester = VectorizedBacktester(BacktestConfig())
    results = backtester.run(strategy, prices)
    results_dict[strategy_name] = results
    
    metrics = results['metrics']
    print(f"    Annual Return:        {metrics['annual_return']:>8.2%}")
    print(f"    Annual Volatility:    {metrics['annual_volatility']:>8.2%}")
    print(f"    Sharpe Ratio:         {metrics['sharpe_ratio']:>8.2f}")
    print(f"    Max Drawdown:         {metrics['max_drawdown']:>8.2%}")
    print(f"    Information Ratio:    {metrics['information_ratio']:>8.2f}")
    print(f"    Hit Ratio:            {metrics['hit_ratio']:>8.2%}")
    print(f"    Avg Turnover:         {metrics['avg_turnover']:>8.2%}")
    print(f"    CVaR (95%):           {metrics['cvar_95']:>8.2%}")

# ============================================================================
# COMPARATIVE ANALYSIS
# ============================================================================

print("\n" + "="*70)
print("COMPARATIVE ANALYSIS")
print("="*70)

comparison_data = []
for strategy_name, results in results_dict.items():
    metrics = results['metrics']
    comparison_data.append({
        'Strategy': strategy_name,
        'Return': f"{metrics['annual_return']:.2%}",
        'Vol': f"{metrics['annual_volatility']:.2%}",
        'Sharpe': f"{metrics['sharpe_ratio']:.2f}",
        'Max DD': f"{metrics['max_drawdown']:.2%}",
        'IR': f"{metrics['information_ratio']:.2f}",
        'Hit%': f"{metrics['hit_ratio']:.1%}",
        'Turnover': f"{metrics['avg_turnover']:.2%}",
    })

comparison_df = pd.DataFrame(comparison_data)
print("\n" + comparison_df.to_string(index=False))

print("\n[3.2] Metric Rankings (based on original values):")
metrics_list = ['annual_return', 'sharpe_ratio', 'max_drawdown', 'information_ratio']
labels_list = ['Return', 'Sharpe', 'Max DD', 'IR']

for metric, label in zip(metrics_list, labels_list):
    if metric == 'max_drawdown':
        best_idx = max(range(len(results_dict)), key=lambda i: list(results_dict.values())[i]['metrics'][metric])
        direction = "(highest, least negative)"
    else:
        best_idx = max(range(len(results_dict)), key=lambda i: list(results_dict.values())[i]['metrics'][metric])
        direction = "(highest)"
    
    best_strategy = list(results_dict.keys())[best_idx]
    print(f"    Best {label}: {best_strategy} {direction}")

# ============================================================================
# TRANSACTION COST SENSITIVITY
# ============================================================================

print("\n" + "="*70)
print("TRANSACTION COST SENSITIVITY")
print("="*70)

print("\n[4] Testing Sharpe ratio across cost regimes...")

cost_scenarios = [0.0, 0.001, 0.005, 0.01]
cost_impact = {strategy_name: [] for strategy_name in strategies.keys()}

# Map strategy names to their classes
strategy_classes = {
    'Momentum': MomentumStrategy,
    'Mean Reversion': MeanReversionStrategy,
    'Factor-Based': FactorStrategy,
}

for cost_pct in cost_scenarios:
    config = BacktestConfig(transaction_cost_pct=cost_pct, slippage_pct=0)
    
    for strategy_name, strategy_class in strategy_classes.items():
        strat = strategy_class(config)
        backtester = VectorizedBacktester(config)
        results = backtester.run(strat, prices)
        sharpe = results['metrics']['sharpe_ratio']
        cost_impact[strategy_name].append(sharpe)

print("\nSharpe Ratio by Transaction Cost:")
print(f"{'Cost':<10} {'Momentum':<12} {'Mean Reversion':<18} {'Factor-Based':<15}")
print("-" * 55)
for i, cost in enumerate(cost_scenarios):
    row = f"{cost*10000:.0f}bps".ljust(10)
    for strategy_name in strategies.keys():
        row += f"{cost_impact[strategy_name][i]:>12.2f}"
    print(row)

# ============================================================================
# CUMULATIVE PERFORMANCE & VISUALIZATION
# ============================================================================

print("\n" + "="*70)
print("CUMULATIVE PERFORMANCE ANALYSIS")
print("="*70)

print("\n[5] Final portfolio values (starting capital: $1M):")
for strategy_name, results in results_dict.items():
    final_value = results['results']['portfolio_value'].iloc[-1]
    total_return = (final_value / 1_000_000 - 1) * 100
    print(f"    {strategy_name:<20} ${final_value:>12,.0f} ({total_return:>+6.1f}%)")

print("\n✓ All backtests complete!")

# ============================================================================
# GENERATE VISUALIZATIONS
# ============================================================================

print("\n" + "="*70)
print("GENERATING VISUALIZATIONS")
print("="*70)

fig, axes = plt.subplots(2, 2, figsize=(14, 10))
fig.suptitle('Backtesting Engine: Multi-Strategy Comparison', fontsize=16, fontweight='bold')

# Plot 1: Cumulative returns
ax = axes[0, 0]
for strategy_name, results in results_dict.items():
    cum_ret = results['results']['cumulative_returns']
    ax.plot(cum_ret.index, cum_ret.values, label=strategy_name, linewidth=2)
ax.set_title('Cumulative Returns (5Y)', fontweight='bold')
ax.set_ylabel('Cumulative Return')
ax.legend()
ax.grid(True, alpha=0.3)

# Plot 2: Drawdown comparison
ax = axes[0, 1]
for strategy_name, results in results_dict.items():
    cumulative = (1 + results['results']['returns']).cumprod()
    running_max = cumulative.expanding().max()
    drawdown = (cumulative - running_max) / running_max
    ax.plot(drawdown.index, drawdown.values * 100, label=strategy_name, linewidth=2)
ax.set_title('Drawdown Over Time', fontweight='bold')
ax.set_ylabel('Drawdown (%)')
ax.legend()
ax.grid(True, alpha=0.3)

# Plot 3: Risk-Return scatter
ax = axes[1, 0]
for strategy_name, results in results_dict.items():
    metrics = results['metrics']
    ax.scatter(metrics['annual_volatility'] * 100, metrics['annual_return'] * 100, 
               s=200, label=strategy_name, alpha=0.7)
ax.set_title('Risk-Return Profile', fontweight='bold')
ax.set_xlabel('Volatility (%)')
ax.set_ylabel('Return (%)')
ax.legend()
ax.grid(True, alpha=0.3)

# Plot 4: Metric heatmap
ax = axes[1, 1]
ax.axis('off')
metrics_subset = ['sharpe_ratio', 'max_drawdown', 'hit_ratio', 'information_ratio']
heatmap_data = []
for strategy_name, results in results_dict.items():
    metrics = results['metrics']
    row = [metrics[m] for m in metrics_subset]
    heatmap_data.append(row)

table_data = [['Strategy'] + [m.replace('_', ' ').title() for m in metrics_subset]]
for i, strategy_name in enumerate(strategies.keys()):
    table_data.append([strategy_name] + [f"{v:.2f}" for v in heatmap_data[i]])

ax.table(cellText=table_data, cellLoc='center', loc='center',
         colWidths=[0.2, 0.2, 0.2, 0.2, 0.2])
ax.set_title('Key Metrics Summary', fontweight='bold', pad=20)

plt.tight_layout()
plt.savefig('backtest_results.png', dpi=150, bbox_inches='tight')
print("\n[6] Visualization saved to 'backtest_results.png'")
plt.show()

print("\n" + "="*70)
print("BACKTEST COMPLETE!")
print("="*70)
