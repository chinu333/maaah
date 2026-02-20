"""Traffic Agent — provides route & traffic info using the TomTom Routing API.

Calculates routes between two locations with real-time traffic data,
travel time, distance, and delay information.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional
from urllib import parse as urlparse

import requests
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain_openai import AzureChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.utils.token_counter import add_tokens

logger = logging.getLogger(__name__)

_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _credential, "https://cognitiveservices.azure.com/.default"
)

_tomtom_api_key = os.getenv("TOMTOM_MAPS_API_KEY", "")
_azure_maps_sub_key = os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY", "")
_azure_maps_client_id = os.getenv("AZURE_MAPS_CLIENT_ID", "")


def _geocode(location_name: str) -> tuple[float, float] | None:
    """Geocode a location name using Azure Maps Search Address API."""
    url = (
        "https://atlas.microsoft.com/search/address/json"
        f"?api-version=1.0&query={requests.utils.quote(location_name)}"
        f"&subscription-key={_azure_maps_sub_key}"
    )
    headers = {"x-ms-client-id": _azure_maps_client_id}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("results", [])
        if not results:
            return None
        pos = results[0].get("position", {})
        return pos.get("lat"), pos.get("lon")
    except Exception as exc:
        logger.exception("Azure Maps geocode failed for %s", location_name)
        return None


def _get_traffic_route(
    start: str,
    end: str,
    route_type: str = "fastest",
    traffic: str = "true",
    travel_mode: str = "car",
    avoid: str = "unpavedRoads",
    vehicle_commercial: str = "false",
    depart_at: str = "now",
) -> dict | str:
    """Call the TomTom Routing API and return the JSON response."""

    start_geo = _geocode(start)
    end_geo = _geocode(end)

    if start_geo is None:
        return f"Could not geocode origin: {start}"
    if end_geo is None:
        return f"Could not geocode destination: {end}"

    start_latlon = f"{start_geo[0]},{start_geo[1]}"
    end_latlon = f"{end_geo[0]},{end_geo[1]}"

    base_url = "https://api.tomtom.com/routing/1/calculateRoute/"
    request_params = (
        urlparse.quote(start_latlon) + ":" + urlparse.quote(end_latlon)
        + "/json?routeType=" + route_type
        + "&traffic=" + traffic
        + "&travelMode=" + travel_mode
        + "&avoid=" + avoid
        + "&vehicleCommercial=" + vehicle_commercial
        + "&departAt=" + urlparse.quote(depart_at)
    )
    request_url = base_url + request_params + "&key=" + _tomtom_api_key

    try:
        response = requests.get(request_url, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        logger.exception("TomTom routing request failed")
        return f"Traffic API error: {exc}"


def _format_traffic(data: dict, origin: str, destination: str) -> str:
    """Turn TomTom routing JSON into readable Markdown."""
    routes = data.get("routes", [])
    if not routes:
        return f"No route found from **{origin}** to **{destination}**."

    route = routes[0]
    summary = route.get("summary", {})

    length_m = summary.get("lengthInMeters", 0)
    length_km = length_m / 1000
    length_mi = length_km * 0.621371

    travel_time_s = summary.get("travelTimeInSeconds", 0)
    travel_mins = travel_time_s // 60
    travel_hrs = travel_mins // 60
    travel_rem_mins = travel_mins % 60

    live_time_s = summary.get("trafficDelayInSeconds", 0)
    delay_mins = live_time_s // 60

    no_traffic_time_s = summary.get("noTrafficTravelTimeInSeconds", 0)
    no_traffic_mins = no_traffic_time_s // 60

    historic_time_s = summary.get("historicTrafficTravelTimeInSeconds", 0)
    historic_mins = historic_time_s // 60

    live_traffic_s = summary.get("liveTrafficIncidentsTravelTimeInSeconds", 0)
    live_traffic_mins = live_traffic_s // 60

    depart = summary.get("departureTime", "N/A")
    arrive = summary.get("arrivalTime", "N/A")

    time_display = (
        f"{travel_hrs}h {travel_rem_mins}m" if travel_hrs > 0
        else f"{travel_mins}m"
    )

    return (
        f"## 🚗 Traffic Route — {origin} → {destination}\n\n"
        f"**Estimated Travel Time:** {time_display}\n\n"
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Distance | {length_km:.1f} km ({length_mi:.1f} mi) |\n"
        f"| Travel Time (with traffic) | {travel_mins} min |\n"
        f"| Travel Time (no traffic) | {no_traffic_mins} min |\n"
        f"| Historic Avg Travel Time | {historic_mins} min |\n"
        f"| Live Traffic Incidents Time | {live_traffic_mins} min |\n"
        f"| Traffic Delay | {delay_mins} min |\n"
        f"| Departure | {depart} |\n"
        f"| Arrival | {arrive} |\n"
    )


def _extract_locations(query: str) -> tuple[str, str]:
    """Extract origin and destination from the query using simple patterns."""
    q = query.lower()

    for prefix in [
        "traffic from ", "route from ", "directions from ",
        "driving from ", "drive from ", "commute from ",
        "how long from ", "travel from ", "distance from ",
        "get traffic from ", "get route from ",
        "get directions from ",
    ]:
        if q.startswith(prefix):
            remainder = query[len(prefix):].strip().rstrip("?.,!")
            if " to " in remainder.lower():
                parts = remainder.lower().split(" to ", 1)
                return parts[0].strip(), parts[1].strip()

    if " to " in q:
        from_idx = q.find("from ")
        if from_idx != -1:
            remainder = q[from_idx + 5:]
            if " to " in remainder:
                parts = remainder.split(" to ", 1)
                origin = parts[0].strip().rstrip("?.,!")
                dest = parts[1].strip().rstrip("?.,!")
                return origin, dest

        parts = q.split(" to ", 1)
        origin = parts[0].strip()
        for kw in ["traffic ", "route ", "directions ", "driving ", "commute ", "distance "]:
            if origin.startswith(kw):
                origin = origin[len(kw):]
        dest = parts[1].strip().rstrip("?.,!")
        return origin.strip(), dest

    return query.strip(), ""


async def _llm_extract_locations(query: str) -> tuple[str, str]:
    """Use the LLM to extract origin and destination from a complex query."""
    settings = get_settings()
    llm = AzureChatOpenAI(
        azure_deployment=settings.azure_openai_chat_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=_token_provider,
        temperature=0,
        request_timeout=30,
    )
    llm.name = "traffic-location-extractor"

    messages = [
        SystemMessage(
            content=(
                "Extract the travel origin and destination from the user's message. "
                "Return ONLY a JSON object: {\"origin\": \"<place>\", \"destination\": \"<place>\"}. "
                "If the destination is not explicitly stated but implied (e.g. \"dinner in Atlanta\" "
                "implies Atlanta is the destination), infer it. "
                "No explanation, no markdown, just the JSON object."
            )
        ),
        HumanMessage(content=query),
    ]
    resp = await llm.ainvoke(messages)
    add_tokens(resp)
    text = resp.content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
        return data.get("origin", "").strip(), data.get("destination", "").strip()
    except json.JSONDecodeError:
        return "", ""


async def invoke(query: str, *, file_path: Optional[str] = None, **kwargs) -> str:
    """Get traffic / route info between locations mentioned in the query."""
    settings = get_settings()

    origin, destination = _extract_locations(query)

    # If simple extraction failed or returned the whole query, use LLM
    if not destination or len(origin) > 80:
        origin, destination = await _llm_extract_locations(query)

    if not origin or not destination:
        return (
            "I need both an **origin** and a **destination** to look up traffic. "
            "Try something like: *traffic from Atlanta to Charlotte*"
        )

    traffic_data = _get_traffic_route(origin, destination)

    if isinstance(traffic_data, str):
        return traffic_data

    formatted = _format_traffic(traffic_data, origin, destination)

    # Use LLM to provide a conversational summary
    llm = AzureChatOpenAI(
        azure_deployment=settings.azure_openai_chat_deployment,
        azure_endpoint=settings.azure_openai_endpoint,
        api_version=settings.azure_openai_api_version,
        azure_ad_token_provider=_token_provider,
        temperature=0.7,
        request_timeout=settings.request_timeout,
    )
    llm.name = "traffic-agent-llm"

    messages = [
        SystemMessage(
            content=(
                "You are the Traffic Agent inside Ensō (Multi Agent AI Hub). "
                "The user asked about traffic or directions. Below is the route data "
                "retrieved from TomTom. Present it clearly in Markdown with a brief "
                "natural-language summary (e.g. 'Expect moderate delays…'), keep the "
                "detailed table, and add any helpful driving tips if relevant."
            )
        ),
        HumanMessage(
            content=f"User query: {query}\n\nRoute data:\n\n{formatted}"
        ),
    ]

    response = await llm.ainvoke(messages)
    add_tokens(response)
    return response.content
