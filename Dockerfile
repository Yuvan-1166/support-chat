# ── Build stage ──────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# Install uv
RUN pip install --no-cache-dir uv

WORKDIR /build

# Copy dependency file first for better caching
COPY requirements.txt .

# Create virtual environment
RUN uv venv /opt/venv

# Activate venv in PATH
ENV PATH="/opt/venv/bin:$PATH"

# Install dependencies
RUN uv pip install --no-cache -r requirements.txt

# ── Runtime stage ────────────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# Copy venv from builder
COPY --from=builder /opt/venv /opt/venv

# Activate venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY app/ ./app/

# Non-root user for security
RUN useradd --create-home appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
