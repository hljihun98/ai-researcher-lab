FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

# 기본은 데모 모드(로컬 도커 시연용). 실시간은 -e GEMINI_API_KEY=... 주입 +
# -e AI_RESEARCHER_DEMO_MODE=0 으로 덮어쓴다.
ENV AI_RESEARCHER_DEMO_MODE=1
ENV PORT=8000
EXPOSE 8000
# 세션 기록이 프로세스 메모리에 있으므로 워커 1개(조회 일관성). render.yaml과 동일.
CMD ["sh", "-c", "gunicorn server:app --bind 0.0.0.0:${PORT} --timeout 300 --workers 1"]
