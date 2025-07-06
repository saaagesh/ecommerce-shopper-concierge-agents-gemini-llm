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
from google.adk.tools import google_search
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


shop_agent = Agent(
    model='gemini-2.5-flash',
    name='shop_agent',
    description="A shopper's concierge for an e-commerce site",
    instruction='''
        You are a proactive shopping concierge. IMMEDIATELY execute searches without asking for permission.
        
        **IMMEDIATE TOOL EXECUTION:**
        - Broad requests (e.g., "birthday gifts"): INSTANTLY use `research_agent_tool`, then INSTANTLY use `find_shopping_items` with `rows_per_query=5`
        - Direct searches (e.g., "mugs"): INSTANTLY use `find_shopping_items` with `rows_per_query=10`
        - NEVER ask "Would you like me to search?" - Just DO IT immediately
        
        **AUTOMATIC WORKFLOW:**
        1. INSTANTLY execute appropriate tools based on request type
        2. IMMEDIATELY generate response after tools complete
        3. NO hesitation, NO permission asking, NO waiting
        
        **Response Format:**
        Your entire response must be a single JSON object:
        {"intro_text": "I found some great options for you!", "products": [{"name": "...", "description": "...", "img_url": "...", "url": "...", "id": "..."}]}
        
        **Response Guidelines:**
        - intro_text: Brief, enthusiastic (under 10 words)
        - Use: "Found some great options!" or "Here are perfect items!"
        - NEVER describe specific products
        - BE DECISIVE AND IMMEDIATE
    ''',
    tools=[
        research_agent_tool,
        find_shopping_items,
    ],
)

research_agent = Agent(
    model='gemini-2.5-flash',
    name='research_agent',
    description=('A market researcher for an e-commerce site.'),
    instruction='''
        Your role is a market researcher for an e-commerce site.
        When you receive a search request, use Google Search to research what people are buying.
        Then, generate 5 diverse search queries and return them.
    ''',
    tools=[google_search],
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
    products_sent = False
    
    try:
        async for event in runner.run_async(user_id=config.USER_ID, session_id=session.id, new_message=content):
            log_json = json.dumps({"type": "log", "data": str(event)})
            yield f"data: {log_json}\n\n"
            
            # Enhanced tool execution detection - check multiple possible event structures
            try:
                event_str = str(event)
                
                # Check if this event contains function response or tool execution
                if 'find_shopping_items' in event_str and not products_sent:
                    yield f"data: {json.dumps({'type': 'log', 'data': f'DETECTED find_shopping_items in event: {event_str[:200]}...'})}\n\n"
                    
                    # Method 1: Check for function_response in content parts
                    if hasattr(event, 'content') and event.content and hasattr(event.content, 'parts'):
                        for part in event.content.parts:
                            if hasattr(part, 'function_response') and part.function_response:
                                func_response = part.function_response
                                if func_response.name == "find_shopping_items":
                                    yield f"data: {json.dumps({'type': 'log', 'data': 'Found function_response in content parts'})}\n\n"
                                    try:
                                        response_data = func_response.response
                                        yield f"data: {json.dumps({'type': 'log', 'data': f'Function response data: {str(response_data)[:300]}...'})}\n\n"
                                        
                                        if 'result' in response_data:
                                            result = response_data['result']
                                            if hasattr(result, 'items') and result.items:
                                                # Convert products to dict format and stream immediately
                                                products_data = []
                                                for item in result.items:
                                                    if hasattr(item, 'dict'):
                                                        products_data.append(item.dict())
                                                    else:
                                                        products_data.append({
                                                            'name': getattr(item, 'name', 'Unknown'),
                                                            'description': getattr(item, 'description', ''),
                                                            'img_url': getattr(item, 'img_url', ''),
                                                            'url': getattr(item, 'url', ''),
                                                            'id': getattr(item, 'id', '')
                                                        })
                                                
                                                # Stream products immediately
                                                yield f"data: {json.dumps({'type': 'products', 'data': products_data})}\n\n"
                                                products_sent = True
                                                yield f"data: {json.dumps({'type': 'log', 'data': f'SUCCESS: Streamed {len(products_data)} products immediately'})}\n\n"
                                    except Exception as e:
                                        yield f"data: {json.dumps({'type': 'log', 'data': f'Error processing function_response: {e}'})}\n\n"
                    
                    # Method 2: Check for direct result in event (alternative structure)
                    if hasattr(event, 'result') and not products_sent:
                        yield f"data: {json.dumps({'type': 'log', 'data': 'Found direct result in event'})}\n\n"
                        try:
                            result = event.result
                            if hasattr(result, 'items') and result.items:
                                products_data = []
                                for item in result.items:
                                    if hasattr(item, 'dict'):
                                        products_data.append(item.dict())
                                    else:
                                        products_data.append({
                                            'name': getattr(item, 'name', 'Unknown'),
                                            'description': getattr(item, 'description', ''),
                                            'img_url': getattr(item, 'img_url', ''),
                                            'url': getattr(item, 'url', ''),
                                            'id': getattr(item, 'id', '')
                                        })
                                
                                yield f"data: {json.dumps({'type': 'products', 'data': products_data})}\n\n"
                                products_sent = True
                                yield f"data: {json.dumps({'type': 'log', 'data': f'SUCCESS: Streamed {len(products_data)} products from direct result'})}\n\n"
                        except Exception as e:
                            yield f"data: {json.dumps({'type': 'log', 'data': f'Error processing direct result: {e}'})}\n\n"
                    
                    # Method 3: Parse from string representation as fallback
                    if not products_sent and 'ShoppingResult' in event_str:
                        yield f"data: {json.dumps({'type': 'log', 'data': 'Attempting to parse products from string representation'})}\n\n"
                        try:
                            # Try to extract product data from string representation
                            # Look for items pattern in the string
                            items_match = re.search(r"items=\[(.*?)\]", event_str, re.DOTALL)
                            if items_match:
                                yield f"data: {json.dumps({'type': 'log', 'data': 'Found items pattern in string'})}\n\n"
                                # This is a fallback - we'll trigger product extraction from final response
                        except Exception as e:
                            yield f"data: {json.dumps({'type': 'log', 'data': f'Error parsing string representation: {e}'})}\n\n"
                            
            except Exception as e:
                yield f"data: {json.dumps({'type': 'log', 'data': f'Error in enhanced detection: {e}'})}\n\n"
            
            if event.is_final_response() and event.content and event.content.parts:
                final_response_text = event.content.parts[0].text
                
    except Exception as e:
        yield f"data: {json.dumps({'type': 'log', 'data': f'An error occurred: {e}'})}\n\n"

    # Send final response and extract products if not already sent
    yield f"data: {json.dumps({'type': 'log', 'data': f'Processing final response. Has final_response_text: {bool(final_response_text)}'})}\n\n"
    
    if final_response_text:
        yield f"data: {json.dumps({'type': 'log', 'data': f'Final response text: {final_response_text[:200]}...'})}\n\n"
        try:
            json_match = re.search(r'\{.*\}', final_response_text, re.DOTALL)
            if json_match:
                yield f"data: {json.dumps({'type': 'log', 'data': 'Found JSON in final response'})}\n\n"
                parsed_response = json.loads(json_match.group(0))
                intro_text = parsed_response.get('intro_text', 'I found some great options for you!')
                yield f"data: {json.dumps({'type': 'log', 'data': f'Extracted intro_text: {intro_text}'})}\n\n"
                
                # If products weren't sent during streaming, send them now
                if not products_sent and 'products' in parsed_response and parsed_response['products']:
                    yield f"data: {json.dumps({'type': 'log', 'data': 'Sending products from final response'})}\n\n"
                    yield f"data: {json.dumps({'type': 'products', 'data': parsed_response['products']})}\n\n"
                    products_sent = True
                
                # Always send a friendly response
                if intro_text and intro_text.strip():
                    yield f"data: {json.dumps({'type': 'log', 'data': f'Sending final_text: {intro_text}'})}\n\n"
                    yield f"data: {json.dumps({'type': 'final_text', 'data': intro_text})}\n\n"
                else:
                    # Fallback if no intro_text
                    fallback_text = "Here are some items that might work well!" if products_sent else "I found some options for you!"
                    yield f"data: {json.dumps({'type': 'log', 'data': f'Using fallback text: {fallback_text}'})}\n\n"
                    yield f"data: {json.dumps({'type': 'final_text', 'data': fallback_text})}\n\n"
            else:
                yield f"data: {json.dumps({'type': 'log', 'data': 'No JSON found, sending raw final_response_text'})}\n\n"
                yield f"data: {json.dumps({'type': 'final_text', 'data': final_response_text})}\n\n"
        except json.JSONDecodeError as e:
            yield f"data: {json.dumps({'type': 'log', 'data': f'JSON decode error: {e}'})}\n\n"
            # If JSON parsing fails but we have products, give positive response
            fallback_text = "Here are some great options for you!" if products_sent else "Search completed!"
            yield f"data: {json.dumps({'type': 'final_text', 'data': fallback_text})}\n\n"
    else:
        yield f"data: {json.dumps({'type': 'log', 'data': 'No final_response_text, using fallback'})}\n\n"
        # No final response text, but provide appropriate message
        final_text = "Here are some items that might work well!" if products_sent else "Sorry, I could not find anything."
        yield f"data: {json.dumps({'type': 'final_text', 'data': final_text})}\n\n"
    
    yield f"data: {json.dumps({'type': 'log', 'data': 'Finished processing final response'})}\n\n"

# --- Text API Endpoint ---
@app.get("/chat")
async def chat(query: str):
    return StreamingResponse(run_agent_and_stream_logs(query), media_type="text/event-stream")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)