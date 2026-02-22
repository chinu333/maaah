"""NASA Agent — queries NASA APIs via the **nasapy** package.

Supported features (auto-selected by keyword detection):
- APOD  (Astronomy Picture of the Day)
- Mars Rover Photos
- NEO   (Near Earth Objects / asteroids)
- NASA Image & Video Library search
- Earth imagery (Landsat)

Falls back to a media/image search when no specific keyword matches.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import nasapy
import requests
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.utils.token_counter import add_tokens
from app.utils.llm_cache import get_chat_llm

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# nasapy helper – all calls are synchronous so we run them in the agent
# ---------------------------------------------------------------------------

def _get_nasa_client() -> nasapy.Nasa:
    """Return a configured nasapy client."""
    settings = get_settings()
    return nasapy.Nasa(key=settings.nasa_api_key)


def _fetch_nasa_data(query: str) -> str:
    """Pick the right nasapy method based on keywords and return formatted text."""
    nasa = _get_nasa_client()
    q = query.lower()
    today = datetime.today().strftime("%Y-%m-%d")

    try:
        # ── APOD ────────────────────────────────────────────────
        if "apod" in q or "picture of the day" in q or "astronomy picture" in q:
            data = nasa.picture_of_the_day(today)
            if isinstance(data, dict):
                return (
                    f"**Astronomy Picture of the Day ({data.get('date', today)})**\n\n"
                    f"**Title:** {data.get('title', 'N/A')}\n\n"
                    f"**Explanation:** {data.get('explanation', 'N/A')}\n\n"
                    f"**Image URL:** {data.get('url', 'N/A')}\n\n"
                    f"**HD URL:** {data.get('hdurl', 'N/A')}"
                )
            return str(data)

        # ── Mars Rover Photos ───────────────────────────────────
        if "mars" in q or "rover" in q:
            rover = "curiosity"
            if "opportunity" in q:
                rover = "opportunity"
            elif "spirit" in q:
                rover = "spirit"
            elif "perseverance" in q:
                rover = "perseverance"

            photos = nasa.mars_rover(sol=1000, rover=rover)
            if isinstance(photos, list):
                photos = photos[:5]
                lines = [f"**Mars Rover Photos – {rover.title()}** (first 5):"]
                for p in photos:
                    cam = p.get("camera", {}).get("full_name", "Unknown")
                    lines.append(
                        f"- ID {p.get('id')} | Camera: {cam} | "
                        f"Earth Date: {p.get('earth_date')} | URL: {p.get('img_src')}"
                    )
                return "\n".join(lines) if photos else "No Mars rover photos found."
            return str(photos) if photos else "No Mars rover photos found for that sol."

        # ── Near Earth Objects ──────────────────────────────────
        if "neo" in q or "near earth" in q or "asteroid" in q:
            start = datetime.today().strftime("%Y-%m-%d")
            end = (datetime.today() + timedelta(days=3)).strftime("%Y-%m-%d")
            data = nasa.asteroids(start_date=start, end_date=end)
            neos = []
            if isinstance(data, dict):
                for date_key, objs in data.get("near_earth_objects", {}).items():
                    neos.extend(objs)
            neos = neos[:5]
            if neos:
                lines = ["**Near Earth Objects** (next 3 days, first 5):"]
                for n in neos:
                    lines.append(
                        f"- {n.get('name', '?')} | Magnitude: {n.get('absolute_magnitude_h', 'N/A')} | "
                        f"Hazardous: {n.get('is_potentially_hazardous_asteroid', 'N/A')}"
                    )
                return "\n".join(lines)
            return "No NEO data available for the next 3 days."

        # ── Earth Imagery (Landsat) ─────────────────────────────
        if "earth" in q and ("image" in q or "landsat" in q or "satellite" in q):
            # Default to Atlanta coordinates
            data = nasa.earth_imagery(lat=33.749, lon=-84.388, date=today)
            if isinstance(data, dict) and data.get("url"):
                return (
                    f"**Earth Imagery (Landsat)**\n\n"
                    f"Date: {data.get('date', today)}\n"
                    f"URL: {data.get('url')}"
                )
            return "No Earth imagery available for the requested location/date."

        # ── Fallback: NASA Image & Video Library search ─────────
        resp = requests.get(
            "https://images-api.nasa.gov/search",
            params={"q": query, "media_type": "image"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json().get("collection", {})
        items = data.get("items", [])[:5]

        if items:
            lines = [f'**NASA Image Search** for "{query}" (top 5):']
            for item in items:
                d = (item.get("data") or [{}])[0]
                link = ((item.get("links") or [{}])[0]).get("href", "N/A")
                lines.append(f"- {d.get('title', 'Untitled')} | {link}")
            return "\n".join(lines)
        return f"No NASA results found for '{query}'."

    except Exception as exc:
        logger.error("NASA Agent error (nasapy): %s", exc)
        return f"Error querying NASA API: {exc}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def invoke(query: str, *, file_path: Optional[str] = None, **kwargs) -> str:
    """Fetch NASA data via nasapy and let the LLM compose a user-friendly answer."""

    nasa_data = _fetch_nasa_data(query)

    llm = get_chat_llm(temperature=0.4, name="nasa-agent-llm")

    messages = [
        SystemMessage(
            content=(
                "You are the NASA Agent inside the Ensō multi-agent system. "
                "Use the NASA data provided below to give the user a helpful, "
                "well-structured answer. Include relevant links and details. "
                "If the data is an error message, explain what happened."
            )
        ),
        HumanMessage(
            content=f"User query: {query}\n\n--- NASA DATA ---\n{nasa_data}"
        ),
    ]

    response = await llm.ainvoke(messages)
    add_tokens(response)
    return response.content
