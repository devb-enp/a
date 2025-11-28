from livekit.agents import (
    JobContext,
    WorkerOptions,
    cli,AgentServer
)
from livekit.plugins import (
    openai,
    silero,
    azure,
    deepgram,
    turn_detector
)
from livekit.plugins.turn_detector.multilingual import MultilingualModel

server = AgentServer()

@server.rtc_session()
async def entrypoint(ctx: JobContext):
    pass
    

if __name__ == "__main__":
    cli.run_app(
       server
    )
