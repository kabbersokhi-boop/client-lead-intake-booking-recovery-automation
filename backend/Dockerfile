FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY frontend/ /frontend/
RUN chmod +x /app/scripts/start.sh
EXPOSE 8000
CMD ["/app/scripts/start.sh"]
