# Temporary Email Service Docker Image
# GitHub: https://github.com/TonnyWong1052/temp-email
FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY static/ ./static/
COPY run.py .

# Expose port
EXPOSE 1234

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:1234/api/health')" || exit 1

# Run application
CMD ["python", "run.py"]
