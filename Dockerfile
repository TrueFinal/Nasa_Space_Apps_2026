FROM python:3.12-slim
WORKDIR /app
ENV ZEPHYR_ROOT=/app
COPY pyproject.toml /app/
COPY src /app/src
RUN pip install --no-cache-dir .
COPY web /app/web
RUN mkdir -p /app/data /app/outputs
EXPOSE 8766
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8766/lab', timeout=4)" || exit 1
CMD ["python", "-m", "spherex_tracking.infrared", "serve", "--host", "0.0.0.0", "--port", "8766"]
