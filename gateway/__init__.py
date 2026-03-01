"""
ZenSensei API Gateway

Unified entry point that proxies all requests to the appropriate
downstream microservice with JWT validation, rate limiting, CORS,
and request logging.
"""

__version__ = "1.0.0"
__service__ = "api-gateway"
