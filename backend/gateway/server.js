const express = require('express');
const WebSocket = require('ws');
const http = require('http');
const crypto = require('crypto');

const app = express();
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

const PORT = Number(process.env.EXPRESS_PORT || 3000);
const FASTAPI_WS_URL = process.env.FASTAPI_WS_URL || 'ws://localhost:8000/agent/stream';

app.get('/health', (_req, res) => {
	res.json({ status: 'ok' });
});

const generateSessionId = () => crypto.randomUUID();

// Relay browser streams -> FastAPI orchestrator
wss.on('connection', (socket) => {
	const sessionId = generateSessionId();
	const fastApiWs = new WebSocket(FASTAPI_WS_URL, {
		headers: { 'X-Session-Id': sessionId }
	});

	const safeSend = (ws, data) => {
		if (ws.readyState === WebSocket.OPEN) {
			ws.send(data);
		}
	};

	// Queue messages until the backend WS is open
	let backendReady = false;
	const pendingMessages = [];

	fastApiWs.on('open', () => {
		backendReady = true;
		// Flush any messages that arrived while we were connecting
		for (const msg of pendingMessages) {
			fastApiWs.send(msg);
		}
		pendingMessages.length = 0;
	});

	socket.on('message', (msg) => {
		let payload;
		try {
			payload = JSON.parse(msg);
		} catch (err) {
			safeSend(socket, JSON.stringify({ type: 'error', error: 'invalid_json' }));
			return;
		}

		const outgoing = JSON.stringify({
			...payload,
			session_id: sessionId,
			browser_timestamp: payload.timestamp
		});

		if (backendReady) {
			safeSend(fastApiWs, outgoing);
		} else {
			pendingMessages.push(outgoing);
		}
	});

	fastApiWs.on('message', (msg) => {
		let response;
		try {
			response = JSON.parse(msg);
		} catch (err) {
			safeSend(socket, JSON.stringify({ type: 'error', error: 'invalid_backend_json' }));
			return;
		}

		// Forward full response from orchestrator, adding a type tag
		safeSend(
			socket,
			JSON.stringify({
				type: 'navigation_command',
				...response
			})
		);
	});

	const closeAll = () => {
		if (fastApiWs.readyState === WebSocket.OPEN) {
			fastApiWs.close();
		}
	};

	socket.on('close', closeAll);
	socket.on('error', closeAll);
	fastApiWs.on('close', () => socket.close());
	fastApiWs.on('error', () => socket.close());
});

server.listen(PORT, () => {
	console.log(`Gateway on :${PORT}`);
});
