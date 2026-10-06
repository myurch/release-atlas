FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --uid 10001 --create-home atlas \
    && mkdir /data && chown atlas:atlas /data
COPY backend ./backend
COPY data ./data
COPY dist ./dist
COPY LICENSE THIRD_PARTY_NOTICES.md ./
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 ATLAS_HOST=0.0.0.0 ATLAS_DATA_DIR=/data
USER 10001
EXPOSE 8765
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3)"
CMD ["python", "-m", "backend"]
