FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend

ENV FLASK_ENV=production
ENV MODEL_PATH=/app/backend/tuned_model.pkl

EXPOSE 5000

CMD ["python", "backend/app.py"]