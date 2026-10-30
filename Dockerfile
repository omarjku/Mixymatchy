# One service: FastAPI serves the API, sign-in/PIN lock (/auth) and the built mobile app (docs/DECISIONS.md, 11-12).
# The legacy Next.js frontend (frontend/) is no longer part of the image; run it locally with `make frontend`.
FROM node:22-slim AS web
WORKDIR /web
COPY mobile/package.json mobile/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY mobile/ ./
# Empty API URL = same origin as the page.
ENV VITE_API_URL=""
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30" "pydantic>=2.7" "python-dotenv>=1.0" "anthropic==2.3.0"
COPY . .
RUN rm -rf frontend mobile
COPY --from=web /web/dist /app/static
ENV STATIC_DIR=/app/static
# Hugging Face Spaces runs containers as uid 1000; the app writes data/ (build, audit log) at start-up.
RUN useradd -m -u 1000 user && chown -R user /app
USER user
EXPOSE 8000
CMD ["sh", "deploy/start.sh"]
