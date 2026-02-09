/**
 * Audio relay middleware – forwards binary audio chunks from the browser
 * WebSocket to the FastAPI orchestrator with minimal buffering.
 */

const WebSocket = require('ws');

const FASTAPI_WS_URL = process.env.FASTAPI_WS_URL || 'ws://localhost:8000/agent/stream';

/**
 * Attach to an existing Express WS server to relay raw audio blobs.
 * The browser sends binary audio frames; this middleware base64-encodes
 * them and forwards as JSON `audio_chunk` payloads to the orchestrator.
 *
 * @param {import('ws').WebSocket} browserSocket  – client connection
 * @param {import('ws').WebSocket} backendSocket  – FastAPI connection
 */
function relayAudio(browserSocket, backendSocket) {
	browserSocket.on('message', (msg, isBinary) => {
		if (!isBinary) return; // text messages handled elsewhere

		if (backendSocket.readyState !== WebSocket.OPEN) return;

		const b64 = Buffer.from(msg).toString('base64');
		const payload = JSON.stringify({
			type: 'audio_chunk',
			data: b64,
			timestamp: Date.now(),
		});

		backendSocket.send(payload);
	});
}

module.exports = { relayAudio };
