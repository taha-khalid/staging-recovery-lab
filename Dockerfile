FROM python:3.14.8-alpine

ENV PYTHONDONTWRITEBYTECODE 1 \
    PYTHONUNBUFFERED 1

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --no-compile -r requirements.txt

# Run the application as a non-root user
RUN adduser --disabled-password appuser

# Give permissions to appuser to access the application directory
RUN chown -R appuser:appuser /app

COPY --chown=appuser:appuser app/* ./app/

# Switch to the non-root user
USER appuser

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
