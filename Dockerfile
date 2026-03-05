FROM python:3.11-alpine

# Install dcron (Alpine's cron) and bash
RUN apk add --no-cache dcron bash tzdata

WORKDIR /app

COPY . .

RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --upgrade pip && \
    /app/venv/bin/pip install -r requirements.txt

ENV PATH="/app/venv/bin:$PATH"

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
