# Use the Python 3.14 (RC) slim image for a small footprint
FROM python:3.14-slim

# Set the working directory
WORKDIR /app

# Install system dependencies if needed (e.g., for sqlite or git)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ffmpeg \
    libopus0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (improves build caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the actual script
COPY . .

# Ensure Python output isn't buffered (so logs show up instantly)
ENV PYTHONUNBUFFERED=1

# Command to run your bot
CMD ["python", "palbot.py"]
