<script lang="ts">
  import type { Room } from "livekit-client";

  let { messages, room, agentDispatched } = $props<{
    messages: { speaker: string; text: string; timestamp: number }[];
    room: Room | undefined;
    agentDispatched: boolean;
  }>();

  let messageInput = $state("");
  let isSending = $state(false);

  function formatTime(timestamp: number) {
    return new Date(timestamp).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  async function sendMessage() {
    if (!messageInput.trim() || !room || !agentDispatched) return;

    const textToSend = messageInput;
    isSending = true;

    try {
      // Find agent participant
      const agentParticipant = Array.from(
        room.remoteParticipants.values()
      ).find(
        (p) =>
          p.identity.toLowerCase().includes("agent") ||
          p.identity.startsWith("AG_")
      );

      if (!agentParticipant) {
        throw new Error("Agent not found");
      }

      // Send message via RPC
      await room.localParticipant.performRpc({
        destinationIdentity: agentParticipant.identity,
        method: "add_message",
        payload: JSON.stringify({ message: textToSend }),
      });

      console.log("Message sent to agent:", textToSend);

      // Notify parent

      // Clear input
      messageInput = "";
    } catch (e) {
      console.error("Failed to send message:", e);
    } finally {
      isSending = false;
    }
  }
</script>

<div class="w-80 h-full bg-gray-900 border-l border-gray-800 flex flex-col">
  <div class="p-4 border-b border-gray-800">
    <h2 class="text-lg font-semibold text-white">Transcript Chat</h2>
  </div>

  <div class="flex-1 overflow-y-auto p-4 space-y-4">
    {#each messages as msg}
      <div class="flex flex-col space-y-1">
        <div class="flex items-baseline justify-between">
          <span class="font-medium text-blue-400 text-sm">{msg.speaker}</span>
          <span class="text-xs text-gray-500">{formatTime(msg.timestamp)}</span>
        </div>
        <p
          class="text-gray-300 text-sm bg-gray-800 p-2 rounded-lg rounded-tl-none"
        >
          {msg.text}
        </p>
      </div>
    {/each}
  </div>

  <!-- Chat Input -->
  <div class="p-4 border-t border-gray-800">
    <form
      onsubmit={(e) => {
        e.preventDefault();
        sendMessage();
      }}
    >
      <div class="flex gap-2">
        <input
          type="text"
          bind:value={messageInput}
          placeholder={agentDispatched
            ? "Type a message..."
            : "Add agent first..."}
          disabled={!agentDispatched || isSending}
          class="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-white text-sm focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none disabled:opacity-50 disabled:cursor-not-allowed"
        />
        <button
          type="submit"
          disabled={!messageInput.trim() || !agentDispatched || isSending}
          class="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold rounded-lg transition-all text-sm"
        >
          {isSending ? "..." : "Send"}
        </button>
      </div>
    </form>
  </div>
</div>
