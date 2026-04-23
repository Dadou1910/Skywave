FROM python:3.11-slim

# System dependencies for PyQt6 / Qt6
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Qt6 runtime
    libgl1 \
    libegl1 \
    libglib2.0-0 \
    libdbus-1-3 \
    libxcb1 \
    libxcb-cursor0 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-randr0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-xinerama0 \
    libxcb-xkb1 \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    libx11-xcb1 \
    libxi6 \
    libxrender1 \
    libxext6 \
    libfontconfig1 \
    libfreetype6 \
    # Audio / QtMultimedia
    libasound2 \
    libpulse0 \
    libgssapi-krb5-2 \
    libgstreamer1.0-0 \
    libgstreamer-plugins-base1.0-0 \
    # Fonts
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONUNBUFFERED=1
ENV QT_QPA_PLATFORM=xcb

CMD ["python", "main.py"]
