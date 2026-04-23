# SkyWave

A desktop EEG interface I built to work with the NeuroSky MindWave Mobile 2 — a consumer Bluetooth headset that streams live brainwave data. The app processes the raw signal in real time, normalises five mental-state metrics per user, records sessions to a local SQLite database, and includes a training mode with audio feedback for focus exercises.

**This repository is the demo version.** The hardware source is excluded since the headset costs ~$100 and most people won't have one. Everything else is fully functional — the mock data source simulates realistic EEG patterns so you can explore the complete interface without any hardware.

---

## What it does

- **Live monitor** — five metrics updated every second: focus, relaxation, stress, flow, and fatigue. Per-user rolling normalisation means scores reflect your personal baseline, not population averages.
- **Session recording** — start/stop a session at any time, add a note when you stop. All data is saved locally.
- **Training mode** — pick a metric and a threshold, and the app plays a tone when you cross it in either direction. Useful for neurofeedback-style focus exercises.
- **Raw waveform view** — live EEG band breakdown (delta, theta, alpha, beta, gamma) with a stacked area chart and per-band power meters.
- **History** — browse past sessions, see average scores, and replay the time series for any recording.
- **Multi-user** — full profile support with per-user score calibration and session history.

---

## Running it

Clone the repo, then run the script for your platform from the project root.

**Linux** — uses Docker, so all system dependencies are handled automatically:
```bash
./run_linux.sh
```
Requires [Docker](https://docs.docker.com/engine/install/).

**Windows** — double-click `run_win.bat` or run it from Command Prompt. It sets up a virtual environment and installs all dependencies automatically on first run.

The only prerequisite is [Python 3.10+](https://www.python.org/downloads/) — check *"Add Python to PATH"* during installation, then you're good to go.

---

## Stack

Python 3.11 · PyQt6 · pyqtgraph · SQLite · NumPy

---

## Project structure

```
├── main.py
├── requirements.txt
├── run_linux.sh
├── run_win.bat
├── backend/
│   ├── engine.py        # signal processing, metric scoring, session lifecycle
│   ├── database.py      # SQLite schema and queries
│   ├── normaliser.py    # per-user rolling normalisation (min/max with decay)
│   ├── sound.py         # sine-wave tone generation, no audio files needed
│   └── sources/
│       ├── base.py          # DataSource interface
│       └── mock_source.py   # simulated EEG with correlated band walks
└── frontend/
    ├── main_window.py
    ├── styles.py
    ├── utils.py
    ├── user_dialog.py
    ├── screens/
    │   ├── monitor_screen.py
    │   ├── training_screen.py
    │   ├── history_screen.py
    │   ├── waves_screen.py
    │   └── profile_screen.py
    └── widgets/
        ├── chart_widget.py   # scrolling real-time chart with blink markers
        └── metric_card.py
```

---

## Hardware version

The full version reads from a NeuroSky MindWave Mobile 2 over Bluetooth — a single-channel consumer EEG headset that costs around $100 and measures attention, meditation, and raw EEG power across five frequency bands. Connecting it is straightforward (the device speaks a documented serial protocol), but since most people don't have one, I didn't include it here. If you do own a headset and want to wire it up, open an issue.

---

## License

MIT
