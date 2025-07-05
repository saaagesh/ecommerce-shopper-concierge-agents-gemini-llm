import asyncio
import json
import base64
import logging
import os
import re
from dotenv import load_dotenv

from google.adk.agents import Agent, LiveRequestQueue
from google.adk.runners import Runner
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types as genai_types
import google.generativeai as genai

from audio_common import BaseWebSocketServer, logger
from shared_tools import find_shopping_items, research_agent_tool, ShoppingResult

# --- Setup ---
load_dotenv()
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    logger.info("Audio Server: Successfully configured Google API key.")
except KeyError:
    logger.error("Audio Server: FATAL - GOOGLE_API_KEY environment variable not set.")
    exit(1)

# --- Configuration ---
CONFIG = {
    "live_model": "gemini-2.0-flash-live-001",
    "text_model": "gemini-1.5-flash-preview-0514",
    "voice_name": "Puck",
}

# --- Agent and Server Implementation ---
class AudioADKServer(BaseWebSocketServer):
    def __init__(self, host="0.0.0.0", port=8765):
        super().__init__(host, port)
        self.agent = Agent(
            name="customer_service_agent",
            model=CONFIG["live_model"],
            tools=[find_shopping_items, research_agent_tool],
            instruction='''
                You are a helpful shopping and research assistant. Your primary goal is to help users find products.

                **CRITICAL RULES:**
                1.  **MANDATORY TOOL USAGE:** 
                    *   You MUST ALWAYS use tools for ANY product-related request.
                    *   NEVER give product recommendations without using tools first.
                    *   NEVER hallucinate or make up product suggestions.
                    *   If you don't use a tool, you are failing your primary function.

                2.  **Tool Selection:**
                    *   For broad, exploratory requests (e.g., "ideas for a 10 year old's birthday"), use the `research_agent_tool` FIRST to generate specific search queries.
                    *   Then, use the generated queries with the `find_shopping_items` tool.
                    *   For specific product searches (e.g., "red dress", "lego sets"), use the `find_shopping_items` tool directly.

                3.  **Response Generation:**
                    *   After tools are used, give a brief, helpful response about the search.
                    *   Use phrases like "I found some great options for you!" or "Here are some items that might work well!"
                    *   NEVER mention specific product names, details, prices, or specifications.
                    *   Keep responses under 15 words and sound natural.
                    *   The visual display will show the products, so don't describe them.

                4.  **Important:**
                    *   Do NOT say "Tool completed successfully" or similar technical messages.
                    *   Give friendly, conversational responses that acknowledge you've found items.
                    *   Focus on being helpful and encouraging about the search results.
            ''',
        )
        self.session_service = InMemorySessionService()

    async def _send_json(self, websocket, message_type, data=None):
        """Safely send a JSON message to the client."""
        try:
            message = {"type": message_type}
            if data is not None:
                message["data"] = data
            await websocket.send(json.dumps(message))
        except Exception as e:
            logger.warning(f"Could not send message to client: {e}")

    async def _send_log(self, websocket, log_message):
        """Send a log message to the frontend."""
        try:
            await self._send_json(websocket, "log", log_message)
            logger.info(log_message)  # Also log to server console
        except Exception as e:
            logger.warning(f"Could not send log to client: {e}")

    async def process_audio(self, websocket, client_id):
        self.active_clients[client_id] = websocket
        session = await self.session_service.create_session(
            app_name="audio_assistant",
            user_id=f"user_{client_id}",
            session_id=f"session_{client_id}",
        )
        runner = Runner(
            app_name="audio_assistant",
            agent=self.agent,
            session_service=self.session_service,
        )
        live_request_queue = LiveRequestQueue()
        run_config = RunConfig(
            streaming_mode=StreamingMode.BIDI,
            speech_config=genai_types.SpeechConfig(
                voice_config=genai_types.VoiceConfig(
                    prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name=CONFIG["voice_name"])
                )
            ),
            response_modalities=[genai_types.Modality.AUDIO],
            output_audio_transcription=genai_types.AudioTranscriptionConfig(),
            input_audio_transcription=genai_types.AudioTranscriptionConfig(),
        )

        async def handle_incoming_messages():
            async for message in websocket:
                try:
                    data = json.loads(message)
                    if data.get("type") == "audio":
                        audio_bytes = base64.b64decode(data.get("data", ""))
                        live_request_queue.send_realtime(
                            genai_types.Blob(data=audio_bytes, mime_type="audio/pcm;rate=16000")
                        )
                except json.JSONDecodeError:
                    logger.error("Invalid JSON message received")

        async def handle_outgoing_messages():
            is_bot_speaking = False
            processed_tool_calls = set()  # Track processed tool calls to prevent duplicates
            processed_function_responses = set()  # Track processed function responses
            async for event in runner.run_live(
                user_id=session.user_id,
                session_id=session.id,
                live_request_queue=live_request_queue,
                run_config=run_config,
            ):
                # Log all events for debugging with more detail
                event_type = type(event).__name__
                await self._send_log(websocket, f"EVENT: {event_type}")
                
                # Log event attributes for debugging
                event_attrs = [attr for attr in dir(event) if not attr.startswith('_')]
                await self._send_log(websocket, f"EVENT ATTRS: {event_attrs[:10]}")  # Limit to first 10 attrs
                
                # Log event content if available
                if hasattr(event, 'content') and event.content:
                    content_str = str(event.content)[:200]
                    await self._send_log(websocket, f"EVENT CONTENT: {content_str}...")
                    
                    # Check for function_response in content parts (this is where tool results are)
                    if hasattr(event.content, 'parts') and event.content.parts:
                        for part in event.content.parts:
                            # Check for function_response which contains tool results
                            if hasattr(part, 'function_response') and part.function_response:
                                func_response = part.function_response
                                
                                # Create unique ID for this function response to prevent duplicates
                                func_response_id = f"{func_response.name}_{func_response.id}"
                                
                                if func_response_id in processed_function_responses:
                                    await self._send_log(websocket, f"SKIPPING DUPLICATE FUNCTION RESPONSE: {func_response.name}")
                                    continue
                                    
                                processed_function_responses.add(func_response_id)
                                await self._send_log(websocket, f"FUNCTION RESPONSE DETECTED: {func_response.name}")
                                
                                if func_response.name == "find_shopping_items":
                                    await self._send_log(websocket, "PROCESSING find_shopping_items function response")
                                    try:
                                        # Get the response data
                                        response_data = func_response.response
                                        await self._send_log(websocket, f"FUNCTION RESPONSE DATA: {str(response_data)[:300]}...")
                                        
                                        # Extract the result
                                        if 'result' in response_data:
                                            result = response_data['result']
                                            if hasattr(result, 'items'):
                                                products = result.items
                                            elif isinstance(result, dict) and 'items' in result:
                                                products = [ProductItem(**item) for item in result['items']]
                                            else:
                                                products = []
                                        else:
                                            products = []
                                        
                                        await self._send_log(websocket, f"EXTRACTED {len(products)} PRODUCTS")
                                        
                                        # Send products IMMEDIATELY to frontend
                                        if products:
                                            # Convert to dict format for JSON serialization
                                            products_data = []
                                            for product in products:
                                                if hasattr(product, 'dict'):
                                                    products_data.append(product.dict())
                                                elif isinstance(product, dict):
                                                    products_data.append(product)
                                                else:
                                                    products_data.append({
                                                        'name': getattr(product, 'name', 'Unknown'),
                                                        'description': getattr(product, 'description', ''),
                                                        'img_url': getattr(product, 'img_url', ''),
                                                        'url': getattr(product, 'url', ''),
                                                        'id': getattr(product, 'id', '')
                                                    })
                                            
                                            await self._send_log(websocket, f"SENDING {len(products_data)} PRODUCTS TO FRONTEND")
                                            await self._send_json(websocket, "products", products_data)
                                            await self._send_log(websocket, f"PRODUCTS SENT SUCCESSFULLY - Sample: {products_data[0]['name'] if products_data else 'None'}")
                                        else:
                                            await self._send_log(websocket, "NO PRODUCTS TO SEND - EMPTY RESULTS")
                                            
                                    except Exception as e:
                                        await self._send_log(websocket, f"ERROR processing function response: {e}")
                            
                            # Also check for code_execution_result which might contain the output
                            elif hasattr(part, 'code_execution_result') and part.code_execution_result:
                                code_result = part.code_execution_result
                                await self._send_log(websocket, f"CODE EXECUTION RESULT: {str(code_result.output)[:200]}...")
                                
                                # Replace code execution output to prevent reading
                                if "find_shopping_items" in str(code_result.output):
                                    code_result.output = "Search completed successfully."
                                    await self._send_log(websocket, "REPLACED CODE EXECUTION OUTPUT")
                
                # Legacy tool detection (keeping for compatibility)
                tool_executed = False
                tool_obj = None
                
                for attr_name in ['tool_code', 'tool_call', 'function_call', 'tool_use', 'tool_result', 'tool_output']:
                    if hasattr(event, attr_name):
                        attr_value = getattr(event, attr_name)
                        if attr_value:
                            tool_executed = True
                            tool_obj = attr_value
                            await self._send_log(websocket, f"FOUND {attr_name}: {str(attr_value)[:200]}...")
                            break
                
                # Handle tool execution BEFORE any other processing
                if tool_executed and tool_obj:
                    # Try to get tool name and output from various possible attributes
                    tool_name = getattr(tool_obj, 'tool_name', None) or getattr(tool_obj, 'name', None) or "unknown_tool"
                    tool_output = getattr(tool_obj, 'output', None) or getattr(tool_obj, 'result', None) or str(tool_obj)
                    
                    # Create a unique identifier for this tool call
                    tool_call_id = f"{tool_name}_{hash(str(tool_output))}"
                    
                    # Skip if we've already processed this tool call
                    if tool_call_id in processed_tool_calls:
                        await self._send_log(websocket, f"SKIPPING DUPLICATE TOOL CALL: {tool_name}")
                        continue
                        
                    processed_tool_calls.add(tool_call_id)
                    await self._send_log(websocket, f"TOOL EXECUTION DETECTED: {tool_name}")
                    await self._send_log(websocket, f"ORIGINAL TOOL OUTPUT: {str(tool_output)[:200]}...")
                    
                    # Process find_shopping_items tool
                    if "find_shopping_items" in tool_name:
                        await self._send_log(websocket, "PROCESSING find_shopping_items tool")
                        try:
                            # Parse the raw tool output
                            if isinstance(tool_output, str):
                                tool_output_data = json.loads(tool_output)
                            elif hasattr(tool_output, 'dict'):
                                tool_output_data = tool_output.dict()
                            else:
                                tool_output_data = tool_output
                                
                            validated_products = ShoppingResult(items=tool_output_data.get("items", []))
                            await self._send_log(websocket, f"VALIDATED PRODUCTS: {len(validated_products.items)} items")
                            
                            # 1. Send products IMMEDIATELY to the frontend
                            if validated_products.items:
                                await self._send_log(websocket, f"SENDING {len(validated_products.items)} PRODUCTS TO FRONTEND")
                                products_data = validated_products.dict()['items']
                                await self._send_json(websocket, "products", products_data)
                                await self._send_log(websocket, f"PRODUCTS SENT SUCCESSFULLY - Sample: {products_data[0]['name'] if products_data else 'None'}")
                            else:
                                await self._send_log(websocket, "NO PRODUCTS TO SEND - EMPTY RESULTS")
                            
                            # 2. Replace with extremely simple confirmation - no specifics at all
                            simple_response = "Search complete."
                            if hasattr(tool_obj, 'output'):
                                tool_obj.output = simple_response
                            await self._send_log(websocket, f"REPLACED TOOL OUTPUT WITH: {simple_response}")
                            
                        except (json.JSONDecodeError, Exception) as e:
                            await self._send_log(websocket, f"ERROR processing find_shopping_items output: {e}")
                            if hasattr(tool_obj, 'output'):
                                tool_obj.output = "Search complete."
                    
                    # Process research_agent_tool
                    elif "research_agent_tool" in tool_name:
                        await self._send_log(websocket, "PROCESSING research_agent_tool")
                        try:
                            # For research tool, just confirm it worked
                            if hasattr(tool_obj, 'output'):
                                tool_obj.output = "Research complete."
                            await self._send_log(websocket, "RESEARCH TOOL OUTPUT REPLACED WITH SIMPLE CONFIRMATION")
                        except Exception as e:
                            await self._send_log(websocket, f"ERROR processing research_agent_tool output: {e}")
                            if hasattr(tool_obj, 'output'):
                                tool_obj.output = "Research complete."
                    
                    else:
                        await self._send_log(websocket, f"UNKNOWN TOOL: {tool_name}")
                        if hasattr(tool_obj, 'output'):
                            tool_obj.output = "Task complete."

                # Handle text content from Gemini or User
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            # Check if this is user input (role='user') or bot response
                            if hasattr(event.content, 'role') and event.content.role == 'user':
                                # This is user transcription
                                await self._send_json(websocket, "user_text", part.text)
                                await self._send_log(websocket, f"USER TRANSCRIPTION: {part.text}")
                            else:
                                # This is bot response - check if it contains tool output to filter
                                text_content = part.text.strip()
                                
                                # Skip if it's just "Tool completed successfully" or similar
                                if any(phrase in text_content.lower() for phrase in [
                                    "tool completed successfully", 
                                    "search complete",
                                    "research complete", 
                                    "task complete",
                                    "search completed successfully"
                                ]):
                                    await self._send_log(websocket, f"SKIPPING TOOL COMPLETION MESSAGE: {text_content}")
                                    continue
                                
                                # Send actual meaningful bot responses
                                if text_content and len(text_content.strip()) > 0:
                                    if not is_bot_speaking:
                                        await self._send_json(websocket, "bot_speech_start")
                                        is_bot_speaking = True
                                    await self._send_json(websocket, "text", part.text)
                                    await self._send_log(websocket, f"BOT RESPONSE: {part.text}")

                        if hasattr(part, "inline_data") and part.inline_data:
                            b64_audio = base64.b64encode(part.inline_data.data).decode("utf-8")
                            await self._send_json(websocket, "audio", b64_audio)

                if event.actions.state_delta.get("turn_complete", False):
                    if is_bot_speaking:
                        await self._send_json(websocket, "bot_speech_end")
                        is_bot_speaking = False
                    await self._send_json(websocket, "turn_complete")
                    await self._send_log(websocket, "TURN COMPLETE")

        await asyncio.gather(handle_incoming_messages(), handle_outgoing_messages())



async def main():
    server = AudioADKServer()
    await server.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Exiting application via KeyboardInterrupt...")
    except Exception as e:
        logger.error(f"Unhandled exception in main: {e}", exc_info=True)