from AlgorithmImports import *

class MovingAverageCrossover(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2020, 1, 1)
        self.set_end_date(2024, 1, 1)
        self.set_cash(100000)

        self.spy = self.add_equity("SPY", Resolution.DAILY).symbol
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol

        self.spy_fast = self.SMA(self.spy, 10, Resolution.DAILY)
        self.spy_slow = self.SMA(self.spy, 50, Resolution.DAILY)

        self.qqq_fast = self.SMA(self.qqq, 10, Resolution.DAILY)
        self.qqq_slow = self.SMA(self.qqq, 50, Resolution.DAILY)

    def on_data(self, data: Slice):
        if not self.spy_fast.is_ready or not self.spy_slow.is_ready:
            return
        if not self.qqq_fast.is_ready or not self.qqq_slow.is_ready:
            return

        # SPY logic
        if self.spy_fast.current.value > self.spy_slow.current.value:
            self.set_holdings(self.spy, 0.5)
        else:
            self.liquidate(self.spy)

        # QQQ logic
        if self.qqq_fast.current.value > self.qqq_slow.current.value:
            self.set_holdings(self.qqq, 0.5)
        else:
            self.liquidate(self.qqq)
