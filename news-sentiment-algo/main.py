from AlgorithmImports import *
from QuantConnect.DataSource import *
import json

# =============================================================================
# STRATEGY THESIS
# =============================================================================
# News sentiment spikes on high-liquidity US equities predict short-term price
# momentum. When a stock's 14-day rolling news sentiment score rises meaningfully
# above its recent 5-day baseline — indicating a surge in positive media coverage
# — and the stock is simultaneously trading above its 50-day moving average
# confirming a macro uptrend, the strategy enters a long position sized at 15%
# of portfolio capital. Positions are exited when sentiment deteriorates below
# the rolling baseline, when a volatility-adjusted stop loss is triggered, or
# after a minimum 5-day hold period to prevent noise-driven churn.
#
# External Data: Tiingo News Feed (QuantConnect Dataset Market)
# Coverage: 10,000 US equities, 120+ news providers, data from January 2014
# Signal: Keyword-based sentiment scoring with rolling deviation detection
#
# ANALYTICAL FAILURE MITIGATIONS:
# - Lookahead Bias: Sentiment is computed only from articles published BEFORE
#   the current trading timestamp. The history() call pulls past articles only.
#   The rolling average uses only previous days' scores, never today's, before
#   the trading decision is made.
# - Overfitting: Parameters (spike threshold 0.08, MA period 50, hold period 5)
#   were selected based on logical reasoning about volatility and signal quality,
#   not by brute-force optimization against the backtest period. The strategy
#   was tested on 2022-2024, a deliberately difficult period including a full
#   bear market, to stress-test robustness rather than cherry-pick easy years.
# - Survivorship Bias: All 9 tickers were established large-cap companies
#   throughout the entire backtest period. No delisted or failed companies
#   are included in the watchlist.
# - Regime Change: The 50-day MA filter acts as a regime detector. When a stock
#   enters a downtrend (price below 50-day MA), the strategy stops entering new
#   longs regardless of sentiment. This caused the strategy to stay mostly
#   uninvested during the 2022 bear market, which is the intended behavior.
# =============================================================================

class NewsSentimentAlgorithm(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.tickers = [
            "AAPL",   # Apple
            "GOOGL",  # Alphabet
            "NVDA",   # Nvidia
            "MSFT",   # Microsoft
            "JPM",    # JPMorgan Chase
            "UNH",    # UnitedHealth
            "V",      # Visa
            "META",   # Meta
            "AMZN",   # Amazon
        ]

        self.stop_loss_pct = {
            "AAPL":  0.08,
            "GOOGL": 0.08,
            "NVDA":  0.13,
            "MSFT":  0.08,
            "JPM":   0.08,
            "UNH":   0.07,
            "V":     0.07,
            "META":  0.12,
            "AMZN":  0.09,
        }

        self.symbols = {}
        self.news_symbols = {}
        self.sentiment_history = {}
        self.moving_averages = {}
        self.entry_date = {}
        self.entry_price = {}

        for ticker in self.tickers:
            equity = self.add_equity(ticker, Resolution.DAILY)
            symbol = equity.symbol
            self.symbols[ticker] = symbol
            self.sentiment_history[ticker] = []
            self.entry_date[ticker] = None
            self.entry_price[ticker] = None
            self.moving_averages[ticker] = self.sma(symbol, 50, Resolution.DAILY)
            news_symbol = self.add_data(TiingoNews, symbol).symbol
            self.news_symbols[ticker] = news_symbol

        for symbol in self.symbols.values():
            self.securities[symbol].set_fee_model(ConstantFeeModel(1.0))
            self.securities[symbol].set_slippage_model(ConstantSlippageModel(0.001))
            # Reality modelling: simulate realistic order fills
            self.securities[symbol].set_fill_model(ImmediateFillModel())

        # =====================================================================
        # FAILURE MODE: STATE PERSISTENCE
        # Purpose: If the algorithm crashes, restarts, or is redeployed during
        # live trading, it restores its last known state instead of starting
        # fresh. Without this, a restart would reset all sentiment history and
        # entry prices, causing the algo to re-enter positions it already holds
        # or miss exits it should have taken.
        # Note: This block is intentionally scoped to live mode only via the
        # self.live_mode check. During backtesting, always start from clean
        # state to prevent cross-run contamination (a bug we hit earlier).
        # =====================================================================
        self.state_key = "algo_state_v2"

        if self.live_mode and self.object_store.contains_key(self.state_key):
            try:
                saved = json.loads(self.object_store.read(self.state_key))
                self.sentiment_history = saved.get("sentiment_history", self.sentiment_history)
                self.entry_price = saved.get("entry_price", self.entry_price)

                # entry_date comes back from JSON as a string, convert to datetime
                raw_dates = saved.get("entry_date", {})
                for ticker, date_str in raw_dates.items():
                    if date_str is not None:
                        self.entry_date[ticker] = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    else:
                        self.entry_date[ticker] = None

                self.debug("State restored successfully from object store")
            except Exception as e:
                self.debug(f"State restore failed, starting fresh: {str(e)}")
        else:
            self.debug("Starting with clean state (backtest mode or no saved state)")

        self.schedule.on(
            self.date_rules.every_day(),
            self.time_rules.after_market_open(list(self.symbols.values())[0], 30),
            self.fetch_and_trade
        )

    def fetch_and_trade(self):
        for ticker, symbol in self.symbols.items():

            if not self.moving_averages[ticker].is_ready:
                continue

            history = self.history(TiingoNews, symbol, 14, Resolution.DAILY)

            if history.empty:
                continue

            articles = []
            for index, row in history.iterrows():
                articles.append({
                    "headline": row.get("title", ""),
                    "summary": row.get("description", "")
                })

            new_score = self.score_sentiment(articles)

            self.sentiment_history[ticker].append(new_score)
            if len(self.sentiment_history[ticker]) > 5:
                self.sentiment_history[ticker].pop(0)

            if len(self.sentiment_history[ticker]) < 3:
                continue

            previous_scores = self.sentiment_history[ticker][:-1]
            rolling_avg = sum(previous_scores) / len(previous_scores)

            sentiment_spike_up = new_score > rolling_avg + 0.08
            sentiment_spike_down = new_score < rolling_avg - 0.08

            price = self.securities[symbol].price
            ma_value = self.moving_averages[ticker].current.value
            price_above_ma = price > ma_value

            if not self.portfolio[symbol].invested:
                if sentiment_spike_up and price_above_ma:
                    self.set_holdings(symbol, 0.15)
                    self.entry_date[ticker] = self.time
                    self.entry_price[ticker] = price
                    self.debug(f"BUY {ticker} | Score: {new_score:.2f} | Avg: {rolling_avg:.2f} | Price: {price:.2f}")

            elif self.portfolio[symbol].invested:
                stop_threshold = self.entry_price[ticker] * (1 - self.stop_loss_pct[ticker])
                if price <= stop_threshold:
                    self.liquidate(symbol)
                    self.debug(f"STOP LOSS {ticker} | Entry: {self.entry_price[ticker]:.2f} | Current: {price:.2f}")
                    self.entry_date[ticker] = None
                    self.entry_price[ticker] = None

                elif self.portfolio[symbol].invested:
                    days_held = (self.time - self.entry_date[ticker]).days
                    if sentiment_spike_down and days_held >= 5:
                        self.liquidate(symbol)
                        self.debug(f"SELL {ticker} | Score: {new_score:.2f} | Avg: {rolling_avg:.2f} | Days held: {days_held}")
                        self.entry_date[ticker] = None
                        self.entry_price[ticker] = None

        # =====================================================================
        # FAILURE MODE: SAVE STATE AFTER EVERY TRADING CYCLE
        # Converts datetime objects to strings before JSON serialization since
        # JSON cannot natively serialize Python datetime objects.
        # Only saves in live mode — no point persisting backtest state.
        # =====================================================================
        if self.live_mode:
            try:
                serializable_dates = {}
                for ticker, dt in self.entry_date.items():
                    serializable_dates[ticker] = str(dt) if dt is not None else None

                state = {
                    "sentiment_history": self.sentiment_history,
                    "entry_price": self.entry_price,
                    "entry_date": serializable_dates
                }
                self.object_store.save(self.state_key, json.dumps(state))
            except Exception as e:
                self.debug(f"State save failed: {str(e)}")

    def score_sentiment(self, articles: list) -> float:
        positive_keywords = [
            "beat", "beats", "topped", "exceeded", "record", "profit", "revenue",
            "earnings", "eps", "margin", "margins", "raised", "guidance", "raised guidance",
            "dividend", "buyback", "cash flow", "operating income", "net income",
            "outperform", "exceed", "blowout", "strong results", "better than expected",
            "upgrade", "upgraded", "overweight", "buy rating", "price target raised",
            "bullish", "positive outlook", "reiterated buy", "analyst upgrade",
            "growth", "surge", "surged", "rally", "rallied", "gain", "gained",
            "momentum", "breakout", "expansion", "accelerating", "robust",
            "market share", "demand", "adoption", "subscriber", "users",
            "launch", "launched", "innovation", "partnership", "deal", "contract",
            "breakthrough", "milestone", "approved", "acquisition", "ai", "cloud",
            "platform", "wins", "award",
            "rate cut", "dovish", "stimulus", "recovery", "soft landing"
        ]

        negative_keywords = [
            "miss", "missed", "below expectations", "loss", "losses", "decline",
            "declining", "revenue miss", "earnings miss", "eps miss", "lowered guidance",
            "cut guidance", "weak results", "disappointing", "disappoints", "writedown",
            "impairment", "shortfall", "deficit",
            "downgrade", "downgraded", "underweight", "sell rating", "price target cut",
            "bearish", "negative outlook", "analyst downgrade",
            "lawsuit", "investigation", "probe", "fine", "penalty", "recall",
            "breach", "hack", "data breach", "fraud", "scandal", "charges",
            "subpoena", "regulatory",
            "crash", "crashed", "plunge", "plunged", "selloff", "sell-off",
            "slump", "slumped", "tumble", "tumbled", "drop", "dropped",
            "layoff", "layoffs", "restructuring", "bankruptcy", "default",
            "debt", "warning", "cautious", "headwinds", "slowdown",
            "competition", "supply chain", "shortage",
            "rate hike", "hawkish", "recession", "inflation", "tariff"
        ]

        score = 0
        for article in articles:
            headline = article.get("headline", "").lower()
            summary = article.get("summary", "").lower()
            text = headline + " " + summary

            for word in positive_keywords:
                if word in text:
                    score += 1
            for word in negative_keywords:
                if word in text:
                    score -= 1

        return score / len(articles) if articles else 0

    def on_data(self, data):
        pass
