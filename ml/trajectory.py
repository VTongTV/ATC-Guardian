"""Trajectory extrapolation for aircraft state vectors.

Projects an aircraft's future position based on its current state
(heading, speed, vertical rate). All calculations use great-circle
math on a spherical Earth model.
"""

import math

from shared.constants import EARTH_RADIUS_NM
from shared.models import AircraftState, PositionGeographic


def extrapolate_position(
    aircraft: AircraftState,
    delta_seconds: float,
) -> PositionGeographic:
    """Project an aircraft's position forward in time.

    Uses a constant-velocity, constant-heading model (no wind,
    no turn). Suitable for short-term look-ahead (≤5 min).

    Args:
        aircraft: Current aircraft state vector.
        delta_seconds: Number of seconds to project forward.

    Returns:
        Projected geographic position with extrapolated altitude.
    """
    distance_nm = _distance_traveled_nm(aircraft.speed_kts, delta_seconds)
    new_latitude = _extrapolate_latitude(
        aircraft.latitude, aircraft.longitude, aircraft.heading_deg, distance_nm
    )
    new_longitude = _extrapolate_longitude(
        aircraft.latitude, aircraft.longitude, aircraft.heading_deg, distance_nm
    )
    new_altitude_ft = _extrapolate_altitude(
        aircraft.altitude_ft, aircraft.vertical_speed_fpm, delta_seconds
    )

    return PositionGeographic(
        latitude=new_latitude,
        longitude=new_longitude,
        altitude_ft=max(0, new_altitude_ft),
    )


def _distance_traveled_nm(speed_kts: float, delta_seconds: float) -> float:
    """Compute distance traveled in nautical miles.

    Args:
        speed_kts: Ground speed in knots (nautical miles per hour).
        delta_seconds: Time delta in seconds.

    Returns:
        Distance traveled in nautical miles.
    """
    hours = delta_seconds / 3600.0
    return speed_kts * hours


def _extrapolate_latitude(
    origin_lat: float,
    origin_lon: float,
    heading_deg: float,
    distance_nm: float,
) -> float:
    """Compute destination latitude using great-circle formula.

    Args:
        origin_lat: Origin latitude in decimal degrees.
        origin_lon: Origin longitude in decimal degrees (unused but kept for API symmetry).
        heading_deg: True heading in degrees.
        distance_nm: Distance traveled in nautical miles.

    Returns:
        Destination latitude in decimal degrees, clamped to [-90, 90].
    """
    lat1_rad = math.radians(origin_lat)
    heading_rad = math.radians(heading_deg)
    angular_distance = distance_nm / EARTH_RADIUS_NM

    lat2_rad = math.asin(
        math.sin(lat1_rad) * math.cos(angular_distance)
        + math.cos(lat1_rad) * math.sin(angular_distance) * math.cos(heading_rad)
    )

    return math.degrees(lat2_rad)


def _extrapolate_longitude(
    origin_lat: float,
    origin_lon: float,
    heading_deg: float,
    distance_nm: float,
) -> float:
    """Compute destination longitude using great-circle formula.

    Args:
        origin_lat: Origin latitude in decimal degrees.
        origin_lon: Origin longitude in decimal degrees.
        heading_deg: True heading in degrees.
        distance_nm: Distance traveled in nautical miles.

    Returns:
        Destination longitude in decimal degrees, normalized to [-180, 180].
    """
    lat1_rad = math.radians(origin_lat)
    lon1_rad = math.radians(origin_lon)
    heading_rad = math.radians(heading_deg)
    angular_distance = distance_nm / EARTH_RADIUS_NM

    sin_lat1 = math.sin(lat1_rad)
    cos_lat1 = math.cos(lat1_rad)
    cos_angular = math.cos(angular_distance)

    lat2_rad = math.asin(
        sin_lat1 * cos_angular
        + cos_lat1 * math.sin(angular_distance) * math.cos(heading_rad)
    )

    cos_lat2 = math.cos(lat2_rad)
    if abs(cos_lat2) < 1e-10:
        return origin_lon

    lon_delta = math.atan2(
        math.sin(heading_rad) * math.sin(angular_distance) * cos_lat1,
        cos_angular - sin_lat1 * math.sin(lat2_rad),
    )

    lon2_rad = lon1_rad + lon_delta
    lon2_deg = math.degrees(lon2_rad)

    return _normalize_longitude(lon2_deg)


def _extrapolate_altitude(
    altitude_ft: int,
    vertical_speed_fpm: int,
    delta_seconds: float,
) -> int:
    """Project altitude forward based on vertical speed.

    Args:
        altitude_ft: Current pressure altitude in feet.
        vertical_speed_fpm: Vertical speed in feet per minute (+ climb, - descend).
        delta_seconds: Time delta in seconds.

    Returns:
        Projected altitude in feet. Floor at 0 (ground).
    """
    delta_minutes = delta_seconds / 60.0
    altitude_change = vertical_speed_fpm * delta_minutes
    return int(altitude_ft + altitude_change)


def _normalize_longitude(lon_deg: float) -> float:
    """Normalize longitude to the range [-180, 180).

    Args:
        lon_deg: Longitude in decimal degrees (any range).

    Returns:
        Normalized longitude in [-180, 180).
    """
    while lon_deg >= 180.0:
        lon_deg -= 360.0
    while lon_deg < -180.0:
        lon_deg += 360.0
    return lon_deg


def compute_bearing(from_lat: float, from_lon: float, to_lat: float, to_lon: float) -> float:
    """Compute initial bearing from one position to another.

    Uses the forward azimuth formula on a great-circle.

    Args:
        from_lat: Origin latitude in decimal degrees.
        from_lon: Origin longitude in decimal degrees.
        to_lat: Destination latitude in decimal degrees.
        to_lon: Destination longitude in decimal degrees.

    Returns:
        Initial bearing in degrees [0, 360).
    """
    lat1_rad = math.radians(from_lat)
    lat2_rad = math.radians(to_lat)
    delta_lon_rad = math.radians(to_lon - from_lon)

    x = math.sin(delta_lon_rad) * math.cos(lat2_rad)
    y = math.cos(lat1_rad) * math.sin(lat2_rad) - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(
        delta_lon_rad
    )

    bearing_rad = math.atan2(x, y)
    bearing_deg = math.degrees(bearing_rad)

    return bearing_deg % 360.0


def haversine_distance_nm(
    lat1: float, lon1: float, lat2: float, lon2: float
) -> float:
    """Compute great-circle distance between two points using the haversine formula.

    Args:
        lat1: First point latitude in decimal degrees.
        lon1: First point longitude in decimal degrees.
        lat2: Second point latitude in decimal degrees.
        lon2: Second point longitude in decimal degrees.

    Returns:
        Distance in nautical miles.
    """
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return EARTH_RADIUS_NM * c
