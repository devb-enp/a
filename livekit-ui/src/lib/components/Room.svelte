<script lang="ts">
  import {
    Room,
    RoomEvent,
    Participant,
    RemoteParticipant,
    LocalParticipant,
    Track,
    type TranscriptionSegment,
  } from "livekit-client";
  import { onMount, onDestroy } from "svelte";
  import VideoGrid from "./VideoGrid.svelte";
  import ChatSidebar from "./ChatSidebar.svelte";
  import ParticipantTile from "./ParticipantTile.svelte";

  let { url, token } = $props<{ url: string; token: string }>();

  let room: Room | undefined = $state();
  let participants: Participant[] = $state([]);
  let transcriptions = $state(new Map<string, string>());
  let chatMessages: { speaker: string; text: string; timestamp: number }[] =
    $state([]);
  let error = $state("");
  let isSummarizing = $state(false);
  let summary = $state("");
  let showSummary = $state(false);
  let agentDispatched = $state(false);
  let isDispatchingAgent = $state(false);
  let isMicEnabled = $state(true);
  let liveTranscripts = $state<Record<string, string>>({});

  // Coordinator State
  let activePoll = $state<{
    id: string;
    question: string;
    options: string[];
    timeout: number;
    endTime: number;
  } | null>(null);
  let activePopup = $state<{ message: string } | null>(null);
  let activeImage = $state<{ url: string; subtitle: string } | null>(null);
  let activeGame = $state<{ description: string } | null>(null);

  let pollTimer = $state(0);
  let hasVoted = $state(false);

  let agentParticipant = $derived(
    participants.find(
      (p) =>
        p.identity.toLowerCase().includes("agent") ||
        p.identity.startsWith("AG_")
    )
  );

  let audienceParticipants = $derived(
    participants.filter((p) => p !== agentParticipant)
  );

  function updateParticipants() {
    if (!room) return;
    const remotes = Array.from(room.remoteParticipants.values());
    participants = [room.localParticipant, ...remotes];
  }

  // This function is no longer used for TranscriptionReceived event,
  // but might be kept if other parts of the app still use it or for future use.
  // The new onTranscriptionReceived handles the live transcripts.
  function handleTranscription(
    segments: TranscriptionSegment[],
    participant?: Participant
  ) {
    if (!participant) return;

    for (const segment of segments) {
      if (segment.final) {
        // Final segment: add to chat and clear interim
        chatMessages = [
          ...chatMessages,
          {
            speaker:
              room.localParticipant.identity === participant.identity
                ? "You"
                : participant.identity,
            text: segment.text,
            timestamp: Date.now(),
          },
        ];
        transcriptions.set(participant.identity, "");
      } else {
        // Interim segment: update overlay
        transcriptions.set(participant.identity, segment.text);
      }
    }
    // Force reactivity for Map if needed (Svelte 5 Map proxies should handle set, but reassigning map is safer if unsure)
    // transcriptions = transcriptions; // Not needed if $state(new Map()) works as expected in Svelte 5
  }

  // New handler for live transcription updates
  const onTranscriptionReceived = (
    participant: Participant,
    track: Track,
    segment: TranscriptionSegment
  ) => {
    // TODO: For later
    if (!segment.final) {
      // Update live transcript
      liveTranscripts[participant.identity] = segment.text;
    } else {
      // Final segment received, but we wait for RPC to add to chat
      // We can clear live transcript here or wait for RPC
      // Requirement: "erased when the transcript is added to the chat sidebar from rpc call"
      // So we do nothing here for final segments regarding chatMessages
    }
  };

  async function requestSummary() {
    if (!room) return;

    isSummarizing = true;
    summary = "";
    error = "";

    try {
      console.log("Requesting meeting summary...");

      // Find the agent participant (typically has "agent" in identity or is the only remote participant)
      const agentParticipant =
        Array.from(room.remoteParticipants.values()).find(
          (p) =>
            p.identity.toLowerCase().includes("agent") ||
            p.identity.startsWith("AG_")
        ) || Array.from(room.remoteParticipants.values())[0];

      if (!agentParticipant) {
        throw new Error("No agent found in the room");
      }

      console.log("Calling RPC on agent:", agentParticipant.identity);

      const response = await room.localParticipant.performRpc({
        destinationIdentity: agentParticipant.identity,
        method: "summarize_meeting",
        payload: "",
      });

      console.log("Summary received:", response);
      summary = response;
      showSummary = true;
    } catch (e) {
      console.error("Failed to get summary:", e);
      error = e instanceof Error ? e.message : String(e);
      summary = "Failed to generate summary. Please try again.";
      showSummary = true;
    } finally {
      isSummarizing = false;
    }
  }

  async function toggleMic() {
    if (!room) return;
    isMicEnabled = !isMicEnabled;
    await room.localParticipant.setMicrophoneEnabled(isMicEnabled);
  }

  async function submitPollVote(option: string) {
    if (!room || !activePoll || hasVoted) return;

    try {
      hasVoted = true;
      await room.localParticipant.performRpc({
        destinationIdentity: "agent", // Assuming agent is the destination
        method: "submit_poll_response",
        payload: JSON.stringify({ pollId: activePoll.id, answer: option }),
      });
    } catch (e) {
      console.error("Error submitting vote:", e);
      hasVoted = false; // Allow retry on error
    }
  }

  async function dispatchAgent() {
    if (!room || agentDispatched) return;

    isDispatchingAgent = true;
    error = "";

    try {
      console.log("Dispatching agent to room:", room.name);

      const response = await fetch("/api/dispatch-agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          roomName: room.name,
          agentName: "transcriber-agent",
        }),
      });

      const data = await response.json();

      if (data.success) {
        agentDispatched = true;
        console.log("Agent dispatched successfully");
      } else {
        throw new Error(data.error || "Failed to dispatch agent");
      }
    } catch (e) {
      console.error("Failed to dispatch agent:", e);
      error = e instanceof Error ? e.message : String(e);
    } finally {
      isDispatchingAgent = false;
    }
  }

  onMount(() => {
    const connectToRoom = async () => {
      console.log(
        "Room component mounting. URL:",
        url,
        "Token length:",
        token?.length
      );
      try {
        if (!url || !token) {
          throw new Error("Missing URL or Token");
        }

        room = new Room({
          adaptiveStream: true,
          dynacast: true,
        });

        room.on(RoomEvent.ParticipantConnected, updateParticipants);
        room.on(RoomEvent.ParticipantDisconnected, updateParticipants);
        room.on(RoomEvent.TranscriptionReceived, onTranscriptionReceived);

        // Register RPC handler for finalized transcripts
        room.localParticipant.registerRpcMethod(
          "transcript_committed",
          async (data) => {
            try {
              const { speaker, text, timestamp } = JSON.parse(data.payload);

              // Add to chat sidebar
              chatMessages = [
                ...chatMessages,
                {
                  speaker:
                    speaker === room.localParticipant.identity
                      ? "You"
                      : speaker,
                  text,
                  timestamp,
                },
              ];

              // Clear live transcript for this speaker
              liveTranscripts[speaker] = "";

              return JSON.stringify({ received: true });
            } catch (e) {
              console.error("Error processing transcript RPC:", e);
              return JSON.stringify({ error: String(e) });
            }
          }
        );

        console.log("Connecting to LiveKit room...");
        await room.connect(url, token);
        console.log("Connected to room:", room.name);

        // Publish camera and microphone
        console.log("Enabling camera and microphone...");
        await room.localParticipant.enableCameraAndMicrophone();
        console.log("Camera and microphone enabled");

        updateParticipants();
        room.registerTextStreamHandler(
          "transcription",
          async (reader, participantInfo) => {
            const transcription = JSON.parse(await reader.readAll());
            console.log("Received transcription:", transcription);
            chatMessages = [...chatMessages, transcription];
          }
        );

        // Coordinator Handlers
        room.registerTextStreamHandler(
          "coordinator_broadcast",
          async (reader) => {
            const data = JSON.parse(await reader.readAll());
            console.log("Received coordinator_broadcast:", data);
            chatMessages = [
              ...chatMessages,
              {
                speaker: "Dungeon Master",
                text: data.message,
                timestamp: Date.now(),
              },
            ];
          }
        );

        room.registerTextStreamHandler("coordinator_poll", async (reader) => {
          const data = JSON.parse(await reader.readAll());
          console.log("Received coordinator_poll:", data);
          activePoll = {
            ...data,
            endTime: Date.now() + data.timeout * 1000,
          };
          hasVoted = false;

          // Start timer
          const updateTimer = () => {
            if (!activePoll) return;
            const remaining = Math.ceil(
              (activePoll.endTime - Date.now()) / 1000
            );
            pollTimer = remaining > 0 ? remaining : 0;

            if (remaining > 0) {
              requestAnimationFrame(updateTimer);
            } else {
              // Poll ended locally
            }
          };
          updateTimer();
        });

        room.registerTextStreamHandler(
          "coordinator_poll_end",
          async (reader) => {
            console.log("Received coordinator_poll_end");
            // Optional: Show results briefly or just clear
            activePoll = null;
          }
        );

        room.registerTextStreamHandler("coordinator_popup", async (reader) => {
          const data = JSON.parse(await reader.readAll());
          console.log("Received coordinator_popup:", data);
          activePopup = data;
          setTimeout(() => (activePopup = null), 5000); // Auto-hide after 5s
        });

        room.registerTextStreamHandler("coordinator_image", async (reader) => {
          const data = JSON.parse(await reader.readAll());
          console.log("Received coordinator_image:", data);
          activeImage = data;
        });

        room.registerTextStreamHandler("coordinator_game", async (reader) => {
          const data = JSON.parse(await reader.readAll());
          console.log("Received coordinator_game:", data);
          activeGame = data;
        });

        room.registerTextStreamHandler(
          "coordinator_private",
          async (reader) => {
            const data = JSON.parse(await reader.readAll());
            console.log("Received coordinator_private:", data);
            chatMessages = [
              ...chatMessages,
              {
                speaker: "DM (Private)",
                text: data.message,
                timestamp: Date.now(),
              },
            ];
          }
        );
      } catch (e) {
        console.error("Failed to connect", e);
        error = e instanceof Error ? e.message : String(e);
      }
    };

    connectToRoom();

    return () => {
      console.log("Disconnecting from room");
      room?.disconnect();
    };
  });
</script>

<div class="flex h-screen w-full bg-black text-white overflow-hidden">
  {#if error}
    <div
      class="absolute inset-0 z-50 flex items-center justify-center bg-black/80"
    >
      <div
        class="bg-red-900/50 p-8 rounded-xl border border-red-500 text-center"
      >
        <h3 class="text-xl font-bold mb-2">Connection Error</h3>
        <p>{error}</p>
        <button
          class="mt-4 px-4 py-2 bg-red-600 rounded hover:bg-red-500"
          onclick={() => window.location.reload()}
        >
          Retry
        </button>
      </div>
    </div>
  {/if}

  <div class="flex-1 flex flex-col min-w-0">
    <header
      class="h-14 border-b border-gray-800 flex items-center px-6 justify-between bg-gray-900/50 backdrop-blur"
    >
      <div class="flex items-center gap-3">
        <button
          class="p-2 rounded-full transition-colors {isMicEnabled
            ? 'bg-gray-800 hover:bg-gray-700 text-white'
            : 'bg-red-500/20 hover:bg-red-500/30 text-red-400'}"
          onclick={toggleMic}
          title={isMicEnabled ? "Mute Microphone" : "Unmute Microphone"}
        >
          {#if isMicEnabled}
            <!-- Mic On Icon -->
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
              <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
              <line x1="12" y1="19" x2="12" y2="23" />
              <line x1="8" y1="23" x2="16" y2="23" />
            </svg>
          {:else}
            <!-- Mic Off Icon -->
            <svg
              xmlns="http://www.w3.org/2000/svg"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              stroke-linecap="round"
              stroke-linejoin="round"
            >
              <line x1="1" y1="1" x2="23" y2="23" />
              <path d="M9 9v3a3 3 0 0 0 5.12 2.12" />
              <path d="M15 9.34V4a3 3 0 0 0-5.94-.6" />
              <path d="M17 16.95A7 7 0 0 1 5 12v-2" />
              <line x1="12" y1="19" x2="12" y2="23" />
              <line x1="8" y1="23" x2="16" y2="23" />
            </svg>
          {/if}
        </button>

        <div class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
        <span class="text-sm font-medium text-gray-400">Live Session</span>
      </div>
      <h1 class="font-bold text-lg tracking-tight">
        LiveKit <span class="text-blue-400">Transcriber</span>
      </h1>
      <div class="text-sm text-gray-400">
        Room: <span class="text-white font-mono"
          >{room?.name || "Connecting..."}</span
        >
      </div>
      <div class="flex items-center gap-2">
        <button
          onclick={dispatchAgent}
          disabled={isDispatchingAgent || agentDispatched || !room}
          class="px-4 py-2 bg-green-600 hover:bg-green-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-all flex items-center gap-2"
        >
          {#if isDispatchingAgent}
            <svg
              class="animate-spin h-4 w-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                class="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                stroke-width="4"
              ></circle>
              <path
                class="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
            Dispatching...
          {:else if agentDispatched}
            ✓ Agent Active
          {:else}
            🤖 Add AI Agent
          {/if}
        </button>
        <button
          onclick={requestSummary}
          disabled={isSummarizing || !room}
          class="px-4 py-2 bg-purple-600 hover:bg-purple-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-all flex items-center gap-2"
        >
          {#if isSummarizing}
            <svg
              class="animate-spin h-4 w-4"
              xmlns="http://www.w3.org/2000/svg"
              fill="none"
              viewBox="0 0 24 24"
            >
              <circle
                class="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                stroke-width="4"
              ></circle>
              <path
                class="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              ></path>
            </svg>
            Summarizing...
          {:else}
            📝 Summarize Meeting
          {/if}
        </button>
      </div>
    </header>

    <main class="flex-1 overflow-y-auto p-4 flex flex-col gap-8 bg-gray-950">
      <!-- Stage Area -->
      <div
        class="flex-none h-[40vh] flex justify-center items-end pb-8 border-b border-gray-800 relative"
      >
        <div
          class="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-purple-900/10 to-transparent pointer-events-none"
        ></div>

        <!-- Agent Spot -->
        <div class="relative w-full max-w-2xl aspect-video">
          {#if agentParticipant}
            <ParticipantTile
              participant={agentParticipant}
              transcription={liveTranscripts[agentParticipant.identity]}
              avatarUrl="https://api.dicebear.com/7.x/avataaars/svg?seed=i"
            />
          {:else}
            <!-- Empty Stage State -->
            <div
              class="w-full h-full border-2 border-dashed border-gray-800 rounded-2xl flex flex-col items-center justify-center text-gray-600 bg-gray-900/50"
            >
              <div class="text-4xl mb-4">🎤</div>
              <div class="text-xl font-medium">Stage Empty</div>
              <div class="text-sm mt-2">Waiting for Coordinator...</div>
            </div>
          {/if}
        </div>
      </div>

      <!-- Audience Area -->
      <div class="flex-1 px-8">
        <div
          class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8 max-w-6xl mx-auto"
        >
          {#each audienceParticipants as p (p.identity)}
            <ParticipantTile
              participant={p}
              transcription={liveTranscripts[p.identity]}
            />
          {/each}

          <!-- Empty Seats (Optional visual filler) -->
          {#each Array(Math.max(0, 6 - audienceParticipants.length)) as _}
            <div
              class="aspect-video bg-gray-900/30 rounded-xl border border-gray-800/50 flex items-center justify-center"
            >
              <div class="text-gray-700 font-medium">Empty Seat</div>
            </div>
          {/each}
        </div>
      </div>
    </main>

    <!-- Coordinator Overlays -->

    <!-- Poll Overlay -->
    {#if activePoll}
      <div
        class="fixed inset-0 bg-black/80 z-50 flex items-center justify-center p-4"
      >
        <div
          class="bg-gray-900 border border-purple-500/30 rounded-2xl p-6 max-w-md w-full shadow-2xl"
        >
          <div class="flex justify-between items-center mb-4">
            <h3 class="text-xl font-bold text-white">{activePoll.question}</h3>
            <div class="text-purple-400 font-mono font-bold text-lg">
              {pollTimer}s
            </div>
          </div>

          <div class="space-y-3">
            {#each activePoll.options as option}
              <button
                class="w-full p-3 text-left bg-gray-800 hover:bg-purple-900/30 border border-gray-700 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed {hasVoted
                  ? 'opacity-50'
                  : ''}"
                onclick={() => submitPollVote(option)}
                disabled={hasVoted || pollTimer === 0}
              >
                {option}
              </button>
            {/each}
          </div>

          {#if hasVoted}
            <p class="text-center text-green-400 mt-4 text-sm animate-pulse">
              Vote Submitted!
            </p>
          {/if}

          <button
            class="mt-4 text-sm text-gray-500 hover:text-gray-300 w-full text-center"
            onclick={() => (activePoll = null)}
          >
            Dismiss (Vote in background)
          </button>
        </div>
      </div>
    {/if}

    <!-- Popup Toast -->
    {#if activePopup}
      <div
        class="fixed top-20 left-1/2 -translate-x-1/2 z-50 animate-bounce-slight"
      >
        <div
          class="bg-purple-900/90 backdrop-blur text-white px-6 py-3 rounded-full shadow-xl border border-purple-500/50 flex items-center gap-3"
        >
          <span class="text-2xl">📜</span>
          <span class="font-medium">{activePopup.message}</span>
        </div>
      </div>
    {/if}

    <!-- Image Modal -->
    {#if activeImage}
      <div
        class="fixed inset-0 bg-black/90 z-50 flex items-center justify-center p-8"
        onclick={() => (activeImage = null)}
      >
        <div class="max-w-4xl w-full flex flex-col items-center gap-4">
          <img
            src={activeImage.url}
            alt="Generated Scene"
            class="rounded-lg shadow-2xl border border-gray-800 max-h-[80vh] object-contain"
          />
          <p
            class="text-xl text-gray-300 font-serif italic text-center max-w-2xl"
          >
            "{activeImage.subtitle}"
          </p>
          <div class="text-sm text-gray-500 mt-2">Click anywhere to close</div>
        </div>
      </div>
    {/if}
  </div>

  <ChatSidebar messages={chatMessages} {room} {agentDispatched} />

  <!-- Summary Modal -->
  {#if showSummary}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onclick={() => (showSummary = false)}
    >
      <div
        class="bg-gray-900 border border-gray-700 rounded-2xl p-6 max-w-2xl w-full mx-4 shadow-2xl"
        onclick={(e) => e.stopPropagation()}
      >
        <div class="flex items-center justify-between mb-4">
          <h2 class="text-2xl font-bold text-white flex items-center gap-2">
            📝 Meeting Summary
          </h2>
          <button
            onclick={() => (showSummary = false)}
            class="text-gray-400 hover:text-white transition-colors"
          >
            <svg
              class="w-6 h-6"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M6 18L18 6M6 6l12 12"
              ></path>
            </svg>
          </button>
        </div>

        <div
          class="bg-gray-950 border border-gray-800 rounded-lg p-4 max-h-96 overflow-y-auto"
        >
          <p class="text-gray-300 whitespace-pre-wrap leading-relaxed">
            {summary}
          </p>
        </div>

        <div class="mt-4 flex justify-end">
          <button
            onclick={() => (showSummary = false)}
            class="px-6 py-2 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-lg transition-all"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>
