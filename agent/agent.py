import asyncio
import logging

from dotenv import load_dotenv

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    AutoSubscribe,
    JobContext,
    JobProcess,
    StopResponse,
    cli,
    llm,
    room_io,
    utils,
    function_tool,
)
from livekit.plugins import deepgram, openai, silero
import json
import time
import uuid
from livekit.agents.tts import SynthesizedAudio
from typing import AsyncIterable


server = AgentServer()


load_dotenv()

logger = logging.getLogger("transcriber")


# This example demonstrates how to transcribe audio from multiple remote participants.
# It creates agent sessions for each participant and transcribes their audio.
def get_combined_chat_context(
    chat_contexts: dict[str, llm.ChatContext],
    chat_context: llm.ChatContext | None = None,
) -> llm.ChatContext:
    """Get all chat messages from all participants sorted by timestamp."""
    combined_context = llm.ChatContext()
    for item in chat_context.items:
        combined_context.insert(item=item)

    for participant_identity, chat_context in chat_contexts.items():
        msg = ""
        if len(chat_context.items) > 0:
            for item in chat_context.items:
                msg += (
                    item.content
                    if isinstance(item.content, str)
                    else " ".join(item.content)
                ) + "\n"
        combined_context.add_message(
            role="user",
            content=f"Participant Name: {participant_identity}\nMessage: ```{msg}```",
            created_at=item.created_at,
        )

    return combined_context


class Transcriber(Agent):
    def __init__(
        self,
        participant_identity: str,
        chat_context: llm.ChatContext,
        room: rtc.Room,
        coordinator,
    ):
        super().__init__(
            instructions="not-needed",
            stt=deepgram.STT(),
        )
        self.participant_identity = participant_identity
        self.chat_context = chat_context
        self.room = room
        self.coordinator = coordinator

    async def on_user_turn_completed(
        self, chat_ctx: llm.ChatContext, new_message: llm.ChatMessage
    ):
        user_transcript = new_message.text_content

        # Maintain chat context by appending the user's message
        self.chat_context.add_message(
            role="user",
            content=user_transcript,
        )

        logger.info(f"[{self.participant_identity}] User said: {user_transcript}")
        logger.info(
            f"[{self.participant_identity}] Chat context now has {len(self.chat_context.items)} messages"
        )

        # Broadcast finalized transcript via RPC

        await self.room.local_participant.send_text(
            text=json.dumps(
                {
                    "speaker": self.participant_identity,
                    "text": user_transcript,
                    "timestamp": int(time.time() * 1000),
                }
            ),
            topic="transcription",
        )
        self.coordinator.on_activity(self.participant_identity, user_transcript)
        raise StopResponse()


class Coordinator:
    def __init__(self, ctx, sessions, chat_contexts):
        self.sessions = sessions
        self._chat_contexts = chat_contexts
        self.ctx = ctx
        self.room = ctx.room
        self.llm = openai.LLM(model="gpt-4o")
        self.chat_ctx = llm.ChatContext()
        self.chat_ctx.add_message(
            role="system",
            content=(
                "You are a Dungeon Master for a D&D game. Your goal is to guide the players through a scenario. "
                "Engage the participants, describe the scene, and use your tools to make it interactive. "
                "You can send private messages, polls, popups, and generate images using tool calls "
                "Please respond with only plain text paragraph without markdown formatting "
                "Respond with maximum of 5 sentences"
            ),
        )
        self.last_activity = time.time()
        self.processing = False
        self._task = None
        self.active_poll = None
        self.waiting_for_user = False  # Wait for user input after coordinator speaks

    def start(self):
        self._task = asyncio.create_task(self.run_loop())

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def on_activity(self, participant_identity: str, text: str):
        self.last_activity = time.time()
        self.waiting_for_user = False  # User spoke, so we can monitor silence again
        # Add user activity to context so Coordinator knows what happened

    async def send_text(self, text: str):
        audio_source = rtc.AudioSource(44100, 1)

        track = rtc.LocalAudioTrack.create_audio_track("agent-audio", audio_source)
        await self.room.local_participant.publish_track(track)

        tts = deepgram.TTS()
        tts_stream = tts.stream()

        async def send_audio(audio_stream: AsyncIterable[SynthesizedAudio]):
            async for a in audio_stream:
                await audio_source.capture_frame(a.audio.frame)

        # create a task to consume and publish audio frames
        tts_stream.push_text(text)
        asyncio.create_task(send_audio(tts_stream))

        # push text into the stream, TTS stream will emit audio frames along with events
        # indicating sentence (or segment) boundaries.
        tts_stream.end_input()

    async def run_loop(self):
        logger.info("Coordinator loop started")
        while True:
            await asyncio.sleep(0.5)
            if self.processing:
                continue

            # Check for silence (3 seconds)
            # Only check if we are NOT waiting for user input

            if not self.waiting_for_user and time.time() - self.last_activity > 5.0:
                logger.info("Silence detected, triggering Coordinator")
                self.processing = True
                try:
                    # Generate response
                    new_chat = get_combined_chat_context(
                        self._chat_contexts, self.chat_ctx
                    )

                    stream = self.llm.chat(
                        chat_ctx=new_chat,
                        tools=[
                            # self.send_private_message,
                            # self.broadcast_message,
                            # self.create_poll,
                            # self.show_popup,
                        ],
                        # TODO: ADD tools here
                    )

                    response_text = ""
                    async for chunk in stream:
                        if chunk.delta and chunk.delta.content:
                            response_text += chunk.delta.content

                    if response_text:
                        await self.room.local_participant.send_text(
                            text=json.dumps(
                                {"type": "broadcast", "message": response_text}
                            ),
                            topic="coordinator_broadcast",
                        )
                        logger.info(f"Coordinator response: {response_text}")
                        self.chat_ctx.add_message(
                            role="assistant", content=response_text
                        )

                except Exception as e:
                    logger.error(f"Coordinator error: {e}")
                finally:
                    self.processing = False
                    self.last_activity = time.time()  # Reset timer
                    self.waiting_for_user = True  # Now wait for user to respond

    async def wait_for_poll_end(self, poll_id: str, timeout: int):
        await asyncio.sleep(timeout)
        if self.active_poll and self.active_poll["id"] == poll_id:
            await self.finalize_poll()

    async def handle_poll_response(self, identity: str, answer: str):
        if not self.active_poll:
            return

        self.active_poll["responses"][identity] = answer
        logger.info(f"Received poll response from {identity}: {answer}")

        # Check if all participants have answered
        current_participants = len(self.room.remote_participants)
        if (
            len(self.active_poll["responses"]) >= current_participants
            and current_participants > 0
        ):
            await self.finalize_poll()

    async def finalize_poll(self):
        if not self.active_poll:
            return

        poll = self.active_poll
        self.active_poll = None  # Clear active poll

        # Tally results
        results = {}
        for answer in poll["responses"].values():
            results[answer] = results.get(answer, 0) + 1

        result_summary = f"Poll results for '{poll['question']}': {results}"
        logger.info(result_summary)

        # Add to chat context
        self.chat_ctx.add_message(role="system", content=result_summary)

        # Broadcast results to UI
        await self.room.local_participant.send_text(
            text=json.dumps({"type": "poll_ended", "results": results}),
            topic="coordinator_poll_end",
        )

        # Trigger coordinator to react to results immediately
        self.waiting_for_user = False
        self.last_activity = 0  # Force immediate trigger

    @function_tool(description="Send a private message to a specific user")
    async def send_private_message(self, identity: str, message: str):
        """Send a private message to a specific participant."""
        logger.info(f"Sending private message to {identity}: {message}")
        # We can use RPC or send_text with a specific topic/destination if supported
        # For now, we'll use send_text with a convention or assume RPC if we had one
        # But wait, send_text is broadcast. We need RPC for private.
        # Let's assume we use the 'add_message' RPC but directed?
        # Actually, LiveKit send_text goes to everyone unless destination_identities is set.
        # Python SDK Room.local_participant.send_text supports destination_identities.

        await self.room.local_participant.send_text(
            text=json.dumps({"type": "private_message", "message": message}),
            topic="coordinator_private",
            destination_identities=[identity],
        )
        return f"Message sent to {identity}"

    @function_tool(description="Broadcast a message to all users")
    async def broadcast_message(self, message: str):
        """Broadcast a message to all participants."""
        logger.info(f"Broadcasting message: {message}")
        await self.room.local_participant.send_text(
            text=json.dumps({"type": "broadcast", "message": message}),
            topic="coordinator_broadcast",
        )
        return "Message broadcasted"

    @function_tool(description="Create a poll for users to vote on")
    async def create_poll(self, question: str, options: list[str], timeout: int = 30):
        """Create a poll with a question and a list of options. Timeout in seconds (default 30)."""
        logger.info(f"Creating poll: {question} - {options} (timeout: {timeout}s)")

        poll_id = str(uuid.uuid4())
        self.active_poll = {
            "id": poll_id,
            "question": question,
            "options": options,
            "responses": {},
            "participants": [
                p.identity for p in self.room.remote_participants.values()
            ],
            "end_time": time.time() + timeout,
        }

        await self.room.local_participant.send_text(
            text=json.dumps(
                {
                    "type": "poll",
                    "id": poll_id,
                    "question": question,
                    "options": options,
                    "timeout": timeout,
                }
            ),
            topic="coordinator_poll",
        )

        # Start a background task to finalize the poll after timeout
        asyncio.create_task(self.wait_for_poll_end(poll_id, timeout))

        return f"Poll created with ID {poll_id}. Waiting for responses."

    @function_tool(description="Show a popup message to all users or a specific user")
    async def show_popup(self, message: str, recipient_identity: str = None):
        """Show a popup. If recipient_identity is None, shows to all."""
        logger.info(f"Showing popup to {recipient_identity or 'all'}: {message}")
        destinations = [recipient_identity] if recipient_identity else []
        await self.room.local_participant.send_text(
            text=json.dumps({"type": "popup", "message": message}),
            topic="coordinator_popup",
            destination_identities=destinations,
        )
        return "Popup shown"

    @function_tool(description="Start an interactive game")
    async def start_game(self, description: str):
        """Start an interactive game with a description."""
        logger.info(f"Starting game: {description}")
        await self.room.local_participant.send_text(
            text=json.dumps({"type": "game", "description": description}),
            topic="coordinator_game",
        )
        return "Game started"

    @function_tool(description="Generate an image and show it to everyone")
    async def generate_image(self, prompt: str, subtitle: str):
        """Generate an image based on a prompt and show it with a subtitle."""
        logger.info(f"Generating image for: {prompt}")
        # Placeholder for actual generation
        # Using a reliable placeholder service
        encoded_prompt = utils.http.url_encode(prompt)
        image_url = f"https://placehold.co/600x400?text={encoded_prompt}"

        await self.room.local_participant.send_text(
            text=json.dumps({"type": "image", "url": image_url, "subtitle": subtitle}),
            topic="coordinator_image",
        )
        return "Image generated and shown"


class MultiUserTranscriber:
    def __init__(self, ctx: JobContext):
        self.ctx = ctx
        self._sessions: dict[str, AgentSession] = {}
        self._chat_contexts: dict[str, llm.ChatContext] = {}
        self._tasks: set[asyncio.Task] = set()
        self.coordinator = Coordinator(ctx, self._sessions, self._chat_contexts)

    def start(self):
        self.ctx.room.on("participant_connected", self.on_participant_connected)
        self.ctx.room.on("participant_disconnected", self.on_participant_disconnected)
        self.coordinator.start()

    def register_rpc_methods(self):
        """Register RPC methods after room connection."""
        self.ctx.room.local_participant.register_rpc_method(
            "summarize_meeting", self.handle_summarize_request
        )
        self.ctx.room.local_participant.register_rpc_method(
            "add_message", self.handle_add_message
        )
        self.ctx.room.local_participant.register_rpc_method(
            "submit_poll_response", self.handle_poll_response
        )
        logger.info(
            "Registered RPC methods: summarize_meeting, add_message, submit_poll_response"
        )

    def get_chat_context(self, participant_identity: str) -> llm.ChatContext | None:
        """Get the chat context for a specific participant."""
        return self._chat_contexts.get(participant_identity)

    def get_all_chat_contexts(self) -> dict[str, llm.ChatContext]:
        """Get all chat contexts for all participants."""
        return self._chat_contexts.copy()

    async def handle_summarize_request(self, data: rtc.RpcInvocationData) -> str:
        """Handle RPC request to summarize the meeting."""
        try:
            logger.info(f"Received summarization request from {data.caller_identity}")

            # Get all messages sorted by timestamp
            all_messages = get_combined_chat_context(self._chat_contexts)

            if len(all_messages.items) == 0:
                return "No conversation has occurred yet."
            summary_context = llm.ChatContext()
            summary_context.add_message(
                role="system",
                content=(
                    "Compress older chat history into a short, faithful summary.\n"
                    "Focus on user goals, constraints, decisions, key facts/preferences/entities, and pending tasks.\n"
                    "Exclude chit-chat and greetings. Be concise."
                ),
            )
            import json

            all_messages = all_messages.to_dict().get("items", [])

            transcript = "\n\n".join([json.dumps(item) for item in all_messages])
            # Format messages as a conversation transcript
            logger.info(f"Transcript: {transcript}")
            # Use OpenAI to generate summary
            llm_instance = openai.LLM(model="gpt-4o-mini")

            # Create a chat context for the summary request
            summary_context.add_message(
                role="user",
                content=f"""
Conversation:
{transcript}

                """,
            )

            # Generate summary
            summary_stream = llm_instance.chat(chat_ctx=summary_context)
            summary_text = ""

            async for chunk in summary_stream:
                if chunk.delta and chunk.delta.content:
                    summary_text += chunk.delta.content

            logger.info(f"Summary generated successfully for {data.caller_identity}")
            return summary_text

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            return f"Error generating summary: {str(e)}"

    async def handle_add_message(self, data: rtc.RpcInvocationData) -> str:
        """Handle RPC request to add a text message to chat context."""
        try:
            import json

            payload = json.loads(data.payload) if data.payload else {}
            message_text = payload.get("message", "")
            participant_identity = data.caller_identity

            if not message_text:
                return json.dumps({"error": "Message is required"})

            # Get or create chat context for this participant
            if participant_identity not in self._chat_contexts:
                self._chat_contexts[participant_identity] = llm.ChatContext()
                logger.info(f"Created new chat context for {participant_identity}")

            chat_context = self._chat_contexts[participant_identity]

            # Add message to context
            chat_context.add_message(
                role="user",
                content=f"Participant Name: {participant_identity}\nMessage: ```{message_text}```",
            )
            await self.ctx.room.local_participant.send_text(
                text=json.dumps(
                    {
                        "speaker": participant_identity,
                        "text": message_text,
                        "timestamp": int(time.time() * 1000),
                    }
                ),
                topic="transcription",
            )

            # Notify Coordinator of activity
            self.coordinator.on_activity(participant_identity, message_text)

            logger.info(f"[{participant_identity}] Added text message: {message_text}")
            logger.info(
                f"[{participant_identity}] Chat context now has {len(chat_context.items)} messages"
            )

            return json.dumps({"success": True})
        except Exception as e:
            logger.error(f"Error adding message: {e}")
            return json.dumps({"error": str(e)})

    async def handle_poll_response(self, data: rtc.RpcInvocationData) -> str:
        """Handle RPC request to submit a poll response."""
        try:
            import json

            payload = json.loads(data.payload) if data.payload else {}
            answer = payload.get("answer")

            if not answer:
                return json.dumps({"error": "Answer is required"})

            await self.coordinator.handle_poll_response(data.caller_identity, answer)
            return json.dumps({"success": True})
        except Exception as e:
            logger.error(f"Error submitting poll response: {e}")
            return json.dumps({"error": str(e)})

    async def aclose(self):
        await self.coordinator.stop()
        await utils.aio.cancel_and_wait(*self._tasks)

        await asyncio.gather(
            *[self._close_session(session) for session in self._sessions.values()]
        )

        self.ctx.room.off("participant_connected", self.on_participant_connected)
        self.ctx.room.off("participant_disconnected", self.on_participant_disconnected)

    def on_participant_connected(self, participant: rtc.RemoteParticipant):
        if participant.identity in self._sessions:
            return

        logger.info(f"starting session for {participant.identity}")
        task = asyncio.create_task(self._start_session(participant))
        self._tasks.add(task)

        def on_task_done(task: asyncio.Task):
            try:
                self._sessions[participant.identity] = task.result()
            finally:
                self._tasks.discard(task)

        task.add_done_callback(on_task_done)

    def on_participant_disconnected(self, participant: rtc.RemoteParticipant):
        if (session := self._sessions.pop(participant.identity, None)) is None:
            return

        # Clean up chat context for disconnected participant
        chat_context = self._chat_contexts.pop(participant.identity, None)
        if chat_context:
            logger.info(
                f"cleaned up chat context for {participant.identity} ({len(chat_context.items)} messages)"
            )

        logger.info(f"closing session for {participant.identity}")
        task = asyncio.create_task(self._close_session(session))
        self._tasks.add(task)
        task.add_done_callback(lambda _: self._tasks.discard(task))

    async def _start_session(self, participant: rtc.RemoteParticipant) -> AgentSession:
        if participant.identity in self._sessions:
            return self._sessions[participant.identity]

        # Initialize chat context for this participant
        chat_context = llm.ChatContext()
        self._chat_contexts[participant.identity] = chat_context
        logger.info(f"initialized chat context for {participant.identity}")

        session = AgentSession(
            vad=self.ctx.proc.userdata["vad"],
        )
        await session.start(
            agent=Transcriber(
                participant_identity=participant.identity,
                chat_context=chat_context,
                room=self.ctx.room,
                coordinator=self.coordinator,
            ),
            room=self.ctx.room,
            room_options=room_io.RoomOptions(
                audio_input=True,
                text_output=True,
                audio_output=True,
                participant_identity=participant.identity,
                # text input is not supported for multiple room participants
                # if needed, register the text stream handler by yourself
                # and route the text to different sessions based on the participant identity
                text_input=False,
            ),
        )
        return session

    async def _close_session(self, sess: AgentSession) -> None:
        await sess.drain()
        await sess.aclose()


server = AgentServer()


@server.rtc_session(agent_name="transcriber-agent")
async def entrypoint(ctx: JobContext):
    transcriber = MultiUserTranscriber(ctx)
    await ctx.connect()
    await ctx.wait_for_participant()
    transcriber.start()

    # Register RPC methods after connection
    transcriber.register_rpc_methods()

    for participant in ctx.room.remote_participants.values():
        # handle all existing participants
        transcriber.on_participant_connected(participant)

    async def cleanup():
        await transcriber.aclose()

    ctx.add_shutdown_callback(cleanup)


def prewarm(proc: JobProcess):
    proc.userdata["vad"] = silero.VAD.load()


server.setup_fnc = prewarm

if __name__ == "__main__":
    cli.run_app(server)
