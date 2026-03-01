# ─── Frontend Dockerfile ────────────────────────────────────────────────────
# Serves the static ZenSensei web app via nginx.
# Build context: repo root  (docker build -f frontend/Dockerfile .)
# ────────────────────────────────────────────────────────────────────────────

# ── Stage 1: nothing to compile — static HTML/CSS/JS ────────────────────────
# We skip a Node build stage since there's no bundler.
# If you add a build step later (Vite, esbuild, etc.), insert it here.

FROM nginx:1.27-alpine

# ── Remove default nginx content ─────────────────────────────────────────────
RUN rm -rf /usr/share/nginx/html/*

# ── Copy static assets ───────────────────────────────────────────────────────
COPY frontend/public/ /usr/share/nginx/html/

# ── Custom nginx config ───────────────────────────────────────────────────────
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

# ── Health-check endpoint (nginx serves a 200 on /health) ────────────────────
# Handled in nginx.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
