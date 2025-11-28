<script lang="ts">
  import { page } from "$app/stores";
  import Room from "$lib/components/Room.svelte";
  import { onMount } from "svelte";

  let roomId = $derived($page.params.roomId);
  let token = $state("");
  let url = $state(""); // Will be fetched or set from env in real app, here we assume we get it or hardcode for now if env not exposed to client
  // In a real app, the URL should probably be passed from the server load function or public env
  // For this demo, we'll fetch it from the token endpoint or just assume the user knows it/it's in the token?
  // Actually, the Room component needs the URL. Let's fetch the URL from the server as well or expose it via public env.

  // Better approach: The token endpoint returns the token. The client needs the LiveKit URL.
  // We can expose PUBLIC_LIVEKIT_URL in .env and import it here.
  // But since I can't easily add PUBLIC_ env vars without restarting/config, I'll return the URL from the API too.

  let error = $state("");
  let username = $state("");
  let isJoining = $state(false);

  async function joinRoom() {
    if (!username) return;
    isJoining = true;
    console.log("Joining room:", roomId, "as", username);
    try {
      const res = await fetch(
        `/api/token?room=${roomId}&username=${encodeURIComponent(username)}`
      );
      const data = await res.json();
      console.log("Token API response:", data);
      if (data.error) throw new Error(data.error);

      token = data.token;
      // For now, we need the LiveKit URL.
      // I will update the API to return it or just hardcode the one from .env.example for testing if not returned.
      // Let's update the API to return the URL as well.
      if (data.url) {
        url = data.url;
      } else {
        // Fallback or error
        throw new Error("Server didn't return LiveKit URL");
      }
      console.log(
        "Token and URL received. Token length:",
        token.length,
        "URL:",
        url
      );
    } catch (e) {
      console.error("Join room error:", e);
      error = e instanceof Error ? e.message : String(e);
      isJoining = false;
    }
  }
</script>

{#if !token}
  <div
    class="min-h-screen bg-black text-white flex items-center justify-center p-4"
  >
    <div class="w-full max-w-md space-y-8">
      <div class="text-center">
        <h1 class="text-3xl font-bold mb-2">Join Meeting</h1>
        <p class="text-gray-400">
          Room: <span class="text-blue-400 font-mono">{roomId}</span>
        </p>
      </div>

      <div
        class="bg-gray-900 border border-gray-800 p-8 rounded-2xl shadow-2xl space-y-6"
      >
        <div class="space-y-2">
          <label for="username" class="text-sm font-medium text-gray-300"
            >Your Name</label
          >
          <input
            id="username"
            type="text"
            bind:value={username}
            placeholder="Enter your name"
            class="w-full bg-gray-950 border border-gray-800 rounded-lg px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all"
            onkeydown={(e) => e.key === "Enter" && joinRoom()}
          />
        </div>

        {#if error}
          <div
            class="p-3 bg-red-900/50 border border-red-500/50 rounded-lg text-red-200 text-sm"
          >
            {error}
          </div>
        {/if}

        <button
          onclick={joinRoom}
          disabled={!username || isJoining}
          class="w-full bg-blue-600 hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold py-3 rounded-lg transition-all"
        >
          {isJoining ? "Joining..." : "Join Room"}
        </button>
      </div>
    </div>
  </div>
{:else}
  <Room {url} {token} />
{/if}
