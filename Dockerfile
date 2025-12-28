FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ ./src/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create non-root user
RUN useradd -m -u 1000 hopper && \
    chown -R hopper:hopper /app

USER hopper

# Expose port
EXPOSE 8000

# Default command
CMD ["uvicorn", "hopper.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
