# Railway Per-Service Configuration Reference
#
# Railway monorepo approach: all services share the SAME repo root (.)
# as their build context, so shared/ is always available.
# Each service points to its own Dockerfile via the Railway dashboard or CLI.
#
# Dashboard setup for each service:
#   Root Directory : .   (repo root)
#   Dockerfile Path: <see per-service config below>
