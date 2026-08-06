# syntax=docker/dockerfile:1.7
FROM node:24.6.0-alpine3.21 AS dependencies
WORKDIR /srv
COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
COPY packages/api-client/package.json ./packages/api-client/package.json
COPY packages/widget/package.json ./packages/widget/package.json
RUN --mount=type=cache,target=/root/.npm npm ci

FROM dependencies AS builder
ARG NEXT_PUBLIC_API_URL
ARG NEXT_PUBLIC_WIDGET_LOADER_URL
ENV NEXT_TELEMETRY_DISABLED=1
COPY tsconfig.base.json ./
COPY apps/web ./apps/web
COPY packages/api-client ./packages/api-client
RUN npm run build --workspace @support-agent/web

FROM node:24.6.0-alpine3.21 AS runtime
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000
WORKDIR /srv
RUN addgroup --system --gid 10001 support-agent \
    && adduser --system --uid 10001 --ingroup support-agent support-agent
COPY --from=builder --chown=support-agent:support-agent /srv/apps/web/.next/standalone ./
COPY --from=builder --chown=support-agent:support-agent /srv/apps/web/.next/static ./apps/web/.next/static
USER support-agent
EXPOSE 3000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
CMD ["node", "apps/web/server.js"]
