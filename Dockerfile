FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=7860

WORKDIR /app

COPY pipecat-amira/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY pipecat-amira/ ./

CMD ["sh", "-c", "python bot.py --host 0.0.0.0 --port ${PORT} -t daily --no-dialin"]
