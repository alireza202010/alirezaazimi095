FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 TZ=Asia/Tehran
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium
COPY goldbot ./goldbot
COPY platforms.json .
CMD ["python", "-m", "goldbot", "run"]
