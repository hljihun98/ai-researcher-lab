FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV AI_RESEARCHER_DEMO_MODE=1
CMD ["python", "main.py", "샘플 질문: RAG 아키텍처를 정리해 주세요."]
