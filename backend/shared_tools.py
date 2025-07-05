
import os
import json
import requests
from typing import List, Optional
from pydantic import BaseModel

from config import config
from google.adk.agents import Agent
from google.adk.tools.agent_tool import AgentTool
from google.adk.tools import google_search

# --- Pydantic Models for Tooling ---
class ProductItem(BaseModel):
    name: str
    description: str
    img_url: str
    url: str
    id: str

class ShoppingResult(BaseModel):
    items: List[ProductItem]

# --- Tool Functions ---
def call_vector_search(url, query, rows=None):
    """Helper function to call the vector search API."""
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
    """
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

research_agent_tool = AgentTool(agent=research_agent)
