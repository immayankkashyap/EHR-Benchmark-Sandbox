FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir fastapi uvicorn pydantic httpx

# Prepare logs directory with correct permissions for writing trajectories
RUN mkdir -p /app/logs && chmod 777 /app/logs

# Copy application files
COPY app /app/app

# Expose the API port
EXPOSE 8080

# Start the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
