FROM python:3.14.5-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 COVERAGE_FILE=/tmp/.coverage
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home health
COPY --chown=health:health . .
USER health
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "30"]
