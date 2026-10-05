# syntax=docker/dockerfile:1
#
# Frontend image: build the Vite bundle, serve it with nginx, and reverse-proxy
# /api to the backend so the browser only ever talks to one origin (no CORS).
#
# Build from the repository root:
#   docker build -f frontend/Dockerfile -t agri-frontend .

# ---------------------------------------------------------------------------
# Stage 1 - build
# ---------------------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /build

# Dependency layer: cached until package.json / lockfile change.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# VITE_API_BASE_URL stays the relative default (/api/v1) so requests go to the
# same origin and nginx proxies them. Baked in at build time, as Vite requires.
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 - serve
# ---------------------------------------------------------------------------
FROM nginx:1.27-alpine AS runtime

COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /build/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]