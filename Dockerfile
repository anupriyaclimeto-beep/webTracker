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

# Run the app (Railway sets PORT at runtime)
CMD ["python", "api.py"]
