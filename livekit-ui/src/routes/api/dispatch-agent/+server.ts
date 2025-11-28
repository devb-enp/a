import { LIVEKIT_API_KEY, LIVEKIT_API_SECRET, LIVEKIT_URL } from '$env/static/private';
import { json } from '@sveltejs/kit';
import { AgentDispatchClient } from 'livekit-server-sdk';
import type { RequestHandler } from './$types';

export const POST: RequestHandler = async ({ request }) => {
  try {
    const { roomName, agentName = 'transcriber-agent', metadata = '' } = await request.json();
    
    if (!roomName) {
      return json({ error: 'Room name is required' }, { status: 400 });
    }

    if (!LIVEKIT_API_KEY || !LIVEKIT_API_SECRET || !LIVEKIT_URL) {
      return json({ error: 'Server misconfigured' }, { status: 500 });
    }

    const client = new AgentDispatchClient(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET);
    
    await client.createDispatch(roomName, agentName, { metadata });
    
    console.log(`Agent "${agentName}" dispatched to room: ${roomName}`);
    
    return json({ success: true, message: `Agent dispatched to room: ${roomName}` });
  } catch (error) {
    console.error('Failed to dispatch agent:', error);
    return json({ 
      error: error instanceof Error ? error.message : 'Failed to dispatch agent' 
    }, { status: 500 });
  }
};
