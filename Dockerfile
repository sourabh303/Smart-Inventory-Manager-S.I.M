FROM python:3.11-slim
WORKDIR /app
COPY . /app
RUN pip install --no-cache-dir -r requirements.txt && pip install flask-limiter python-dotenv
EXPOSE 5050
CMD ["python", "app.py"]