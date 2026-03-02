# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly.

**Email:** security@zensensei.net

Please do NOT open a public GitHub issue for security vulnerabilities.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.x     | ✅        |

## Security Measures

- All API endpoints require authentication
- Passwords are hashed with bcrypt
- JWTs use HS256 signing with per-environment secrets
- All inter-service communication uses Railway's private network
- CORS is restricted to approved origins
- Rate limiting is enforced at both nginx and application level
- OAuth tokens are encrypted at rest with Fernet
