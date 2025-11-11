FROM python:3.12-slim

WORKDIR /workspace

# Install system dependencies INCLUDING GO
RUN apt-get update && apt-get install -y \
    git \
    wget \
    curl \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Install Go
RUN wget https://go.dev/dl/go1.22.0.linux-amd64.tar.gz && \
    tar -C /usr/local -xzf go1.22.0.linux-amd64.tar.gz && \
    rm go1.22.0.linux-amd64.tar.gz

# Set Go environment variables
ENV PATH="/usr/local/go/bin:${PATH}"
ENV GOPATH="/go"
ENV PATH="${GOPATH}/bin:${PATH}"

# Install golangci-lint
RUN curl -sSfL https://raw.githubusercontent.com/golangci/golangci-lint/master/install.sh | sh -s -- -b /usr/local/bin v1.64.8

# Copy requirements and install Python dependencies
COPY requirements.txt /workspace/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy framework code
COPY hybrid_rag_framework.py /workspace/hybrid_rag_framework.py

ENV FLASK_RUN_HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

EXPOSE 5001

CMD ["python", "hybrid_rag_framework.py"]
