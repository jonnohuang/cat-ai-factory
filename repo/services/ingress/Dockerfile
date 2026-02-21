FROM python:3.13-slim

WORKDIR /app

# Copy requirements and install
COPY repo/services/ingress/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire repo structure (needed for shared schemas and persistence)
# In production, you might want to be more selective.
COPY . .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Run the service
CMD ["sh", "-c", "uvicorn repo.services.ingress.main:app --host 0.0.0.0 --port $PORT"]
