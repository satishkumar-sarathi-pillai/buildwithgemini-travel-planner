# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import uuid
from pathlib import Path
from zoneinfo import ZoneInfo

import google.auth
from google.auth.transport.requests import Request
import httpx
from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from dotenv import load_dotenv
from google import genai
from google.cloud import firestore, storage

from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.genai import types

from app.a2ui_utils import a2ui_callback

load_dotenv()

FIRESTORE_PROJECT_ID = "qwiklabs-gcp-02-64351d593793"
STORAGE_BUCKET_NAME = "travel-planner-media-64351d59"

db = firestore.Client(project=FIRESTORE_PROJECT_ID)
storage_client = storage.Client(project=FIRESTORE_PROJECT_ID)
genai_client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="us-central1")
global_genai_client = genai.Client(vertexai=True, project=FIRESTORE_PROJECT_ID, location="global")

# Read agent engine resource name from deployment_metadata.json if available
deployment_metadata_path = Path(__file__).parent.parent / "deployment_metadata.json"
agent_engine_resource_name = None
memory_bank_id = "156378041260441600"

if deployment_metadata_path.exists():
    try:
        meta = json.loads(deployment_metadata_path.read_text())
        agent_engine_resource_name = meta.get("remote_agent_runtime_id")
        if agent_engine_resource_name:
            memory_bank_id = agent_engine_resource_name.split("/")[-1]
    except Exception:
        agent_engine_resource_name = None

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=agent_engine_resource_name
)


def memory_bank_service_builder():
    return VertexAiMemoryBankService(
        project=FIRESTORE_PROJECT_ID,
        location="us-east1",
        agent_engine_id=memory_bank_id,
    )


async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None


async def generate_destination_image(prompt: str, tool_context: ToolContext) -> str:
    """Generate an image illustration for a travel destination item using gemini-3.1-flash-lite-image in global region,
    saving it as an artifact in Playground and uploading it to public Cloud Storage.

    Args:
        prompt: Description of the destination item or landmark to generate an image for (e.g. 'Eiffel Tower at night').
        tool_context: ADK ToolContext instance injected automatically by the runtime.

    Returns:
        The public HTTPS URL of the image uploaded to Cloud Storage (https://storage.googleapis.com/<bucket>/<object>).
    """
    full_prompt = f"A vibrant, artistic travel illustration of {prompt}"
    response = global_genai_client.models.generate_content(
        model="gemini-3.1-flash-lite-image",
        contents=full_prompt,
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            image_bytes = part.inline_data.data
            mime_type = part.inline_data.mime_type or "image/jpeg"
            ext = "jpg" if "jpeg" in mime_type or "jpg" in mime_type else "png"
            filename = f"illustrations/{uuid.uuid4().hex[:8]}.{ext}"

            # 1. Save with tool_context.save_artifact for Playground's Artifacts panel
            artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
            await tool_context.save_artifact(filename=filename, artifact=artifact_part)

            # 2. Upload image bytes to hardcoded public Cloud Storage bucket
            bucket = storage_client.bucket("travel-planner-media-64351d59")
            blob = bucket.blob(filename)
            blob.upload_from_string(image_bytes, content_type=mime_type)

            public_url = f"https://storage.googleapis.com/travel-planner-media-64351d59/{filename}"
            return public_url

    return "Failed to generate image."


async def generate_destination_video(prompt: str, tool_context: ToolContext) -> str:
    """Generate a short video clip for a travel destination or landmark item using Google's gemini-omni-flash-preview model in the global region,
    saving it as an artifact in Playground and uploading it to public Cloud Storage.

    Args:
        prompt: Description of the destination scene or landmark to generate a video for (e.g. 'Cherry blossoms swaying in Tokyo breeze').
        tool_context: ADK ToolContext instance injected automatically by the runtime.

    Returns:
        The public HTTPS URL of the video uploaded to Cloud Storage (https://storage.googleapis.com/<bucket>/<object>).
    """
    credentials, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    credentials.refresh(Request())
    token = credentials.token

    url = "https://aiplatform.googleapis.com/v1beta1/projects/qwiklabs-gcp-02-64351d593793/locations/global/interactions"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "model": "gemini-omni-flash-preview",
        "input": f"A vibrant short video clip of {prompt}",
        "response_format": [{"type": "video"}],
    }

    async with httpx.AsyncClient(timeout=300.0) as client:
        res = await client.post(url, headers=headers, json=body)
        res.raise_for_status()
        data = res.json()

    video_bytes = None
    mime_type = "video/mp4"

    if "steps" in data:
        for step in data["steps"]:
            if step.get("type") == "model_output":
                for content in step.get("content", []):
                    if content.get("type") == "video":
                        if content.get("data"):
                            video_bytes = base64.b64decode(content["data"])
                            mime_type = content.get("mime_type") or "video/mp4"
                            break

    if not video_bytes:
        return "Failed to generate video."

    filename = f"videos/{uuid.uuid4().hex[:8]}.mp4"

    # 1. Save with tool_context.save_artifact so it shows up in Playground's Artifacts panel
    artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
    await tool_context.save_artifact(filename=filename, artifact=artifact_part)

    # 2. Upload video bytes directly to hardcoded public Cloud Storage bucket
    bucket = storage_client.bucket("travel-planner-media-64351d59")
    blob = bucket.blob(filename)
    blob.upload_from_string(video_bytes, content_type=mime_type)

    public_url = f"https://storage.googleapis.com/travel-planner-media-64351d59/{filename}"
    return public_url


def geocode_address(address: str) -> dict:
    """Turn an address or landmark name into geographic coordinates (latitude & longitude) using Google Geocoding API.

    Args:
        address: The address, place name, or landmark to geocode (e.g. 'Eiffel Tower, Paris' or 'Kyoto Station').

    Returns:
        A dictionary with 'name', 'formatted_address', and 'location' ({'lat': ..., 'lng': ...}).
    """
    key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not key:
        return {"error": "GOOGLE_MAPS_API_KEY environment variable not set."}

    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={key}"
    try:
        response = httpx.get(url, timeout=10.0).json()
        if response.get("status") == "OK" and response.get("results"):
            first = response["results"][0]
            return {
                "name": address,
                "formatted_address": first.get("formatted_address", ""),
                "location": first.get("geometry", {}).get("location", {}),
            }
        return {"error": f"Geocoding failed with status: {response.get('status')}"}
    except Exception as e:
        return {"error": f"Geocoding request failed: {str(e)}"}


def search_nearby_places(
    latitude: float,
    longitude: float,
    place_type: str = "tourist_attraction",
    radius_meters: float = 1000.0,
) -> list[dict]:
    """Find nearby places of a given type near geographic coordinates using Google Places API (New).

    Args:
        latitude: Latitude of the center point.
        longitude: Longitude of the center point.
        place_type: Type of place to search for (e.g. 'restaurant', 'tourist_attraction', 'cafe', 'museum').
        radius_meters: Search radius in meters (default: 1000.0).

    Returns:
        A list of place dictionaries with 'name', 'address', and 'location'.
    """
    key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not key:
        return [{"error": "GOOGLE_MAPS_API_KEY environment variable not set."}]

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "X-Goog-Api-Key": key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location",
        "Content-Type": "application/json",
    }
    body = {
        "includedTypes": [place_type],
        "locationRestriction": {
            "circle": {
                "center": {"latitude": latitude, "longitude": longitude},
                "radius": radius_meters,
            }
        },
    }
    try:
        response = httpx.post(url, headers=headers, json=body, timeout=10.0).json()
        places = response.get("places", [])
        results = []
        for p in places:
            results.append(
                {
                    "name": p.get("displayName", {}).get("text", ""),
                    "address": p.get("formattedAddress", ""),
                    "location": p.get("location", {}),
                }
            )
        return results
    except Exception as e:
        return [{"error": f"Places search failed: {str(e)}"}]


def get_currency_exchange_rates(base_currency: str = "USD", target_currencies: str = "JPY,EUR,GBP") -> dict:
    """Get live currency exchange rates from the Frankfurter open API for travel budget planning.

    Args:
        base_currency: The 3-letter base currency code (e.g. 'USD', 'EUR').
        target_currencies: Comma-separated 3-letter target currency codes (e.g. 'JPY,EUR,GBP').

    Returns:
        A dictionary containing exchange rates, base currency, and date.
    """
    try:
        api_key = os.getenv("EXCHANGE_RATE_API_KEY", "")
        url = "https://api.frankfurter.dev/v1/latest"
        params = {"base": base_currency.upper(), "symbols": target_currencies.upper()}
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        response = httpx.get(url, params=params, headers=headers, timeout=10.0)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": f"Failed to fetch live exchange rates: {str(e)}"}


def generate_destination_illustration(prompt: str) -> str:
    """Generate a custom AI travel illustration for a destination or landmark and upload it to Cloud Storage.

    Args:
        prompt: Description of the destination or landmark to illustrate (e.g., 'Golden Pavilion in Kyoto at sunset').

    Returns:
        The public HTTP URL of the generated illustration image.
    """
    full_prompt = f"A vibrant, artistic travel illustration of {prompt}"
    response = genai_client.models.generate_content(
        model="gemini-2.5-flash-image",
        contents=full_prompt,
    )
    for part in response.candidates[0].content.parts:
        if part.inline_data:
            image_bytes = part.inline_data.data
            mime_type = part.inline_data.mime_type or "image/png"
            ext = "png" if "png" in mime_type else "jpg"
            filename = f"illustrations/{uuid.uuid4().hex[:8]}.{ext}"

            bucket = storage_client.bucket(STORAGE_BUCKET_NAME)
            blob = bucket.blob(filename)
            blob.upload_from_string(image_bytes, content_type=mime_type)

            public_url = f"https://storage.googleapis.com/{STORAGE_BUCKET_NAME}/{filename}"
            return f"Generated travel illustration for '{prompt}': {public_url}"

    return "Failed to generate image illustration."


def search_destinations(country: str = "", category: str = "", max_budget_usd: int = 0) -> list[dict]:
    """Search for travel destinations in the Firestore database.

    Args:
        country: Optional filter by country name (e.g., 'Japan', 'France').
        category: Optional filter by category (e.g., 'Culture & Food', 'Art & Culinary').
        max_budget_usd: Optional maximum average daily budget in USD.

    Returns:
        A list of destination dictionaries matching the query filters.
    """
    collection_ref = db.collection("destinations")
    docs = collection_ref.stream()
    results = []
    for doc in docs:
        data = doc.to_dict()
        if country and country.lower() not in data.get("country", "").lower():
            continue
        if category and category.lower() not in data.get("category", "").lower():
            continue
        if max_budget_usd > 0 and data.get("average_daily_budget_usd", 0) > max_budget_usd:
            continue
        results.append(data)
    return results


def get_destination_details(destination_id: str) -> dict:
    """Get complete details for a specific travel destination by ID from Firestore.

    Args:
        destination_id: Unique destination ID (e.g., 'tokyo-japan', 'paris-france').

    Returns:
        A dictionary containing destination details or an error dictionary if not found.
    """
    doc_ref = db.collection("destinations").document(destination_id)
    doc = doc_ref.get()
    if doc.exists:
        return doc.to_dict()
    return {"error": f"Destination '{destination_id}' not found."}


def add_destination(
    destination_id: str,
    name: str,
    country: str,
    category: str,
    best_time_to_visit: str,
    average_daily_budget_usd: int,
    highlights: list[str],
    description: str,
) -> str:
    """Add a new destination to the Firestore travel database.

    Args:
        destination_id: Unique slug ID for the destination (e.g. 'sydney-australia').
        name: Name of the destination city or region.
        country: Country where the destination is located.
        category: Travel category (e.g. 'Nature & Beach', 'Food & History').
        best_time_to_visit: Best months/seasons to visit.
        average_daily_budget_usd: Estimated average daily cost per person in USD.
        highlights: Key attractions or highlights as a list of strings.
        description: Brief overview description of the destination.

    Returns:
        Confirmation message string.
    """
    data = {
        "id": destination_id,
        "name": name,
        "country": country,
        "category": category,
        "best_time_to_visit": best_time_to_visit,
        "average_daily_budget_usd": average_daily_budget_usd,
        "highlights": highlights,
        "description": description,
    }
    db.collection("destinations").document(destination_id).set(data)
    return f"Successfully added destination '{name}' ({destination_id}) to Firestore."


def get_weather(query: str) -> str:
    """Simulates a web search for weather information.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the weather information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are an expert AI Travel Planner & Itinerary Illustrator. "
        "You remember user preferences across sessions using Memory Bank."
    ),
    workflow_description=(
        "Analyze the user request, query Firestore destinations, geocode locations, search nearby places, "
        "get live currency exchange rates, execute custom python scripts via code execution sandbox, "
        "generate travel illustrations, and return structured A2UI cards or text when appropriate."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    code_executor=code_executor,
    instruction=instruction,
    tools=[
        PreloadMemoryTool(),
        search_destinations,
        get_destination_details,
        add_destination,
        geocode_address,
        search_nearby_places,
        get_currency_exchange_rates,
        generate_destination_image,
        generate_destination_illustration,
        generate_destination_video,
        get_weather,
    ],
    after_model_callback=a2ui_callback,
    after_agent_callback=generate_memories_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
