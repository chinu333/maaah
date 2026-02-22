"""Weather Agent — provides current weather for a location using Azure Maps.

Uses the Azure Maps Weather REST API with a subscription key and client ID.
Location geocoding is handled via the Azure Maps Search Address API.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional

import requests
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.utils.token_counter import add_tokens
from app.utils.llm_cache import get_chat_llm

logger = logging.getLogger(__name__)

# Azure Maps credentials
_azure_maps_sub_key = os.getenv("AZURE_MAPS_SUBSCRIPTION_KEY", "")
_azure_maps_client_id = os.getenv("AZURE_MAPS_CLIENT_ID", "")


def _geocode_azure_maps(location_name: str) -> tuple[float, float] | None:
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


def _get_weather_from_azure_maps(location_name: str) -> dict | str:
    """Geocode *location_name* then fetch current weather from Azure Maps."""
    try:
        coords = _geocode_azure_maps(location_name)
        if coords is None:
            return f"Could not geocode location: {location_name}"

        lat, lon = coords
        latlon = f"{lat},{lon}"

        url = (
            "https://atlas.microsoft.com/weather/currentConditions/json"
            f"?api-version=1.0&query={latlon}"
            f"&subscription-key={_azure_maps_sub_key}"
        )
        headers = {
            "Content-Type": "application/json",
            "x-ms-client-id": _azure_maps_client_id,
        }

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as exc:
        logger.exception("Azure Maps weather request failed")
        return f"Weather API error: {exc}"
    except Exception as exc:
        logger.exception("Weather fetch failed")
        return f"Error fetching weather: {exc}"


def _format_weather(data: dict, location_name: str) -> str:
    """Turn Azure Maps weather JSON into a readable Markdown string."""
    results = data.get("results", [])
    if not results:
        return f"No weather data returned for **{location_name}**."

    w = results[0]
    phrase = w.get("phrase", "N/A")
    temp = w.get("temperature", {})
    temp_val = temp.get("value", "N/A")
    temp_unit = temp.get("unit", "")
    feels = w.get("realFeelTemperature", {})
    feels_val = feels.get("value", "N/A")
    feels_unit = feels.get("unit", "")
    humidity = w.get("relativeHumidity", "N/A")
    wind = w.get("wind", {})
    wind_speed = wind.get("speed", {}).get("value", "N/A")
    wind_unit = wind.get("speed", {}).get("unit", "")
    wind_dir = wind.get("direction", {}).get("localizedDescription", "N/A")
    visibility = w.get("visibility", {}).get("value", "N/A")
    vis_unit = w.get("visibility", {}).get("unit", "")
    uv_index = w.get("uvIndex", "N/A")
    uv_text = w.get("uvIndexPhrase", "")
    cloud_cover = w.get("cloudCover", "N/A")
    date_time = w.get("dateTime", "")

    return (
        f"## ☀️ Current Weather — {location_name}\n\n"
        f"**Condition:** {phrase}\n\n"
        f"| Metric | Value |\n"
        f"|--------|-------|\n"
        f"| Temperature | {temp_val}° {temp_unit} |\n"
        f"| Feels Like | {feels_val}° {feels_unit} |\n"
        f"| Humidity | {humidity}% |\n"
        f"| Wind | {wind_speed} {wind_unit} {wind_dir} |\n"
        f"| Visibility | {visibility} {vis_unit} |\n"
        f"| UV Index | {uv_index} ({uv_text}) |\n"
        f"| Cloud Cover | {cloud_cover}% |\n\n"
        f"*Observed: {date_time}*"
    )


def _extract_location(query: str) -> str:
    """Try to extract a location name from the query string."""
    q = query.lower()
    # Remove common weather prefixes
    for prefix in [
        "weather in ", "weather for ", "weather at ",
        "what is the weather in ", "what's the weather in ",
        "how is the weather in ", "how's the weather in ",
        "get weather for ", "get weather in ",
        "current weather in ", "current weather for ",
        "temperature in ", "temperature at ",
        "weather ",
    ]:
        if q.startswith(prefix):
            return query[len(prefix):].strip().rstrip("?.,!")
    # fallback: return full query (LLM will handle)
    return query.strip().rstrip("?.,!")


async def _llm_extract_location(query: str) -> str:
    """Use the LLM to extract the weather location from a complex query."""
    llm = get_chat_llm(temperature=0.0, request_timeout=30, name="weather-location-extractor")

    messages = [
        SystemMessage(
            content=(
                "Extract the single city/location the user wants weather for. "
                "Return ONLY a JSON object: {\"location\": \"<city, state/country>\"}. "
                "If multiple locations are mentioned, pick the one most relevant to the weather question. "
                "No explanation, no markdown, just the JSON object."
            )
        ),
        HumanMessage(content=query),
    ]
    resp = await llm.ainvoke(messages)
    add_tokens(resp)
    text = resp.content.strip()
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        data = json.loads(text)
        return data.get("location", "").strip()
    except json.JSONDecodeError:
        return text.strip('"\' ')


async def invoke(query: str, *, file_path: Optional[str] = None, **kwargs) -> str:
    """Fetch weather for the location mentioned in the query."""
    settings = get_settings()

    # Try simple extraction first; if it returns the whole query, use LLM
    location_name = _extract_location(query)
    if len(location_name) > 80 or location_name.lower() == query.lower().strip().rstrip("?.,!"):
        location_name = await _llm_extract_location(query)

    if not location_name:
        return "I couldn't determine which location you want weather for. Please specify a city or place."

    weather_data = _get_weather_from_azure_maps(location_name)

    if isinstance(weather_data, str):
        # It's an error message
        return weather_data

    formatted = _format_weather(weather_data, location_name)

    # Use LLM to provide a conversational summary alongside the data
    llm = get_chat_llm(temperature=0.7, name="weather-agent-llm")

    messages = [
        SystemMessage(
            content=(
                "You are the Weather Agent inside Ensō (Multi Agent AI Hub). "
                "The user asked about the weather. Below is the raw weather data retrieved "
                "from Azure Maps. Present it clearly in Markdown, add a brief natural-language "
                "summary at the top (e.g. 'It's a warm sunny day…'), and keep the detailed "
                "table. If it looks like severe weather, warn the user."
            )
        ),
        HumanMessage(
            content=f"User query: {query}\n\nWeather data:\n\n{formatted}"
        ),
    ]

    response = await llm.ainvoke(messages)
    add_tokens(response)
    return response.content
