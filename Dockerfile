FROM python:3.11-alpine
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt && pip cache purge
COPY . .
ENTRYPOINT ["python", "-m", "tetik"]
