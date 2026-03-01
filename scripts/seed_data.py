#!/usr/bin/env python3
"""
ZenSensei Seed Data Script

Loads all sample JSON fixtures into the running microservices via their REST APIs.
Run after all services are healthy.

Usage:
    python scripts/seed_data.py [--base-url http://localhost:4000] [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import httpx

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("seed_data")

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://localhost:4000")
DEFAULT_ADMIN_EMAIL = "admin@zensensei.com"
DEFAULT_ADMIN_PASSWORD = "demo123!"


def load_json(filename: str) -> Any:
    path = DATA_DIR / filename
    log.info("Loading %s", path)
    with path.open() as f:
        return json.load(f)


class SeedClient:
    def __init__(self, base_url: str, dry_run: bool = False) -> None:
        self.base_url = base_url.rstrip("/")
        self.dry_run = dry_run
        self._token: str | None = os.getenv("SEED_JWT")
        self._client = httpx.Client(timeout=30, follow_redirects=True)

    def login(self, email: str, password: str) -> None:
        log.info("Authenticating as %s", email)
        if self.dry_run:
            log.info("[DRY-RUN] Would authenticate")
            self._token = "dry-run-token"
            return
        resp = self._client.post(
            f"{self.base_url}/api/v1/auth/login",
            json={"email": email, "password": password},
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        log.info("Authenticated successfully")

    def post(self, path: str, data: Any) -> Any:
        url = f"{self.base_url}{path}"
        if self.dry_run:
            log.info("[DRY-RUN] POST %s", url)
            return {}
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        resp = self._client.post(url, json=data, headers=headers)
        if resp.status_code not in (200, 201):
            log.warning("POST %s returned %d: %s", url, resp.status_code, resp.text[:200])
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()


def seed_users(client: SeedClient) -> None:
    log.info("Seeding users...")
    auth_data = load_json("auth.json")
    for user in auth_data.get("users", []):
        try:
            client.post("/api/v1/auth/register", {"email": user["email"], "display_name": user.get("display_name", "")})
            log.info("Created user: %s", user["email"])
        except Exception as exc:
            log.warning("User %s: %s", user["email"], exc)


def seed_goals(client: SeedClient) -> None:
    log.info("Seeding goals...")
    goals_data = load_json("sample_goals.json")
    for goal in goals_data.get("goals", []):
        try:
            client.post("/api/v1/goals", goal)
        except Exception as exc:
            log.warning("Goal %s: %s", goal.get("id"), exc)


def seed_events(client: SeedClient) -> None:
    log.info("Seeding events...")
    events_data = load_json("sample_events.json")
    for event in events_data.get("events", []):
        try:
            client.post("/api/v1/events", event)
        except Exception as exc:
            log.warning("Event %s: %s", event.get("id"), exc)


def main() -> None:
    parser = argparse.ArgumentParser(description="ZenSensei seed data loader")
    parser.add_argument("--base-url", default=GATEWAY_URL)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--admin-email", default=DEFAULT_ADMIN_EMAIL)
    parser.add_argument("--admin-password", default=DEFAULT_ADMIN_PASSWORD)
    args = parser.parse_args()

    client = SeedClient(base_url=args.base_url, dry_run=args.dry_run)
    try:
        client.login(args.admin_email, args.admin_password)
        seed_users(client)
        seed_goals(client)
        seed_events(client)
        log.info("Seeding complete!")
    finally:
        client.close()


if __name__ == "__main__":
    main()
