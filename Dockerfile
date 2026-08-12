# ── Base: Ubuntu Jammy with Python 3.11 ───────────────────────────────────
FROM ubuntu:22.04

# ── System deps: Python 3.11, pip, g++, wget, curl ───────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-distutils \
        python3-pip \
        g++ \
        wget \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Java 25 JDK from Adoptium (JPlag 6.3.0 needs Java 25; JDK for javac) ──
RUN wget -q "https://api.adoptium.net/v3/binary/latest/25/ga/linux/x64/jdk/hotspot/normal/eclipse" \
        -O /tmp/jdk25.tar.gz \
    && mkdir -p /opt/java/25 \
    && tar -xzf /tmp/jdk25.tar.gz -C /opt/java/25 --strip-components=1 \
    && rm /tmp/jdk25.tar.gz
ENV JAVA_HOME=/opt/java/25
ENV PATH="$JAVA_HOME/bin:$PATH"

# Make python3 / pip point to 3.11
RUN update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.11 1 \
 && python3 -m pip install --no-cache-dir --upgrade pip

# ── Python dependencies ───────────────────────────────────────────────────
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# ── Application code ──────────────────────────────────────────────────────
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Config lives in /app/config so it can be mounted as a persistent volume
# without shadowing the code.
ENV PREGRADER_CONFIG_DIR=/app/config
RUN mkdir -p /app/config

EXPOSE 5000
ENV PYTHONUNBUFFERED=1

CMD ["python3", "frontend/app.py"]
