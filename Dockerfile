FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# 데모 모드로 웹앱 실행. 실시간은 ANTHROPIC_API_KEY 주입 + 이 값 제거.
ENV AI_RESEARCHER_DEMO_MODE=1
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "gunicorn server:app --bind 0.0.0.0:${PORT} --timeout 300 --workers 2"]
