FROM python:3.11-slim

WORKDIR /app

ARG PORT=8080

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=${PORT}
ENV STREAMLIT_SERVER_PORT=${PORT}
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true

EXPOSE 8080

CMD ["streamlit", "run", "dashboard/App.py"]
