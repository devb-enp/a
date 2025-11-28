import { AccessToken } from 'livekit-server-sdk';
import { LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL } from '$env/static/private';
import { json } from '@sveltejs/kit';
import type { RequestHandler } from './$types';

export const GET: RequestHandler = async ({ url }) => {
  const roomName = url.searchParams.get('room');
  const participantName = url.searchParams.get('username');

  if (!roomName || !participantName) {
    return json({ error: 'Missing room or username' }, { status: 400 });
  }

  if (!LIVEKIT_API_KEY || !LIVEKIT_API_SECRET) {
    return json({ error: 'Server misconfigured' }, { status: 500 });
  }

  const at = new AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET, {
    identity: participantName,
  });

  at.addGrant({ roomJoin: true, room: roomName });

  return json({ token: await at.toJwt(), url: LIVEKIT_URL });
};
