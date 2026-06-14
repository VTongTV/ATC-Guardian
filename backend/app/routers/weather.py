"""Weather router — proxies Aviation Weather Center data to the frontend.

The AWC Data API has no CORS headers, so all weather requests must be
proxied through this backend router. The AWCWeatherClient handles the
actual HTTP communication with AWC.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from backend.app.services.weather_client import AWCAPIError, AWCWeatherClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/weather", tags=["weather"])

# Injected by main.py on application startup
_weather_client: AWCWeatherClient | None = None


def set_weather_client(client: AWCWeatherClient) -> None:
    """Register the AWC weather client instance for this router.

    Called once during application lifespan startup.

    Args:
        client: The active AWCWeatherClient instance.
    """
    global _weather_client
    _weather_client = client


def _get_client() -> AWCWeatherClient:
    """Retrieve the weather client or raise 503 if not initialized.

    Returns:
        The active AWCWeatherClient.

    Raises:
        HTTPException: 503 if the client is not yet initialized.
    """
    if _weather_client is None:
        raise HTTPException(
            status_code=503,
            detail="Weather service not initialized",
        )
    return _weather_client


@router.get("/metar")
async def get_metar(ids: str = Query(..., description="Comma-separated ICAO codes")) -> list[dict]:
    """Proxy METAR request to AWC.

    Fetches current weather observations for specified airports.

    Args:
        ids: Comma-separated ICAO station codes (e.g. "KJFK,KLGA").

    Returns:
        List of METAR observation dicts from AWC.

    Raises:
        HTTPException: 400 on bad request, 502 on AWC upstream failure,
            503 if the weather service is not initialized.
    """
    client = _get_client()
    icao_list = [code.strip().upper() for code in ids.split(",") if code.strip()]
    if not icao_list:
        raise HTTPException(status_code=400, detail="At least one ICAO code is required")

    try:
        return await client.get_metar(icao_list)
    except AWCAPIError as exc:
        logger.warning("METAR request failed: %s", exc)
        status = exc.status_code if exc.status_code > 0 else 502
        raise HTTPException(status_code=status, detail=exc.detail) from exc


@router.get("/taf")
async def get_taf(ids: str = Query(..., description="Comma-separated ICAO codes")) -> list[dict]:
    """Proxy TAF request to AWC.

    Fetches terminal aerodrome forecasts for specified airports.

    Args:
        ids: Comma-separated ICAO station codes (e.g. "KJFK,KLGA").

    Returns:
        List of TAF forecast dicts from AWC.

    Raises:
        HTTPException: 400 on bad request, 502 on AWC upstream failure,
            503 if the weather service is not initialized.
    """
    client = _get_client()
    icao_list = [code.strip().upper() for code in ids.split(",") if code.strip()]
    if not icao_list:
        raise HTTPException(status_code=400, detail="At least one ICAO code is required")

    try:
        return await client.get_taf(icao_list)
    except AWCAPIError as exc:
        logger.warning("TAF request failed: %s", exc)
        status = exc.status_code if exc.status_code > 0 else 502
        raise HTTPException(status_code=status, detail=exc.detail) from exc


@router.get("/airsigmet")
async def get_airsigmet(
    hazard_type: str | None = Query(None, description="conv|turb|ice|ifr|mt"),
) -> list[dict]:
    """Proxy AIR/SIGMET request to AWC.

    Fetches active air meteorological warnings and advisories.

    Args:
        hazard_type: Optional filter — one of "conv", "turb", "ice",
            "ifr", "mt". Omit to retrieve all types.

    Returns:
        List of AIR/SIGMET dicts from AWC.

    Raises:
        HTTPException: 400 on bad request, 502 on AWC upstream failure,
            503 if the weather service is not initialized.
    """
    client = _get_client()
    valid_hazard_types = {"conv", "turb", "ice", "ifr", "mt"}
    if hazard_type is not None and hazard_type not in valid_hazard_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid hazard_type '{hazard_type}'. Must be one of: {', '.join(sorted(valid_hazard_types))}",
        )

    try:
        return await client.get_airsigmet(hazard_type=hazard_type)
    except AWCAPIError as exc:
        logger.warning("AIR/SIGMET request failed: %s", exc)
        status = exc.status_code if exc.status_code > 0 else 502
        raise HTTPException(status_code=status, detail=exc.detail) from exc


@router.get("/pirep")
async def get_pirep(
    radius: int = Query(100, description="Radius in NM"),
    lat: float = Query(40.6413, description="Center latitude"),
    lon: float = Query(-73.7781, description="Center longitude"),
) -> list[dict]:
    """Proxy PIREP request to AWC.

    Fetches pilot weather reports within a radius of a geographic point.
    Defaults to 100 NM around JFK airport.

    Args:
        radius: Search radius in nautical miles.
        lat: Center latitude in decimal degrees.
        lon: Center longitude in decimal degrees.

    Returns:
        List of PIREP dicts from AWC.

    Raises:
        HTTPException: 400 on bad request, 502 on AWC upstream failure,
            503 if the weather service is not initialized.
    """
    client = _get_client()
    if radius <= 0 or radius > 500:
        raise HTTPException(
            status_code=400,
            detail="Radius must be between 1 and 500 NM",
        )

    try:
        return await client.get_pirep(radius_nm=radius, lat=lat, lon=lon)
    except AWCAPIError as exc:
        logger.warning("PIREP request failed: %s", exc)
        status = exc.status_code if exc.status_code > 0 else 502
        raise HTTPException(status_code=status, detail=exc.detail) from exc
