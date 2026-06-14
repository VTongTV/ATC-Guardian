"""AWC Weather Client — proxies all Aviation Weather Center API calls.

The AWC Data API has no CORS headers, so the frontend cannot call it
directly. All requests are routed through this async client on the
backend.

API docs: https://aviationweather.gov/api/data
"""

import asyncio
import logging
import time
from collections import deque

import httpx

logger = logging.getLogger(__name__)

AWC_BASE_URL = "https://aviationweather.gov/api/data"
AWC_REQUEST_TIMEOUT_SECONDS = 10
AWC_RATE_LIMIT_PER_MINUTE = 100
AWC_RETRIES = 2


class AWCAPIError(Exception):
    """Raised when the AWC API returns an unexpected response.

    Attributes:
        status_code: HTTP status code from AWC (or 0 for network errors).
        detail: Human-readable error description.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        """Initialize the error.

        Args:
            status_code: HTTP status code from AWC.
            detail: Human-readable description of the failure.
        """
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"AWC API error {status_code}: {detail}")


class AWCWeatherClient:
    """Async client for the Aviation Weather Center Data API.

    All external HTTP calls are proxied through this client so the
    frontend never calls AWC directly (no CORS support).

    Attributes:
        base_url: Root URL of the AWC Data API.
        timeout: Per-request timeout in seconds.
        _client: Underlying httpx async client.
        _request_timestamps: Rolling window of request times for rate limiting.
    """

    def __init__(
        self,
        base_url: str = AWC_BASE_URL,
        timeout: int = AWC_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        """Initialize the AWC client.

        Args:
            base_url: Root URL of the AWC Data API.
            timeout: Per-request timeout in seconds.
        """
        self.base_url = base_url
        self.timeout = timeout
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(timeout),
            follow_redirects=True,
            headers={"User-Agent": "ATC-Guardian/0.1"},
        )
        self._request_timestamps: deque[float] = deque()

    async def _request(
        self,
        method: str,
        path: str,
        params: dict[str, str | int | float] | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request with retry and rate-limit tracking.

        Args:
            method: HTTP method (GET, etc.).
            path: URL path relative to base_url.
            params: Optional query parameters.

        Returns:
            The httpx Response object.

        Raises:
            AWCAPIError: If the request fails after retries or returns
                a non-2xx status.
        """
        self._enforce_rate_limit()

        last_error: httpx.HTTPError | None = None
        for attempt in range(AWC_RETRIES + 1):
            try:
                response = await self._client.request(method, path, params=params)
                self._record_request()

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", "60"))
                    logger.warning(
                        "AWC rate limit hit, retrying after %ds", retry_after
                    )
                    raise AWCAPIError(429, f"Rate limited. Retry after {retry_after}s")

                if response.status_code >= 400:
                    raise AWCAPIError(
                        response.status_code,
                        f"AWC returned {response.status_code}: {response.text[:200]}",
                    )

                return response

            except AWCAPIError:
                raise
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "AWC request failed (attempt %d/%d): %s",
                    attempt + 1,
                    AWC_RETRIES + 1,
                    exc,
                )
                if attempt < AWC_RETRIES:
                    await self._backoff(attempt)

        raise AWCAPIError(
            0,
            f"AWC request failed after {AWC_RETRIES + 1} attempts: {last_error}",
        )

    def _enforce_rate_limit(self) -> None:
        """Drop timestamps older than 60s and warn if near the limit."""
        now = time.monotonic()
        cutoff = now - 60.0
        while self._request_timestamps and self._request_timestamps[0] < cutoff:
            self._request_timestamps.popleft()

        remaining = AWC_RATE_LIMIT_PER_MINUTE - len(self._request_timestamps)
        if remaining <= 10:
            logger.warning(
                "AWC rate limit approaching: %d requests remaining in window",
                remaining,
            )

    def _record_request(self) -> None:
        """Record the timestamp of a successful request."""
        self._request_timestamps.append(time.monotonic())

    @staticmethod
    async def _backoff(attempt: int) -> None:
        """Sleep with exponential backoff between retries.

        Args:
            attempt: Current retry attempt number (0-indexed).
        """
        delay = min(2 ** attempt, 10)
        await asyncio.sleep(delay)

    async def get_metar(self, icao_ids: list[str]) -> list[dict]:
        """Fetch METAR data for the given ICAO station IDs.

        Args:
            icao_ids: List of ICAO codes (e.g. ["KJFK", "KLGA"]).

        Returns:
            List of METAR data dicts from AWC JSON response.

        Raises:
            AWCAPIError: If the AWC API request fails.
        """
        params: dict[str, str | int | float] = {
            "ids": ",".join(icao_ids),
            "format": "json",
        }
        response = await self._request("GET", "/metar", params=params)
        return response.json()

    async def get_taf(self, icao_ids: list[str]) -> list[dict]:
        """Fetch TAF data for the given ICAO station IDs.

        Args:
            icao_ids: List of ICAO codes (e.g. ["KJFK", "KLGA"]).

        Returns:
            List of TAF data dicts from AWC JSON response.

        Raises:
            AWCAPIError: If the AWC API request fails.
        """
        params: dict[str, str | int | float] = {
            "ids": ",".join(icao_ids),
            "format": "json",
        }
        response = await self._request("GET", "/taf", params=params)
        return response.json()

    async def get_airsigmet(
        self, hazard_type: str | None = None
    ) -> list[dict]:
        """Fetch AIR/SIGMET data, optionally filtered by hazard type.

        Args:
            hazard_type: One of "conv", "turb", "ice", "ifr", "mt".
                None returns all types.

        Returns:
            List of AIR/SIGMET data dicts from AWC JSON response.

        Raises:
            AWCAPIError: If the AWC API request fails.
        """
        params: dict[str, str | int | float] = {"format": "json"}
        if hazard_type is not None:
            params["hazard"] = hazard_type
        response = await self._request("GET", "/airsigmet", params=params)
        return response.json()

    async def get_pirep(
        self,
        radius_nm: int = 100,
        lat: float | None = None,
        lon: float | None = None,
    ) -> list[dict]:
        """Fetch PIREP data within a radius of a point.

        Args:
            radius_nm: Search radius in nautical miles.
            lat: Center latitude in decimal degrees.
            lon: Center longitude in decimal degrees.

        Returns:
            List of PIREP data dicts from AWC JSON response.

        Raises:
            AWCAPIError: If the AWC API request fails.
        """
        params: dict[str, str | int | float] = {"format": "json"}
        if lat is not None and lon is not None:
            params["age"] = "3600"
            # AWC expects format: radius@lat,lon
            params["point"] = f"{radius_nm}@{lat},{lon}"
        response = await self._request("GET", "/pirep", params=params)
        return response.json()

    async def close(self) -> None:
        """Close the HTTP client session.

        Must be called during application shutdown to release connections.
        """
        await self._client.aclose()
        logger.info("AWC Weather client closed")
