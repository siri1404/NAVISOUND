/**
 * Lightweight auth middleware.
 *
 * For now this validates that each incoming WebSocket upgrade request
 * carries either an `Authorization: Bearer <token>` header or a
 * `token` query-string parameter.  The token is compared against the
 * AUTH_TOKEN environment variable (optional; if unset, all requests pass).
 */

function authenticate(req, _res, next) {
	const expected = process.env.AUTH_TOKEN;

	// If no token configured, skip auth (local-dev mode)
	if (!expected) return next();

	const header = req.headers['authorization'] || '';
	const bearer = header.startsWith('Bearer ') ? header.slice(7) : '';
	const query = new URL(req.url, `http://${req.headers.host}`).searchParams.get('token') || '';

	if (bearer === expected || query === expected) {
		return next();
	}

	if (req.headers.upgrade === 'websocket') {
		// For WS upgrades we can't send a normal HTTP response easily;
		// destroy the socket which causes the client to see a connection error.
		req.socket.destroy();
		return;
	}

	return _res.status(401).json({ error: 'unauthorized' });
}

module.exports = { authenticate };
