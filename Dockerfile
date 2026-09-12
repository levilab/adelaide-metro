FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ARG PORT=8080

RUN pip install --no-cache-dir -r requirements.txt

COPY ca.pem /app/ca.pem

COPY . .

ENV SSL_CERT_FILE=/app/ca.pem

ENV PORT=${PORT}
ENV STREAMLIT_SERVER_PORT=${PORT}
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true

EXPOSE 8080

CMD ["streamlit", "run", "dashboard/App.py"]
