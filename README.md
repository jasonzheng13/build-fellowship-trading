# News Sentiment Trading Algorithm
**Build Fellowship Final Project** | QuantConnect | Python

## Strategy Thesis

This strategy is built on the hypothesis that abnormal spikes in news sentiment for high-liquidity US equities predict short-term positive price momentum. Using the Tiingo News Feed — which aggregates over 120 news providers across 10,000 US equities — the algorithm computes a daily keyword-based sentiment score for each stock in a 9-ticker watchlist. Rather than comparing scores against an absolute threshold, the strategy detects meaningful deviations above each stock's own 5-day rolling sentiment baseline, filtering out the persistent positive bias inherent in financial news language. Entries require simultaneous confirmation from a 50-day moving average trend filter to avoid buying into downtrends. Positions are protected by volatility-adjusted per-ticker stop losses and a minimum 5-day hold period to prevent noise-driven churn.

---

## External Data Source

**Tiingo News Feed** (QuantConnect Dataset Market)
- Coverage: 10,000 US equities
- Sources: 120+ aggregated news providers
- Delivery: Per-second frequency as articles are published
- Historical data available from January 2014

The dataset is subscribed to per-equity using QuantConnect's `add_data(TiingoNews, symbol)` API, which links each news stream to its corresponding equity symbol and makes it available via the `history()` and `on_data()` interfaces.

---

## Architecture

The algorithm has three core components that work in sequence on every trading day:

**1. Sentiment Scoring (`score_sentiment`)**
For each ticker, the algorithm pulls the last 14 days of Tiingo news articles and runs a keyword scan across the headline and description of each article. Positive financial keywords (beat, earnings, upgrade, AI, revenue, etc.) increment the score and negative keywords (miss, layoff, recession, downgrade, etc.) decrement it. The raw score is averaged across all articles to produce a normalized daily sentiment score.

**2. Rolling Deviation Detection (`fetch_and_trade`)**
Rather than comparing the raw score against a fixed threshold — which fails because financial news has a permanent positive bias — the algorithm compares today's score against the average of the previous 5 days. A spike up (today > rolling average + 0.08) signals unusually positive coverage. A spike down (today < rolling average - 0.08) signals deteriorating sentiment.

**3. Trend Confirmation + Execution**
Buy signals require the stock to be trading above its 50-day moving average, confirming a macro uptrend. This filter kept the strategy largely uninvested during the 2022 bear market. Position size is 15% of portfolio capital per ticker (supports up to 6 simultaneous positions). Sells trigger on sentiment spike down after a minimum 5-day hold, or immediately on a per-ticker volatility-adjusted stop loss.

---

## Watchlist

| Ticker | Company | Stop Loss | Rationale |
|--------|---------|-----------|-----------|
| AAPL | Apple | 8% | Core tech, high news volume |
| GOOGL | Alphabet | 8% | Core tech, high news volume |
| NVDA | Nvidia | 13% | High volatility, AI news cycles |
| MSFT | Microsoft | 8% | Core tech, consistent coverage |
| JPM | JPMorgan Chase | 8% | Most news-covered financial stock |
| UNH | UnitedHealth | 7% | Defensive healthcare, low volatility |
| V | Visa | 7% | Low volatility, stable sentiment |
| META | Meta | 12% | High volatility, sharp sentiment swings |
| AMZN | Amazon | 9% | High article volume across AWS + retail |

---

## Backtest Results

**Period:** January 2022 – January 2024
**Starting Capital:** $100,000
**Platform:** QuantConnect (LEAN Engine)

| Metric | Value |
|--------|-------|
| Total Return | 26.78% |
| Net Profit | $22,387 |
| Final Equity | $126,778 |
| PSR | 48% |
| Total Fees | -$142 |
| Total Trades | 120+ |

The backtest period was intentionally selected to include the 2022 bear market — one of the worst years for tech stocks in recent history (NASDAQ -33%) — to stress-test robustness rather than cherry-pick favorable conditions. The strategy outperformed the S&P 500 benchmark return of approximately 18-20% over the same period.

The equity curve declined through most of 2022 as the 50-day MA filter kept the strategy mostly in cash during the downtrend, then compounded steadily through 2023's recovery.

---

## Failure Mode Preparation

### Mechanical Failures
**State Persistence:** On live deployment, the algorithm saves `sentiment_history`, `entry_price`, and `entry_date` to QuantConnect's `object_store` after every trading cycle. On restart, this state is restored so the algorithm resumes correctly without re-entering existing positions or losing exit signals. State persistence is gated to `self.live_mode` — backtests always start clean to prevent cross-run contamination.

**Error Handling:** All object store save and restore operations are wrapped in `try/except` blocks. If storage is unavailable due to server issues or network latency, the algorithm logs the error and continues running rather than crashing.

### Analytical Failures
**Lookahead Bias:** Sentiment is computed only from articles published before the current trading timestamp. The rolling average is computed from previous days' scores only, never including the current day's score before the trading decision is made.

**Overfitting:** Parameters were selected based on logical reasoning about volatility and signal quality, not brute-force optimization against the backtest period. The 0.08 spike threshold, 50-day MA period, and 5-day hold period were each chosen for explainable reasons documented in the code.

**Survivorship Bias:** All 9 tickers were established large-cap companies throughout the entire backtest period. No delisted or failed companies are included.

**Regime Change:** The 50-day moving average filter acts as a regime detector. When price falls below the MA, the strategy stops entering new longs regardless of sentiment, providing automatic protection against sustained bear markets.

### Reality Modelling
| Assumption | Model Applied |
|------------|---------------|
| Transaction fees | `ConstantFeeModel($1.00 per trade)` |
| Price slippage | `ConstantSlippageModel(0.1%)` |
| Order fills | `ImmediateFillModel()` |

## Built With

- [QuantConnect](https://www.quantconnect.com/) — cloud backtesting and live trading platform
- [LEAN Engine](https://github.com/QuantConnect/Lean) — open source algorithmic trading engine
- [Tiingo News Feed](https://www.quantconnect.com/datasets/tiingo-news-feed) — alternative news data
- Python 3

