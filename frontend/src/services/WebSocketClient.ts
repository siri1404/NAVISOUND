/**
 * WebSocket client for NaviSound gateway.
 * Handles connection lifecycle, auto-reconnection, and JSON framing.
 */

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

export class WebSocketClient {
	private ws: WebSocket | null = null;
	private url: string;
	private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
	private reconnectDelay = 1000;
	private maxReconnectDelay = 16000;
	private intentionallyClosed = false;

	onMessage: ((data: any) => void) | null = null;
	onStatusChange: ((status: ConnectionStatus) => void) | null = null;

	constructor(url?: string) {
		this.url = url || (window as any).GATEWAY_WS || 'ws://localhost:3001';
	}

	connect(): void {
		if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) return;
		this.intentionallyClosed = false;
		this.onStatusChange?.('connecting');

		try {
			this.ws = new WebSocket(this.url);
		} catch {
			this.onStatusChange?.('error');
			this._scheduleReconnect();
			return;
		}

		this.ws.onopen = () => {
			this.reconnectDelay = 1000;
			this.onStatusChange?.('connected');
		};

		this.ws.onmessage = (ev) => {
			try {
				this.onMessage?.(JSON.parse(ev.data as string));
			} catch {
				// non-JSON
			}
		};

		this.ws.onclose = () => {
			this.onStatusChange?.('disconnected');
			if (!this.intentionallyClosed) this._scheduleReconnect();
		};

		this.ws.onerror = () => {
			this.onStatusChange?.('error');
		};
	}

	send(data: object): boolean {
		if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false;
		this.ws.send(JSON.stringify(data));
		return true;
	}

	get isConnected(): boolean {
		return this.ws?.readyState === WebSocket.OPEN;
	}

	disconnect(): void {
		this.intentionallyClosed = true;
		if (this.reconnectTimer) {
			clearTimeout(this.reconnectTimer);
			this.reconnectTimer = null;
		}
		this.ws?.close();
		this.ws = null;
	}

	private _scheduleReconnect(): void {
		if (this.reconnectTimer || this.intentionallyClosed) return;
		this.reconnectTimer = setTimeout(() => {
			this.reconnectTimer = null;
			this.connect();
		}, this.reconnectDelay);
		this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay);
	}
}
