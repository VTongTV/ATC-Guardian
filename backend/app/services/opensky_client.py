"""OpenSky Network ADS-B API client.

Fetches live aircraft state vectors from the OpenSky Network REST API
for a geographic bounding box. Falls back gracefully when credentials
are missing or the API is unreachable.
"""

import asyncio
import logging
from datetime import datetime, timezone

import httpx

from shared.constants import (
    METERS_PER_SECOND_TO_FPM,
    METERS_PER_SECOND_TO_KNOTS,
    METERS_TO_FEET,
    OPENSKY_POLL_INTERVAL_SECONDS,
    OPENSKY_DAILY_CREDIT_LIMIT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenSky API constants
# ---------------------------------------------------------------------------

OPENSKY_BASE_URL = "https://opensky-network.org/api"
OPENSKY_STATES_ENDPOINT = "/states/all"
OPENSKY_REQUEST_TIMEOUT_SECONDS = 15
OPENSKY_RETRY_ATTEMPTS = 2

# Default bounding box: JFK area
JFK_BBOX_LAMIN = 40.5
JFK_BBOX_LAMAX = 40.9
JFK_BBOX_LOMIN = -74.2
JFK_BBOX_LOMAX = -73.5

# OpenSky state vector indices (array positions in the response)
_IDX_ICAO24 = 0
_IDX_CALLSIGN = 1
_IDX_ORIGIN_COUNTRY = 2
_IDX_TIME_POSITION = 3
_IDX_LAST_CONTACT = 4
_IDX_LONGITUDE = 5
_IDX_LATITUDE = 6
_IDX_BARO_ALT = 7
_IDX_ON_GROUND = 8
_IDX_VELOCITY = 9
_IDX_HEADING = 10
_IDX_VERT_RATE = 11
_IDX_SENSORS = 12
_IDX_GEO_ALT = 13
_IDX_SQUAWK = 14
_IDX_SPI = 15
_IDX_POSITION_SOURCE = 16


class OpenSkyAPIError(Exception):
    """Raised when the OpenSky API returns an error or is unreachable."""


class OpenSkyClient:
    """Async client for the OpenSky Network ADS-B API.

    Fetches real-time aircraft state vectors for a geographic bounding box.
    Requires an OpenSky free account (LDAP credentials) for authenticated
    requests. Without credentials the client refuses to query the API.

    Attributes:
        is_configured: Whether valid credentials are available.
    """

    def __init__(self, username: str | None = None, password: str | None = None) -> None:
        """Initialize with optional credentials.

        Args:
            username: OpenSky Network username (LDAP). If None, client is
                unconfigured and get_states will raise OpenSkyAPIError.
            password: OpenSky Network password. If None, client is unconfigured.
        """
        self._username = username
        self._password = password
        self._client: httpx.AsyncClient | None = None

    @property
    def is_configured(self) -> bool:
        """Whether valid credentials are available.

        Returns:
            True if both username and password are non-empty strings.
        """
        return bool(self._username and self._password)

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared httpx.AsyncClient.

        Returns:
            A configured httpx.AsyncClient with basic auth credentials.

        Raises:
            OpenSkyAPIError: If credentials are not configured.
        """
        if self._client is None or self._client.is_closed:
            if not self.is_configured:
                raise OpenSkyAPIError(
                    "OpenSky credentials not configured. "
                    "Set OPENSKY_USERNAME and OPENSKY_PASSWORD."
                )
            self._client = httpx.AsyncClient(
                auth=(self._username, self._password),  # type: ignore[arg-type]
                timeout=OPENSKY_REQUEST_TIMEOUT_SECONDS,
            )
        return self._client

    def _parse_state_vector(self, raw: list, server_time: float) -> dict | None:
        """Convert a raw OpenSky state vector array to an AircraftState-compatible dict.

        Args:
            raw: A single state vector array from the OpenSky API response.
            server_time: Server time from the response root, used as fallback.

        Returns:
            A dict with keys matching the AircraftState model, or None if the
            vector is malformed or the aircraft is on the ground.
        """
        if not raw or len(raw) < 12:
            return None

        try:
            latitude = raw[_IDX_LATITUDE]
            longitude = raw[_IDX_LONGITUDE]
            baro_alt = raw[_IDX_BARO_ALT]
            velocity = raw[_IDX_VELOCITY] or 0.0
            heading = raw[_IDX_HEADING]
            vert_rate = raw[_IDX_VERT_RATE] or 0.0
            on_ground = raw[_IDX_ON_GROUND] or False
            squawk = raw[_IDX_SQUAWK] or "1200"
            callsign = (raw[_IDX_CALLSIGN] or "").strip()
        except (IndexError, TypeError):
            return None

        # Skip aircraft with no position data
        if latitude is None or longitude is None:
            return None

        # Skip on-ground aircraft
        if on_ground:
            return None

        # Convert units: meters -> feet, m/s -> kts, m/s -> fpm
        altitude_ft = int(round((baro_alt or 0.0) * METERS_TO_FEET))
        speed_kts = round((velocity or 0.0) * METERS_PER_SECOND_TO_KNOTS, 1)
        vertical_speed_fpm = int(round((vert_rate or 0.0) * METERS_PER_SECOND_TO_FPM))

        # Determine timestamp
        time_pos = raw[_IDX_TIME_POSITION] or raw[_IDX_LAST_CONTACT] or server_time
        timestamp = datetime.fromtimestamp(time_pos, tz=timezone.utc)

        # Determine squawk — strip whitespace and default to 1200
        squawk_clean = str(squawk).replace(".", "").strip()[:4]
        if len(squawk_clean) != 4:
            squawk_clean = "1200"

        return {
            "callsign": callsign or "????",
            "latitude": latitude,
            "longitude": longitude,
            "altitude_ft": max(0, altitude_ft),
            "heading_deg": heading or 0.0,
            "speed_kts": max(0.0, speed_kts),
            "vertical_speed_fpm": vertical_speed_fpm,
            "squawk": squawk_clean,
            "timestamp": timestamp,
            "on_ground": False,
        }

    async def get_states(
        self,
        lamin: float,
        lamax: float,
        lomin: float,
        lomax: float,
    ) -> list[dict]:
        """Fetch aircraft states within a bounding box.

        Args:
            lamin: Minimum latitude (south edge).
            lamax: Maximum latitude (north edge).
            lomin: Minimum longitude (west edge).
            lomax: Maximum longitude (east edge).

        Returns:
            List of aircraft state dicts with keys matching AircraftState model.

        Raises:
            OpenSkyAPIError: If the API returns an error or is unreachable.
        """
        if not self.is_configured:
            raise OpenSkyAPIError(
                "OpenSky credentials not configured. "
                "Set OPENSKY_USERNAME and OPENSKY_PASSWORD."
            )

        client = self._get_client()
        params = {
            "lamin": lamin,
            "lamax": lamax,
            "lomin": lomin,
            "lomax": lomax,
        }

        last_error: Exception | None = None

        for attempt in range(OPENSKY_RETRY_ATTEMPTS):
            try:
                response = await client.get(
                    f"{OPENSKY_BASE_URL}{OPENSKY_STATES_ENDPOINT}",
                    params=params,
                )

                if response.status_code == 401:
                    raise OpenSkyAPIError(
                        "OpenSky authentication failed. Check credentials."
                    )
                if response.status_code == 429:
                    raise OpenSkyAPIError(
                        "OpenSky rate limit exceeded (429). "
                        "Upgrade account or wait before retrying."
                    )
                if response.status_code != 200:
                    raise OpenSkyAPIError(
                        f"OpenSky API returned HTTP {response.status_code}: "
                        f"{response.text[:200]}"
                    )

                data = response.json()
                server_time = data.get("time", 0.0)
                raw_states = data.get("states") or []

                aircraft = []
                for raw_state in raw_states:
                    parsed = self._parse_state_vector(raw_state, server_time)
                    if parsed is not None:
                        aircraft.append(parsed)

                logger.info(
                    "OpenSky: fetched %d aircraft from %d raw states",
                    len(aircraft),
                    len(raw_states),
                )
                return aircraft

            except OpenSkyAPIError:
                raise
            except httpx.TimeoutException as exc:
                last_error = exc
                logger.warning(
                    "OpenSky request timed out (attempt %d/%d)",
                    attempt + 1,
                    OPENSKY_RETRY_ATTEMPTS,
                )
            except httpx.HTTPError as exc:
                last_error = exc
                logger.warning(
                    "OpenSky HTTP error (attempt %d/%d): %s",
                    attempt + 1,
                    OPENSKY_RETRY_ATTEMPTS,
                    exc,
                )

            # Brief backoff before retry
            if attempt < OPENSKY_RETRY_ATTEMPTS - 1:
                await asyncio.sleep(1.0)

        raise OpenSkyAPIError(
            f"OpenSky API unreachable after {OPENSKY_RETRY_ATTEMPTS} attempts: "
            f"{last_error}"
        )

    async def get_states_jfk(self) -> list[dict]:
        """Fetch aircraft states in the JFK area bounding box.

        Uses a bounding box centered on the JFK TMA:
            lamin=40.5, lamax=40.9, lomin=-74.2, lomax=-73.5

        Returns:
            List of aircraft state dicts within the JFK bounding box.

        Raises:
            OpenSkyAPIError: If the API call fails.
        """
        return await self.get_states(
            lamin=JFK_BBOX_LAMIN,
            lamax=JFK_BBOX_LAMAX,
            lomin=JFK_BBOX_LOMIN,
            lomax=JFK_BBOX_LOMAX,
        )

    async def close(self) -> None:
        """Close the HTTP client session.

        Safe to call multiple times. After close, the client will be
        recreated on the next request.
        """
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.debug("OpenSky client session closed")
