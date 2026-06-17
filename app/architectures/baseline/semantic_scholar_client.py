"""Semantic Scholar Graph API client.

Synchronous, ``urllib``-based. Handles timeout, retry with exponential backoff,
429 rate-limiting, 5xx retry, invalid-JSON, request logging, optional API key,
and raw-response caching (SQLite ``api_cache`` + ``data/baseline/raw_cache``).

Works without an API key. Caching makes runs reproducible: a cache hit replays
the exact prior response, so the pipeline is deterministic given a fixed cache.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.architectures.baseline import constants, db
from app.architectures.baseline.errors import APIResponseError, RateLimitError
from app.state import store

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ClientStats:
    api_call_count: int = 0
    cache_hit_count: int = 0
    cache_miss_count: int = 0
    rate_limit_events: int = 0
    latencies_ms: List[float] = field(default_factory=list)

    @property
    def avg_latency_ms(self) -> float:
        return sum(self.latencies_ms) / len(self.latencies_ms) if self.latencies_ms else 0.0


class SemanticScholarClient:
    """A thin, cache-aware client. One instance per run."""

    def __init__(
        self,
        conn: Optional[sqlite3.Connection],
        enable_cache: bool = True,
        raw_cache_dir: Path = constants.RAW_CACHE_DIR,
        sleeper=time.sleep,
    ) -> None:
        self.conn = conn
        self.enable_cache = enable_cache and conn is not None
        self.raw_cache_dir = raw_cache_dir
        self.stats = ClientStats()
        self._sleep = sleeper

    # ------------------------------------------------------------------ #
    def _cache_key(self, endpoint: str, params: Dict[str, Any]) -> str:
        basis = endpoint + "?" + urllib.parse.urlencode(sorted(params.items()))
        return store.hash_text(basis)

    def _headers(self) -> Dict[str, str]:
        headers = {"User-Agent": constants.USER_AGENT, "Accept": "application/json"}
        key = constants.api_key()
        if key:
            headers["x-api-key"] = key
        return headers

    def _http_get(self, url: str) -> tuple[int, Optional[Dict[str, Any]]]:
        """One HTTP GET; returns (status_code, parsed_json_or_None)."""
        req = urllib.request.Request(url, headers=self._headers())
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=constants.request_timeout_s()) as resp:
                body = resp.read()
                status = resp.getcode()
        except urllib.error.HTTPError as exc:
            status = exc.code
            body = exc.read() if hasattr(exc, "read") else b""
        finally:
            self.stats.latencies_ms.append((time.perf_counter() - started) * 1000.0)

        if status == 429:
            raise RateLimitError("Semantic Scholar returned 429 (rate limited)")
        if status >= 500:
            raise APIResponseError(f"Semantic Scholar server error {status}")

        if status != 200:
            return status, None
        try:
            return status, json.loads(body)
        except json.JSONDecodeError as exc:
            raise APIResponseError(f"Invalid JSON from Semantic Scholar: {exc}") from exc

    def _request(self, endpoint: str, params: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """GET with cache + retry. Returns parsed JSON or None on hard failure."""
        cache_key = self._cache_key(endpoint, params)

        if self.enable_cache:
            cached = db.cache_get(self.conn, cache_key)
            if cached is not None:
                self.stats.cache_hit_count += 1
                logger.debug("cache hit: %s", endpoint)
                return cached
            self.stats.cache_miss_count += 1

        url = f"{constants.base_url()}{endpoint}?{urllib.parse.urlencode(params)}"
        data: Optional[Dict[str, Any]] = None
        last_exc: Optional[Exception] = None

        for attempt in range(constants.MAX_ATTEMPTS):
            try:
                self.stats.api_call_count += 1
                status, data = self._http_get(url)
                self._sleep(constants.RATE_LIMIT_SLEEP_S)
                break
            except RateLimitError as exc:
                last_exc = exc
                self.stats.rate_limit_events += 1
                logger.warning("429 on attempt %d for %s", attempt + 1, endpoint)
            except APIResponseError as exc:
                last_exc = exc
                logger.warning("API error on attempt %d: %s", attempt + 1, exc)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last_exc = exc
                logger.warning("network error on attempt %d: %s", attempt + 1, exc)

            if attempt < len(constants.RETRY_BACKOFF_S):
                self._sleep(constants.RETRY_BACKOFF_S[attempt])
        else:
            logger.error("giving up on %s after %d attempts: %s",
                         endpoint, constants.MAX_ATTEMPTS, last_exc)
            raise APIResponseError(str(last_exc) if last_exc else "request failed")

        if self.enable_cache and data is not None:
            db.cache_put(self.conn, cache_key, constants.SOURCE, endpoint, params,
                         data, 200, _now())
            self._write_raw_cache(cache_key, data)
        return data

    def _write_raw_cache(self, cache_key: str, data: Dict[str, Any]) -> None:
        try:
            self.raw_cache_dir.mkdir(parents=True, exist_ok=True)
            store.write_json(self.raw_cache_dir / f"{cache_key}.json", data)
        except OSError as exc:  # caching is best-effort; never fail the run
            logger.debug("raw cache write failed: %s", exc)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def search(self, query: str, fields: List[str], limit: int) -> List[Dict[str, Any]]:
        """Paper search; returns the list of raw paper objects (possibly empty)."""
        params = {
            "query": query,
            "fields": ",".join(fields),
            "limit": min(max(1, limit), 100),
        }
        data = self._request(constants.SEARCH_PATH, params)
        return list((data or {}).get("data", []) or [])

    def get_paper(self, paper_id: str, fields: List[str]) -> Optional[Dict[str, Any]]:
        """Lookup a single paper by id (used for target-paper resolution)."""
        endpoint = f"{constants.PAPER_PATH}/{urllib.parse.quote(paper_id, safe='')}"
        params = {"fields": ",".join(fields)}
        try:
            return self._request(endpoint, params)
        except APIResponseError:
            return None
