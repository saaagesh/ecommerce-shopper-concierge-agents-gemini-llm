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
from shared_tools import find_shopping_items, research_agent_tool, research_agent_tool

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
            tools=[find_shopping_items, research_agent_tool],  # Add the research agent tool
            instruction='''
                You are a helpful shopping and research assistant.
                You have two tools at your disposal:

                1. `research_agent_tool`: Use this for broad, exploratory requests (e.g., "ideas for a 10 year old's birthday"). This tool will generate a list of more specific search queries. You should then take those queries and use the other tool.

                2. `find_shopping_items`: Use this for specific product searches (e.g., "red dress", "lego sets"). You can also use this tool with the queries you get from the research_agent_tool. After this tool returns results, you MUST verbally summarize them and also include a JSON block with the full product data in your text response, formatted EXACTLY like this:
                    PRODUCTS_JSON_START
                    {"products": [{"name": "...", "description": "...", "img_url": "...", "url": "...", "id": "..."}]}
                    PRODUCTS_JSON_END

                Listen to the user's request and decide which tool is appropriate. For broad requests, use the research tool first, then the shopping tool. For specific requests, use the shopping tool directly.
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
            # Revert to only requesting AUDIO, as this was the last working configuration.
            # The agent should still provide the text part for the tool call.
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
            async for event in runner.run_live(
                user_id=session.user_id,
                session_id=session.id,
                live_request_queue=live_request_queue,
                run_config=run_config,
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "text") and part.text:
                            if not is_bot_speaking:
                                await self._send_json(websocket, "bot_speech_start")
                                is_bot_speaking = True
                            await self._process_text_part(websocket, part.text)

                        if hasattr(part, "inline_data") and part.inline_data:
                            b64_audio = base64.b64encode(part.inline_data.data).decode("utf-8")
                            await self._send_json(websocket, "audio", b64_audio)

                if event.actions.state_delta.get("turn_complete", False):
                    if is_bot_speaking:
                        await self._send_json(websocket, "bot_speech_end")
                        is_bot_speaking = False
                    await self._send_json(websocket, "turn_complete")

        await asyncio.gather(handle_incoming_messages(), handle_outgoing_messages())

    async def _process_text_part(self, websocket, text_content):
        """Processes text from the model, extracting product JSON if present."""
        match = re.search(r'PRODUCTS_JSON_START(.*?)PRODUCTS_JSON_END', text_content, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            try:
                product_data = json.loads(json_str)
                if 'products' in product_data:
                    logger.info(f"SENDING PRODUCTS TO FRONTEND: {len(product_data['products'])} items")
                    await self._send_json(websocket, "products", product_data['products'])
                # Remove the JSON block from the text to not speak it
                text_content = re.sub(r'PRODUCTS_JSON_START.*?PRODUCTS_JSON_END', '', text_content, flags=re.DOTALL).strip()
            except json.JSONDecodeError:
                logger.error("Failed to decode product JSON from agent response.")

        if text_content:
            await self._send_json(websocket, "text", text_content)

    async def _process_text_part(self, websocket, text_content):
        """Processes text from the model, extracting product JSON if present."""
        match = re.search(r'PRODUCTS_JSON_START(.*?)PRODUCTS_JSON_END', text_content, re.DOTALL)
        if match:
            json_str = match.group(1).strip()
            try:
                product_data = json.loads(json_str)
                if 'products' in product_data:
                    logger.info(f"SENDING PRODUCTS TO FRONTEND: {len(product_data['products'])} items")
                    await self._send_json(websocket, "products", product_data['products'])
                # Remove the JSON block from the text to not speak it
                text_content = re.sub(r'PRODUCTS_JSON_START.*?PRODUCTS_JSON_END', '', text_content, flags=re.DOTALL).strip()
            except json.JSONDecodeError:
                logger.error("Failed to decode product JSON from agent response.")

        if text_content:
            await self._send_json(websocket, "text", text_content)


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