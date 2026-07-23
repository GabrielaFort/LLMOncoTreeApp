FROM eclipse-temurin:21-jre-jammy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/LLMPathReportParser \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    OLLAMA_HOST=http://host.docker.internal:11434

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxcb1 \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt

COPY LLMOncoTreeApp/requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir -r /tmp/requirements.txt

COPY LLMPathReportParser /opt/LLMPathReportParser
COPY LLMOncoTreeApp /opt/LLMOncoTreeApp

WORKDIR /opt/LLMOncoTreeApp

EXPOSE 8501

CMD ["python3", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
