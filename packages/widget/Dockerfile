# syntax=docker/dockerfile:1.7
FROM node:24.6.0-alpine3.21 AS builder
WORKDIR /srv
COPY package.json package-lock.json tsconfig.base.json ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/api-client ./packages/api-client
COPY packages/widget ./packages/widget
RUN --mount=type=cache,target=/root/.npm npm ci \
    && npm run build --workspace @support-agent/widget

FROM nginxinc/nginx-unprivileged:1.27.5-alpine3.21 AS runtime
COPY infra/widget-nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /srv/packages/widget/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/health || exit 1
