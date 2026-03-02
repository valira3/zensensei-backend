# ─── ZenSensei Frontend ───────────────────────────────────────────────────────
# Serves the static SPA via nginx with API proxy to the gateway service.
# ──────────────────────────────────────────────────────────────────────────────

FROM nginx:1.25-alpine

# ── Install envsubst (part of gettext) ─────────────────────────────────────
RUN apk add --no-cache gettext

# ── Copy static assets ─────────────────────────────────────────────────────
COPY frontend/public/ /usr/share/nginx/html/

# ── Copy nginx config template ──────────────────────────────────────────────
COPY frontend/nginx.conf /etc/nginx/templates/default.conf.template

# ── Default environment variables ──────────────────────────────────────────
# PORT is injected by Railway at runtime
ENV PORT=3000
ENV API_GATEWAY_URL=http://gateway.railway.internal:4000

EXPOSE 3000

# ── Health check ───────────────────────────────────────────────────────────
HEALTHCHECK --interval=15s --timeout=5s --retries=3 --start-period=10s \
    CMD wget -q --spider http://localhost:${PORT}/health || exit 1

# ── Start nginx with env substitution ────────────────────────────────────
# envsubst replaces ${PORT} and ${API_GATEWAY_URL} in the template
CMD ["/bin/sh", "-c", "envsubst '${PORT} ${API_GATEWAY_URL}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
