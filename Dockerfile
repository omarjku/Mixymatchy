# One service: FastAPI serves the API and the statically exported Next.js frontend.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Empty API URL = same origin as the page.
ENV STATIC_EXPORT=1 NEXT_PUBLIC_API_URL=""
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.7" "python-dotenv>=1.0"
COPY . .
COPY --from=web /web/out /app/static
ENV STATIC_DIR=/app/static
CMD ["sh", "deploy/start.sh"]
