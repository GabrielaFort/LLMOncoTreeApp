FROM eclipse-temurin:21-jre-jammy

LABEL org.opencontainers.image.source="https://github.com/GabrielaFort/LLMOncoTreeApp"
LABEL org.opencontainers.image.description="Streamlit app for running the LLM OncoTree classifier"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    OLLAMA_HOST=http://host.docker.internal:11434

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxcb1 \
        python3 \
        python3-pip \
        python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/LLMOncoTreeApp

ARG TORCH_VERSION=2.13.0+cpu
ARG TORCHVISION_VERSION=0.28.0+cpu

COPY requirements.txt /tmp/requirements.txt
RUN python3 -m pip install --no-cache-dir --upgrade pip \
    && python3 -m pip install --no-cache-dir \
        --extra-index-url https://download.pytorch.org/whl/cpu \
        torch==${TORCH_VERSION} \
        torchvision==${TORCHVISION_VERSION} \
    && python3 -m pip install --no-cache-dir -r /tmp/requirements.txt

COPY . /opt/LLMOncoTreeApp
RUN python3 scripts/setup_external_deps.py \
    && rm -rf local_test __pycache__ scripts/__pycache__

EXPOSE 8501

CMD ["python3", "-m", "streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
