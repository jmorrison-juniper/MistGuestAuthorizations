# MistGuestAuthorizations Container Image
# Compatible with both Docker and Podman (OCI-compliant)
# Multi-architecture: linux/amd64, linux/arm64
FROM python:3.11-slim

# Metadata following OCI standards
LABEL org.opencontainers.image.title="MistGuestAuthorizations"
LABEL org.opencontainers.image.description="Juniper Mist Guest WiFi Pre-Authorization Portal"
LABEL org.opencontainers.image.version="25.12.17.12.00"
LABEL org.opencontainers.image.vendor="Joseph Morrison"
LABEL org.opencontainers.image.authors="Joseph Morrison <jmorrison@juniper.net>"
LABEL org.opencontainers.image.licenses="CC-BY-NC-SA-4.0"
LABEL org.opencontainers.image.documentation="https://github.com/jmorrison-juniper/MistGuestAuthorizations"
LABEL org.opencontainers.image.source="https://github.com/jmorrison-juniper/MistGuestAuthorizations"
LABEL maintainer="Joseph Morrison <jmorrison@juniper.net>"

# Install minimal system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r mistguest && useradd -r -g mistguest -m -s /bin/bash mistguest

# Set working directory
WORKDIR /app

# Create config directory for logs
RUN mkdir -p /config/logs && chown -R mistguest:mistguest /config

# Copy requirements first for better Docker layer caching
COPY requirements.txt ./

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt \
        --trusted-host pypi.org \
        --trusted-host pypi.python.org \
        --trusted-host files.pythonhosted.org

# Copy application files
COPY app.py mist_connection.py ./
COPY templates ./templates/

# Set ownership to non-root user
RUN chown -R mistguest:mistguest /app

# Switch to non-root user
USER mistguest

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=5000
ENV LOG_LEVEL=INFO

# Expose the Flask port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# Run the application
CMD ["python", "app.py"]
