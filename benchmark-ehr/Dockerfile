FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py prepare.py ingest.py index.html ./
CMD ["python", "server.py", "--host", "0.0.0.0", "--fhir", "http://hapi-fhir-jpaserver:8080/fhir"]
