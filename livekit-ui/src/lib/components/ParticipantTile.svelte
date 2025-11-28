<script lang="ts">
  import {
    Participant,
    Track,
    RoomEvent,
    ParticipantEvent,
    TrackPublication,
    RemoteTrackPublication,
    RemoteParticipant,
  } from "livekit-client";
  import { onMount, onDestroy } from "svelte";

  let {
    participant,
    transcription = "",
    avatarUrl,
  } = $props<{
    participant: Participant;
    transcription?: string;
    avatarUrl?: string;
  }>();

  let videoEl: HTMLVideoElement;
  let isVideoEnabled = $state(false);

  function attachTrack() {
    const pub = participant.getTrackPublication(Track.Source.Camera);
    if (pub && pub.isSubscribed && pub.videoTrack) {
      pub.videoTrack.attach(videoEl);
      isVideoEnabled = true;
    } else {
      isVideoEnabled = false;
    }
  }

  function handleTrackSubscribed(track: RemoteTrackPublication) {
    if (track.source === Track.Source.Camera) {
      attachTrack();
    }
  }

  function handleTrackUnsubscribed(track: RemoteTrackPublication) {
    if (track.source === Track.Source.Camera) {
      track.videoTrack?.detach(videoEl);
      isVideoEnabled = false;
    }
  }

  function handleMuteUpdate() {
    attachTrack();
  }

  $effect(() => {
    attachTrack();

    participant.on(ParticipantEvent.TrackSubscribed, handleTrackSubscribed);
    participant.on(ParticipantEvent.TrackUnsubscribed, handleTrackUnsubscribed);
    participant.on(ParticipantEvent.TrackMuted, handleMuteUpdate);
    participant.on(ParticipantEvent.TrackUnmuted, handleMuteUpdate);
    // For local participant
    participant.on(ParticipantEvent.LocalTrackPublished, attachTrack);
    participant.on(ParticipantEvent.LocalTrackUnpublished, attachTrack);

    return () => {
      participant.off(ParticipantEvent.TrackSubscribed, handleTrackSubscribed);
      participant.off(
        ParticipantEvent.TrackUnsubscribed,
        handleTrackUnsubscribed
      );
      participant.off(ParticipantEvent.TrackMuted, handleMuteUpdate);
      participant.off(ParticipantEvent.TrackUnmuted, handleMuteUpdate);
      participant.off(ParticipantEvent.LocalTrackPublished, attachTrack);
      participant.off(ParticipantEvent.LocalTrackUnpublished, attachTrack);
    };
  });
</script>

<div
  class="relative bg-gray-900 rounded-xl overflow-hidden aspect-video shadow-lg border border-gray-800 group"
>
  <!-- svelte-ignore a11y_media_has_caption -->
  <video
    bind:this={videoEl}
    class="w-full h-full object-cover {isVideoEnabled
      ? 'opacity-100'
      : 'opacity-0'} transition-opacity duration-300"
  ></video>

  {#if !isVideoEnabled}
    <div
      class="absolute inset-0 flex items-center justify-center text-gray-500 bg-gray-800"
    >
      {#if avatarUrl}
        <img
          src={avatarUrl}
          alt={participant.identity}
          class="w-full h-1/2 object-contain"
        />
      {:else}
        <div
          class="w-20 h-20 rounded-full bg-gray-700 flex items-center justify-center text-2xl font-bold uppercase"
        >
          {participant.identity.slice(0, 2)}
        </div>
      {/if}
    </div>
  {/if}

  <div
    class="absolute bottom-3 left-3 bg-black/60 backdrop-blur-md text-white px-3 py-1.5 rounded-lg text-sm font-medium flex items-center gap-2"
  >
    {#if participant.isMicrophoneEnabled}
      <div class="w-2 h-2 rounded-full bg-green-500 animate-pulse"></div>
    {:else}
      <div class="w-2 h-2 rounded-full bg-red-500"></div>
    {/if}
    {participant.identity}
    {participant instanceof RemoteParticipant ? "" : "(You)"}
  </div>

  {#if transcription}
    <div
      class="absolute -top-24 left-1/2 -translate-x-1/2 w-[90%] z-20 pointer-events-none transition-all duration-300 ease-out transform"
    >
      <div
        class="relative bg-white text-gray-900 px-6 py-4 rounded-[2rem] text-center text-lg font-medium shadow-xl border-2 border-gray-100 animate-pulse"
      >
        {transcription}

        <!-- Bubble Tail -->
        <div
          class="absolute -bottom-3 left-1/2 -translate-x-1/2 w-6 h-6 bg-white border-b-2 border-r-2 border-gray-100 rotate-45 transform"
        ></div>
      </div>
    </div>
  {/if}
</div>
