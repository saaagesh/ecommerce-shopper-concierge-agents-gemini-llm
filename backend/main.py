import os
import logging
import asyncio
import requests
import json
import re
from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import StreamingResponse

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from shared_tools import find_shopping_items, research_agent_tool
from google.genai import types as genai_types
import google.generativeai as genai
from dotenv import load_dotenv

from config import config

# --- Setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
load_dotenv()

# Use the API key from the environment
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    logger.info("Text Server: Successfully configured Google API key.")
except KeyError:
    logger.error("Text Server: FATAL - GOOGLE_API_KEY environment variable not set.")
    exit(1)

# --- FastAPI App ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ProductItem(BaseModel):
    name: str
    description: str
    img_url: str
    url: str
    id: str

class ShoppingResult(BaseModel):
    items: List[ProductItem]

# --- Tools ---
def call_vector_search(url, query, rows=None):
    headers = {'Content-Type': 'application/json'}
    payload = {
        "query": query,
        "rows": rows,
        "dataset_id": "mercari3m_mm",
        "use_dense": True,
        "use_sparse": True,
        "rrf_alpha": 0.5,
        "use_rerank": True,
    }
    try:
        response = requests.post(url, headers=headers, data=json.dumps(payload))
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error calling the API: {e}")
        return None

def find_shopping_items(queries: list[str], rows_per_query: Optional[int] = None) -> ShoppingResult:
    if rows_per_query is None:
        rows_per_query = 10
    all_items = []
    for query in queries:
        result = call_vector_search(
            url=config.VECTOR_SEARCH_URL,
            query=query,
            rows=rows_per_query,
        )
        if result and "items" in result:
            all_items.extend(result["items"])
    return ShoppingResult(items=[ProductItem(**item) for item in all_items])

# --- Agents ---
research_agent = Agent(
    model='gemini-1.5-flash',
    name='research_agent',
    description=('A market researcher for an e-commerce site.'),
    instruction='''
        Your role is a market researcher for an e-commerce site.
        When you receive a search request, use Google Search to research what people are buying.
        Then, generate 5 diverse search queries and return them.
    ''',
    tools=[google_search],
)

shop_agent = Agent(
    model='gemini-2.5-flash',
    name='shop_agent',
    description="A shopper's concierge for an e-commerce site",
    instruction='''
        Your role is a shopper's concierge.
        - For broad requests (e.g., "birthday gift for a 10 year old"), use the `research_agent` to generate 5 queries, then use `find_shopping_items` with `rows_per_query=2` for each.
        - For direct searches (e.g., "mugs"), use `find_shopping_items` with `rows_per_query=10`.
        - For specific counts (e.g., "find 10 mugs"), use that number for `rows_per_query`.
        Your entire response must be a single JSON object like:
        {"intro_text": "...", "products": [{"name": "...", "description": "...", "img_url": "...", "url": "...", "id": "..."}]}
    ''',
    tools=[
        research_agent_tool,
        find_shopping_items,
    ],
)

# --- Text Endpoint Logic ---
session_service = InMemorySessionService()

async def run_agent_and_stream_logs(query: str):
    yield f"data: {json.dumps({'type': 'log', 'data': f'User Query: {query}'})}\n\n"
    session = await session_service.create_session(
        app_name=config.APP_NAME,
        user_id=config.USER_ID,
    )
    runner = Runner(
        app_name=config.APP_NAME,
        agent=shop_agent,
        session_service=session_service,
    )
    content = genai_types.Content(role='user', parts=[genai_types.Part(text=query)])
    final_response_text = None
    try:
        async for event in runner.run_async(user_id=config.USER_ID, session_id=session.id, new_message=content):
            log_json = json.dumps({"type": "log", "data": str(event)})
            yield f"data: {log_json}\n\n"
            if event.is_final_response() and event.content and event.content.parts:
                final_response_text = event.content.parts[0].text
    except Exception as e:
        yield f"data: {json.dumps({'type': 'log', 'data': f'An error occurred: {e}'})}\n\n"

    if final_response_text:
        try:
            json_match = re.search(r'\{.*\}', final_response_text, re.DOTALL)
            if json_match:
                yield f"data: {json.dumps({'type': 'result', 'data': json.loads(json_match.group(0))})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'result', 'data': {'intro_text': final_response_text, 'products': []}})}\n\n"
        except json.JSONDecodeError:
            yield f"data: {json.dumps({'type': 'result', 'data': {'intro_text': 'Error decoding agent JSON.', 'products': []}})}\n\n"
    else:
        yield f"data: {json.dumps({'type': 'result', 'data': {'intro_text': 'Sorry, I couldn\'t find anything.', 'products': []}})}\n\n"

# --- Text API Endpoint ---
@app.get("/chat")
async def chat(query: str):
    return StreamingResponse(run_agent_and_stream_logs(query), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)