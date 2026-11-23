FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY marketsim/ marketsim/
COPY sql/ sql/
COPY run_pipeline.py .
# the raw pack (data/) and the output folder are mounted by docker-compose
CMD ["python", "run_pipeline.py", "--load-db"]
