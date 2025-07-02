import os
import logging
import asyncio
import requests
import json
from typing import Dict, List

from fastapi import FastAPI
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

class Query(BaseModel):
    text: str

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

def find_shopping_items(queries: list[str]) -> Dict[str, str]:
    items = []
    for query in queries:
        result = call_vector_search(
            url=config.VECTOR_SEARCH_URL,
            query=query,
            rows=3,
        )
        if result and "items" in result:
            items.extend(result["items"])
    return {"items": items}

# --- Agents ---
research_agent = Agent(
    model='gemini-1.5-flash',
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
    model='gemini-1.5-flash',
    name='shop_agent',
    description=(
        'A shopper\'s concierge for an e-commerce site'
    ),
    instruction=f'''
        Your role is a shopper's concierge for an e-commerce site with millions of
        items. Follow the following steps.

        When you recieved a search request from an user, pass it to `research_agent`
        tool, and receive 5 generated queries. Then, pass the list of queries to
        `find_shopping_items` to find items. When you recieved a list of items from
        the tool, answer to the user with item's name, description and the image url.
    ''',
    tools=[
        AgentTool(agent=research_agent),
        find_shopping_items,
    ],
)

# --- ADK Runner ---
session_service = InMemorySessionService()

async def run_agent(query: str):
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
    async for event in runner.run_async(user_id=config.USER_ID, session_id=session.id, new_message=content):
        if event.is_final_response():
            if event.content and event.content.parts:
                final_response_text = event.content.parts[0].text
            break
    return final_response_text

# --- API Endpoint ---
@app.post("/chat")
async def chat(query: Query):
    if not config.GOOGLE_API_KEY or config.GOOGLE_API_KEY == "YOUR_API_KEY":
        return {"error": "GOOGLE_API_KEY environment variable not set."}
    os.environ["GOOGLE_API_KEY"] = config.GOOGLE_API_KEY

    response = await run_agent(query.text)
    return {"response": response}

