import os
import logging
import asyncio
import requests
import json
import re
from typing import Dict, List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools import google_search
from google.genai import types

from config import config

# Ignore warnings from ADK and Gemini APIs
logging.getLogger("google.adk.runners").setLevel(logging.ERROR)
logging.getLogger("google_genai.types").setLevel(logging.ERROR)

# --- FastAPI App ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

class Query(BaseModel):
    text: str

class ProductItem(BaseModel):
    name: str
    description: str
    img_url: str
    url: str
    id: str

class ShoppingResult(BaseModel):
    items: List[ProductItem]

# --- Vector Search Tool ---
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
    """
    Finds shopping items from the vector search API based on a list of queries.
    Returns a list of products with their details.
    :param queries: A list of search terms.
    :param rows_per_query: The number of items to retrieve for each query.
    """
    # Set a default value inside the function if not provided
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
    
    # Ensure the returned data conforms to the Pydantic model
    return ShoppingResult(items=[ProductItem(**item) for item in all_items])

# --- Agents ---
research_agent = Agent(
    model='gemini-2.5-flash',
    name='research_agent',
    description=('''
        A market researcher for an e-commerce site. Receives a search request
        from a user, and returns a list of 5 generated queries in English.
    '''),
    instruction=f'''
        Your role is a market researcher for an e-commerce site with millions of
        items.

        When you recieved a search request from an user, use Google Search tool to
        research on what kind of items people are purchasing for the user's intent.

        Then, generate 5 queries finding those items on the e-commerce site and
        return them.
    ''',
    tools=[google_search],
)

shop_agent = Agent(
    model='gemini-2.5-flash',
    name='shop_agent',
    description=(
        'A shopper\'s concierge for an e-commerce site'
    ),
    instruction=f'''
        Your role is a shopper's concierge for an e-commerce site with millions of
        items. When you receive a search request from a user, first, analyze the request.

        - If the request is a direct search for a specific item (e.g., "mugs", "red t-shirt"), you should call the `find_shopping_items` tool with `rows_per_query` set to 10.
        - If the user asks for a specific number of items (e.g., "find 10 mugs", "show me 25 t-shirts"), use the `rows_per_query` parameter in the `find_shopping_items` tool.
        - If the request is broad or requires research (e.g., "birthday gift for a 10 year old"), you MUST first use the `research_agent` tool to generate 5 specific search queries. Then, use those generated queries with the `find_shopping_items` tool, setting `rows_per_query` to 2 for each query to get a total of 10 results.

        After finding the items, you MUST format your entire response as a single JSON object.
        Do not include any text outside of the JSON object.

        The JSON object should have the following structure:
        {{
          "intro_text": "A brief, friendly introductory message for the user.",
          "products": [
            {{
              "name": "Product Name",
              "description": "Product Description",
              "img_url": "https://example.com/image.jpg"
            }}
          ]
        }}

        Example for a direct search with a specific count:
        User request: "find 10 mugs"
        You think: The user is asking for 10 specific items. I will call `find_shopping_items` directly with `rows_per_query=10`.
        You call: `find_shopping_items(queries=["mugs"], rows_per_query=10)`
        You receive a `ShoppingResult` object from the tool.
        You will then use the data from that object to construct your final JSON response.
        Your response MUST include all the items returned by the tool.
        You respond:
        {{
          "intro_text": "Here are 10 mugs I found for you:",
          "products": [
             // ... 10 product objects here ...
          ]
        }}
    ''',
    tools=[
        AgentTool(agent=research_agent),
        find_shopping_items,
    ],
)

from starlette.responses import StreamingResponse

# ... (imports)

# --- ADK Runner ---
session_service = InMemorySessionService()

async def run_agent_and_stream_logs(query: str):
    """
    Runs the agent and streams logs and the final result in SSE format.
    """
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
    content = types.Content(role='user', parts=[types.Part(text=query)])
    
    final_response_text = None

    try:
        async for event in runner.run_async(user_id=config.USER_ID, session_id=session.id, new_message=content):
            log_json = json.dumps({"type": "log", "data": str(event)})
            yield f"data: {log_json}\n\n"

            if event.is_final_response():
                if event.content and event.content.parts:
                    final_response_text = event.content.parts[0].text
    except Exception as e:
        error_log = json.dumps({"type": "log", "data": f"An error occurred: {e}"})
        yield f"data: {error_log}\n\n"

    if final_response_text:
        try:
            json_match = re.search(r'\{.*\}', final_response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                response_json = json.loads(json_str)
                result_json = json.dumps({"type": "result", "data": response_json})
                yield f"data: {result_json}\n\n"
            else:
                fallback_json = json.dumps({"type": "result", "data": {"intro_text": final_response_text, "products": []}})
                yield f"data: {fallback_json}\n\n"
        except json.JSONDecodeError:
            error_json = json.dumps({"type": "result", "data": {"intro_text": "Error decoding agent's JSON.", "products": []}})
            yield f"data: {error_json}\n\n"
    else:
        not_found_json = json.dumps({"type": "result", "data": {"intro_text": "Sorry, I couldn't find anything.", "products": []}})
        yield f"data: {not_found_json}\n\n"


# --- API Endpoint ---
@app.get("/chat")
async def chat(query: str):
    if not config.GOOGLE_API_KEY or config.GOOGLE_API_KEY == "YOUR_API_KEY":
        return {"error": "GOOGLE_API_KEY environment variable not set."}
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    return StreamingResponse(run_agent_and_stream_logs(query), media_type="text/event-stream")

