FROM python:3.11-slim
WORKDIR /app
COPY scripts/requirements.txt .
RUN pip install -r requirements.txt
COPY scripts/ ./scripts/
COPY results/ ./results/
CMD ["sleep", "infinity"]