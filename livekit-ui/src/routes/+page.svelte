<script lang="ts">
  import { goto } from "$app/navigation";

  let roomCode = $state("");

  function createMeeting() {
    console.log("Create meeting clicked");
    const randomId = Math.random().toString(36).substring(2, 7);
    console.log("Navigating to", `/room/${randomId}`);
    goto(`/room/${randomId}`).catch((e) =>
      console.error("Navigation error:", e)
    );
  }

  function joinMeeting() {
    console.log("Join meeting clicked", roomCode);
    if (roomCode) {
      goto(`/room/${roomCode}`).catch((e) =>
        console.error("Navigation error:", e)
      );
    }
  }
</script>

<svelte:head>
  <title>LiveKit Transcriber</title>
</svelte:head>

<div
  class="min-h-screen bg-black text-white flex items-center justify-center p-4 relative overflow-hidden"
>
  <!-- Background decoration -->
  <div
    class="absolute top-0 left-0 w-full h-full overflow-hidden z-0 pointer-events-none"
  >
    <div
      class="absolute top-[-10%] left-[-10%] w-[40%] h-[40%] bg-blue-600/20 rounded-full blur-[100px]"
    ></div>
    <div
      class="absolute bottom-[-10%] right-[-10%] w-[40%] h-[40%] bg-purple-600/20 rounded-full blur-[100px]"
    ></div>
  </div>

  <div class="w-full max-w-md space-y-12 relative z-10">
    <div class="text-center space-y-4">
      <div
        class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-purple-600 mb-4 shadow-lg shadow-blue-500/20"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          class="w-8 h-8 text-white"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            stroke-linecap="round"
            stroke-linejoin="round"
            stroke-width="2"
            d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z"
          />
        </svg>
      </div>
      <h1
        class="text-5xl font-bold tracking-tighter bg-gradient-to-r from-white via-blue-100 to-blue-200 bg-clip-text text-transparent"
      >
        LiveKit Transcriber
      </h1>
      <p class="text-gray-400 text-lg">
        Real-time transcription for your video calls
      </p>
    </div>

    <div class="space-y-6">
      <button
        type="button"
        onclick={createMeeting}
        class="w-full group relative overflow-hidden bg-white text-black font-bold py-4 rounded-xl transition-all transform hover:scale-[1.02] active:scale-[0.98] shadow-xl hover:shadow-2xl hover:shadow-white/10"
      >
        <div
          class="absolute inset-0 bg-gradient-to-r from-blue-100 to-purple-100 opacity-0 group-hover:opacity-100 transition-opacity"
        ></div>
        <span class="relative flex items-center justify-center gap-2">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            class="w-5 h-5"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              stroke-linecap="round"
              stroke-linejoin="round"
              stroke-width="2"
              d="M12 4v16m8-8H4"
            />
          </svg>
          New Meeting
        </span>
      </button>

      <div class="relative">
        <div class="absolute inset-0 flex items-center">
          <div class="w-full border-t border-gray-800"></div>
        </div>
        <div class="relative flex justify-center text-sm">
          <span class="px-4 bg-black text-gray-500">or join existing</span>
        </div>
      </div>

      <div class="flex gap-2">
        <input
          type="text"
          bind:value={roomCode}
          placeholder="Enter room code"
          class="flex-1 bg-gray-900/50 border border-gray-800 rounded-xl px-4 py-3 text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all placeholder-gray-600"
        />
        <button
          type="button"
          onclick={joinMeeting}
          disabled={!roomCode}
          class="bg-gray-800 hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold px-6 rounded-xl transition-all border border-gray-700 hover:border-gray-600"
        >
          Join
        </button>
      </div>
    </div>
  </div>
</div>
