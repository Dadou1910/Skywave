import math
import time
import random
import threading

from backend.sources.base import DataSource


class MockSource(DataSource):
    """
    Generates realistic fake EEG packets at 1 Hz.

    Uses three correlated latent drives instead of independent band walks so
    that the derived metrics are neurologically plausible:
      - focus and stress are anti-correlated  (you can't be both at once)
      - relaxation rises when arousal falls
      - fatigue drifts slowly and independently
    """

    # How fast each drive drifts per tick (fraction of its [0,1] range)
    _AROUSAL_STEP  = 0.04
    _BALANCE_STEP  = 0.03   # focus(1) vs stress(0) balance when aroused
    _REST_STEP     = 0.035
    _FATIGUE_STEP  = 0.02

    def __init__(self):
        super().__init__()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._connected = False

        # Latent drives, all in [0, 1]
        self._arousal  = random.uniform(0.3, 0.7)
        self._balance  = random.uniform(0.3, 0.7)   # 1=focused, 0=stressed
        self._rest     = random.uniform(0.3, 0.7)
        self._fatigue  = random.uniform(0.15, 0.45)

    @property
    def source_name(self) -> str:
        return "Mock (development)"

    def is_connected(self) -> bool:
        return self._connected

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="MockSource",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3)
        self._connected = False

    # ------------------------------------------------------------------
    # Latent drive mechanics
    # ------------------------------------------------------------------

    @staticmethod
    def _walk(v: float, step: float, pull: float = 0.5) -> float:
        """Random walk with mean-reversion so drives don't get stuck at 0/1."""
        delta = random.uniform(-step, step) + (pull - v) * 0.06
        return max(0.0, min(1.0, v + delta))

    def _update_drives(self) -> None:
        self._arousal = self._walk(self._arousal, self._AROUSAL_STEP)

        # Rest is anti-correlated with arousal: when alert, less resting alpha
        rest_pull = 0.85 - self._arousal * 0.7
        self._rest = self._walk(self._rest, self._REST_STEP, pull=rest_pull)

        # Balance (focus vs stress) mean-reverts toward 0.5 independently
        self._balance = self._walk(self._balance, self._BALANCE_STEP)

        self._fatigue = self._walk(self._fatigue, self._FATIGUE_STEP, pull=0.3)

    # ------------------------------------------------------------------
    # Band power synthesis
    # ------------------------------------------------------------------

    def _build_packet(self) -> dict:
        self._update_drives()

        a = self._arousal   # 0=drowsy, 1=activated
        b = self._balance   # 0=stressed, 1=focused  (only meaningful when a is high)
        r = self._rest      # 0=alert, 1=relaxed/alpha
        f = self._fatigue   # 0=fresh, 1=tired

        def jitter(scale: float) -> float:
            return random.gauss(0, scale)

        # --- lowBeta (13-20 Hz): concentration / engagement ---
        # Peaks when aroused AND focused (balance high)
        low_beta = max(0, int(a * b * 90_000 + r * 15_000 + jitter(4_000)))

        # --- highBeta (20-30 Hz): anxiety / cognitive stress ---
        # Peaks when aroused AND stressed (balance low)
        high_beta = max(0, int(a * (1 - b) * 75_000 + jitter(3_000)))

        # --- alpha (8-13 Hz): relaxed alertness ---
        # Peaks when resting; suppressed by arousal
        alpha_total = max(0, int(r * 160_000 + (1 - a) * 30_000 + jitter(5_000)))
        low_alpha   = max(0, int(alpha_total * 0.55 + jitter(2_000)))
        high_alpha  = max(0, alpha_total - low_alpha)

        # --- theta (4-8 Hz): drowsiness / meditation ---
        # Rises with fatigue and rest; suppressed by arousal
        theta = max(0, int(f * 70_000 + r * 40_000 + (1 - a) * 25_000 + jitter(3_000)))

        # --- delta (0.5-4 Hz): deep sleep / fatigue ---
        delta = max(0, int(f * 600_000 + (1 - a) * 200_000 + jitter(20_000)))

        # --- gamma (30+ Hz): sensory processing, minor ---
        low_gamma  = max(0, int(a * 25_000 + jitter(1_500)))
        high_gamma = max(0, int(a * 15_000 + jitter(1_000)))

        # eSense proxies
        attention  = int(max(0, min(100, a * b * 90 + jitter(5))))
        meditation = int(max(0, min(100, r * 85 + (1 - a) * 20 + jitter(5))))

        packet = {
            "poorSignalLevel": 0,
            "eSense": {
                "attention":  attention,
                "meditation": meditation,
            },
            "eegPower": {
                "delta":     delta,
                "theta":     theta,
                "lowAlpha":  low_alpha,
                "highAlpha": high_alpha,
                "lowBeta":   low_beta,
                "highBeta":  high_beta,
                "lowGamma":  low_gamma,
                "highGamma": high_gamma,
            },
        }

        if random.random() < 0.03:
            packet["blinkStrength"] = int(max(1, min(255, random.gauss(80, 30))))

        return packet

    def _run(self) -> None:
        self._connected = True
        while not self._stop_event.is_set():
            packet = self._build_packet()
            self._emit(packet)
            for _ in range(10):
                if self._stop_event.is_set():
                    break
                time.sleep(0.1)
        self._connected = False
