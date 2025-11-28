<script lang="ts">
  import { Participant } from "livekit-client";
  import ParticipantTile from "./ParticipantTile.svelte";

  let { participants, transcriptions, liveTranscripts } = $props<{
    participants: Participant[];
    transcriptions: Map<string, string>;
    liveTranscripts: Record<string, string>;
  }>();
</script>

<div
  class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 p-4 auto-rows-fr"
>
  {#each participants as p (p.identity)}
    <ParticipantTile
      participant={p}
      transcription={liveTranscripts[p.identity]}
    />
  {/each}
</div>
