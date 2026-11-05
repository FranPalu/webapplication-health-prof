#!/usr/bin/env python3
"""Measure the local proxy using a disposable synthetic patient fixture on stdin."""

import argparse
import json
import math
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from urllib.error import HTTPError, URLError
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

BASE = "http://localhost:8080"
PATHS = (
    "/health/ready/",
    "/api/v1/organizations/",
    "/api/v1/patients/",
    "/api/v1/shares/",
    "/api/v1/appointments/bookings/",
    "/api/v1/pharmacy/reservations/",
    "/api/v1/payments/orders/",
    "/api/v1/research/catalog/",
)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def measure(path, headers):
    started = time.perf_counter()
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(
            Request(BASE + path, headers=headers), timeout=10
        ) as response:
            response.read()
            status = str(response.status)
    except HTTPError as exc:
        status = str(exc.code)
        exc.close()
    except (URLError, TimeoutError):
        status = "transport_error"
    return (time.perf_counter() - started) * 1000, status


def summarize(samples):
    times = sorted(duration for duration, _ in samples)
    statuses = Counter(status for _, status in samples)
    return {
        "samples": len(times),
        "p50_ms": round(times[math.ceil(len(times) * 0.50) - 1], 2),
        "p95_ms": round(times[math.ceil(len(times) * 0.95) - 1], 2),
        "statuses": dict(sorted(statuses.items())),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--samples", type=int, default=100, help="Requests per endpoint"
    )
    parser.add_argument("--concurrency", type=int, default=8)
    args = parser.parse_args()
    if not 1 <= args.concurrency <= args.samples <= 2000:
        parser.error("Require 1 <= concurrency <= samples <= 2000")

    fixture = json.load(sys.stdin)
    email = fixture["patient_email"]
    if not email.endswith("@patients.example"):
        parser.error("A disposable synthetic patient is required")

    jar = CookieJar()
    client = build_opener(ProxyHandler({}), NoRedirect(), HTTPCookieProcessor(jar))
    with client.open(BASE + "/api/v1/auth/session/", timeout=10):
        csrf = next(cookie.value for cookie in jar if cookie.name == "csrftoken")
    login = Request(
        BASE + "/api/v1/auth/login/",
        data=json.dumps(
            {"email": email, "password": fixture["patient_password"]}
        ).encode(),
        headers={
            "Content-Type": "application/json",
            "X-CSRFToken": csrf,
            "Origin": BASE,
        },
    )
    with client.open(login, timeout=10):
        headers = {"Cookie": "; ".join(f"{c.name}={c.value}" for c in jar)}

    results = {}
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        for path in PATHS:
            for _ in range(5):
                measure(path, headers)
            samples = list(
                executor.map(measure, [path] * args.samples, [headers] * args.samples)
            )
            results[path] = summarize(samples)
    print(
        json.dumps(
            {
                "concurrency": args.concurrency,
                "warmup_per_endpoint": 5,
                "endpoints": results,
            },
            indent=2,
        )
    )
    return int(
        any(
            row["statuses"] != {"200": args.samples} or row["p95_ms"] >= 500
            for row in results.values()
        )
    )


if __name__ == "__main__":
    sys.exit(main())
