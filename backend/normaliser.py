from collections import deque


class RollingNormaliser:
    def __init__(self, window=30, min_packets=10, smoothing=0.3):
        self.values      = deque(maxlen=window)
        self.min_packets = min_packets
        self.smoothing   = smoothing
        self.ema         = None

    def normalise(self, value):
        self.values.append(value)

        if len(self.values) < self.min_packets:
            return None

        lo = min(self.values)
        hi = max(self.values)

        raw_score = 50.0 if hi == lo else (value - lo) / (hi - lo) * 100

        if self.ema is None:
            self.ema = raw_score
        else:
            self.ema = self.smoothing * raw_score + (1 - self.smoothing) * self.ema

        return round(self.ema)