# syntax=docker/dockerfile:1

# Caddy with the Creator Portal baked in: the built frontend is served from /srv on the
# same origin as /api, so the httpOnly auth cookies work without CORS.

FROM node:22-alpine AS frontend

WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./
RUN npm run build

FROM caddy:2-alpine

COPY --from=frontend /frontend/dist /srv
