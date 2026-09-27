FROM python:3.12.8-slim
WORKDIR /app
COPY backend/simulator/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/demo_ai ./demo_ai
CMD ["uvicorn", "demo_ai.main:app", "--host", "0.0.0.0", "--port", "8081"]
