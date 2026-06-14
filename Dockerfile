FROM python:3.11-slim

WORKDIR /app

# Copy only API requirements
COPY api/requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the API code
COPY api/ ./

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
  CMD python -c "import requests; requests.get('http://localhost:5000')"

# Run the app
CMD ["python", "api.py"]
