FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
COPY requirements.txt requirements-web.txt ./
RUN pip install -r requirements-web.txt
COPY screener ./screener
COPY config.toml pyproject.toml ./
RUN mkdir -p /data/out
ENV SCREENER_CONFIG=/app/config.toml
VOLUME ["/data"]
EXPOSE 8080
CMD ["python", "-m", "screener", "-c", "/app/config.toml", "serve", "--host", "0.0.0.0", "--port", "8080"]
