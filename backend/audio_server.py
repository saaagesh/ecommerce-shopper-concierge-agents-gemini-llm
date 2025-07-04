import asyncio
import json
import base64
import logging
import os
from dotenv import load_dotenv

from google.adk.agents import Agent, LiveRequestQueue
from google.adk.runners import Runner
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types as genai_types
import google.generativeai as genai

# Import the base server class
from audio_common import BaseWebSocketServer, logger

# --- Setup ---
load_dotenv()
try:
    genai.configure(api_key=os.environ["GOOGLE_API_KEY"])
    logger.info("Audio Server: Successfully configured Google API key.")
except KeyError:
    logger.error("Audio Server: FATAL - GOOGLE_API_KEY environment variable not set.")
    exit(1)

# --- Agent and Server Implementation ---
class AudioADKServer(BaseWebSocketServer):
    def __init__(self, host="0.0.0.0", port=8765):
        super().__init__(host, port)
        self.agent = Agent(
            name="customer_service_agent",
            model="gemini-2.0-flash-live-001",
            instruction="You are a helpful voice assistant.",
        )
        self.session_service = InMemorySessionService()

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
                    prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(voice_name="Puck")
                )
            ),
            response_modalities=["AUDIO"],
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
            async for event in runner.run_live(
                user_id=session.user_id,
                session_id=session.id,
                live_request_queue=live_request_queue,
                run_config=run_config,
            ):
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if hasattr(part, "inline_data") and part.inline_data:
                            b64_audio = base64.b64encode(part.inline_data.data).decode("utf-8")
                            await websocket.send(json.dumps({"type": "audio", "data": b64_audio}))
                        if hasattr(part, "text") and part.text:
                            await websocket.send(json.dumps({"type": "text", "data": part.text}))
                if event.turn_complete:
                    await websocket.send(json.dumps({"type": "turn_complete"}))

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