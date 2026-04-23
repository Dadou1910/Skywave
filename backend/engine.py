from __future__ import annotations

import time

from PyQt6.QtCore import QObject, pyqtSignal

from backend.normaliser import RollingNormaliser
from backend.sources.base import DataSource
from backend.database import Database


# ── Metric definitions ────────────────────────────────────────────────────────
# Single source of truth used by the engine, all screens, and all widgets.
# (key, display label, hex colour, low description, high description)
METRICS: list[tuple[str, str, str, str, str]] = [
    (
        "focus", "Focus", "#7F77DD",
        "mind wandering / passive",
        "deep concentration / task-locked",
    ),
    (
        "relax", "Relax", "#1D9E75",
        "tense / mentally activated",
        "calm / eyes-closed ease",
    ),
    (
        "stress", "Stress", "#D85A30",
        "at ease / low mental load",
        "anxious / overthinking",
    ),
    (
        "flow", "Flow", "#EF9F27",
        "scattered / surface thinking",
        "creative immersion / in the zone",
    ),
    (
        "fatigue", "Fatigue", "#378ADD",
        "mentally fresh / alert",
        "mentally tired / slow waves rising",
    ),
]

METRIC_KEYS = [m[0] for m in METRICS]
WARMUP_PACKETS = 10


# ── ScorePacket ───────────────────────────────────────────────────────────────
class ScorePacket:
    __slots__ = ("scores", "blink", "is_warmup", "warmup_count", "raw_bands", "signal_quality")

    def __init__(
        self,
        scores: dict[str, float | None],
        blink: int | None,
        is_warmup: bool,
        warmup_count: int,
        raw_bands: dict | None = None,
        signal_quality: int = -1,
    ):
        self.scores         = scores
        self.blink          = blink
        self.is_warmup      = is_warmup
        self.warmup_count   = warmup_count
        self.raw_bands      = raw_bands or {}
        self.signal_quality = signal_quality


# ── DataEngine ────────────────────────────────────────────────────────────────
class DataEngine(QObject):
    """
    Central nervous system of the app.

    Owns the DataSource, normalises raw EEG bands into 0-100 scores,
    emits new_scores(ScorePacket), and manages session/training lifecycle.
    """

    new_scores = pyqtSignal(object)
    connection_changed = pyqtSignal(bool)

    def __init__(self, source: DataSource, db: Database, user_id: int | None = None, parent=None):
        super().__init__(parent)

        self._source  = source
        self._db      = db
        self._user_id = user_id

        self._normalisers = {
            key: RollingNormaliser(min_packets=WARMUP_PACKETS)
            for key in METRIC_KEYS
        }
        self._raw_count = 0
        self._last_packet_time = 0.0

        self._session_id:          int | None = None
        self._training_session_id: int | None = None
        self._training_metric:     str | None = None
        self._training_threshold:  float      = 0.0
        self._seconds_on_target:   int        = 0
        self._was_on_target:       bool       = False

        self._source.set_callback(self._on_raw_packet)

    def start(self) -> None:
        self._source.start()

    def stop(self) -> None:
        if self._training_session_id is not None:
            self.stop_training()
        if self._session_id is not None:
            self.end_session()
        self._source.stop()

    def is_connected(self) -> bool:
        return self._source.is_connected()

    def begin_session(self, note: str = "") -> None:
        if self._session_id is not None:
            return
        self._session_id = self._db.start_session(
            source_name=self._source.source_name,
            note=note,
            user_id=self._user_id,
        )

    def end_session(self, note: str = "") -> None:
        if self._session_id is None:
            return
        self._db.end_session(self._session_id, note)
        self._session_id = None

    @property
    def session_active(self) -> bool:
        return self._session_id is not None

    def start_training(self, metric: str, threshold: float) -> None:
        if not self.session_active:
            self.begin_session()
        self._training_metric    = metric
        self._training_threshold = threshold
        self._seconds_on_target  = 0
        self._was_on_target      = False
        self._training_session_id = self._db.start_training_session(
            session_id=self._session_id,
            target_metric=metric,
            target_threshold=threshold,
        )

    def stop_training(self, note: str = "") -> None:
        if self._training_session_id is None:
            return
        self._db.end_training_session(
            self._training_session_id,
            self._seconds_on_target,
            note,
        )
        self._training_session_id = None
        self._training_metric     = None
        self._was_on_target       = False

    @property
    def training_active(self) -> bool:
        return self._training_session_id is not None

    def _on_raw_packet(self, packet: dict) -> None:
        signal = packet.get("poorSignalLevel", -1)

        if signal == 200:
            pkt = ScorePacket(
                scores={k: None for k in METRIC_KEYS},
                blink=None,
                is_warmup=True,
                warmup_count=self._raw_count,
                signal_quality=200,
            )
            self.new_scores.emit(pkt)
            return

        now = time.monotonic()
        if now - self._last_packet_time < 1.0:
            return
        self._last_packet_time = now

        b         = packet.get("eegPower", {})
        alpha     = b.get("lowAlpha", 0)  + b.get("highAlpha", 0)
        low_beta  = b.get("lowBeta",  0)
        high_beta = b.get("highBeta", 0)
        beta      = low_beta + high_beta
        theta     = b.get("theta",    0)
        delta     = b.get("delta",    0)

        raw_bands = {k: b.get(k, 0) for k in (
            "delta", "theta", "lowAlpha", "highAlpha",
            "lowBeta", "highBeta", "lowGamma", "midGamma",
        )}

        ratios = {
            "focus":   low_beta         / (alpha + theta + 1),
            "relax":   alpha            / (alpha + beta  + 1),
            "stress":  high_beta        / (alpha         + 1),
            "flow":    theta            / (alpha + beta  + 1),
            "fatigue": (delta + theta)  / (alpha + beta  + 1),
        }

        self._raw_count += 1
        is_warmup = self._raw_count <= WARMUP_PACKETS

        scores: dict[str, float | None] = {}
        for key, ratio in ratios.items():
            scores[key] = self._normalisers[key].normalise(ratio)

        blink = packet.get("blinkStrength")

        pkt = ScorePacket(
            scores=scores,
            blink=blink,
            is_warmup=is_warmup,
            warmup_count=self._raw_count,
            raw_bands=raw_bands,
            signal_quality=signal,
        )

        if not is_warmup and self._session_id is not None:
            if all(v is not None for v in scores.values()):
                self._db.insert_reading(self._session_id, {**scores, "blink": blink})

        if self.training_active and not is_warmup:
            self._update_training(scores)

        self.new_scores.emit(pkt)

    def _update_training(self, scores: dict) -> None:
        metric = self._training_metric
        score  = scores.get(metric)
        if score is None:
            return

        on_target = score >= self._training_threshold

        if on_target:
            self._seconds_on_target += 1

        if on_target and not self._was_on_target:
            self._db.log_training_event(
                self._training_session_id, "enter", score
            )
        elif not on_target and self._was_on_target:
            self._db.log_training_event(
                self._training_session_id, "exit", score
            )

        self._was_on_target = on_target
