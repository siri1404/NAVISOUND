import React, { useEffect, useRef, useState } from 'react';
import { SpatialAudioEngine } from '../services/SpatialAudioEngine';
import { WebSocketClient } from '../services/WebSocketClient';
import { SpatialAudioVisualizer } from './SpatialAudioVisualizer';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Hazard {
	type: string;
	urgency: string;
	direction?: string;
	distance_feet?: number;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export const NavigationUI: React.FC = () => {
	/* ---- state (drives rendering) ---- */
	const [connStatus, setConnStatus] = useState<string>('disconnected');
	const [cameraActive, setCameraActive] = useState(false);
	const [audioEnabled, setAudioEnabled] = useState(false);
	const [voiceActive, setVoiceActive] = useState(false);

	const [direction, setDirection] = useState('');
	const [distanceFeet, setDistanceFeet] = useState(0);
	const [hazards, setHazards] = useState<Hazard[]>([]);
	const [confidence, setConfidence] = useState(0);
	const [summary, setSummary] = useState('');

	const [latencyMs, setLatencyMs] = useState(0);
	const [framesSent, setFramesSent] = useState(0);
	const [query, setQuery] = useState('');
	const [features, setFeatures] = useState<string[]>([]);

	/* ---- refs (stable across renders, used in callbacks) ---- */
	const videoRef = useRef<HTMLVideoElement>(null);
	const canvasRef = useRef<HTMLCanvasElement>(null);
	const wsRef = useRef<WebSocketClient | null>(null);
	const audioRef = useRef<SpatialAudioEngine | null>(null);
	const mediaStreamRef = useRef<MediaStream | null>(null);

	const streamingRef = useRef(false);
	const waitingRef = useRef(false);
	const sendTimeRef = useRef(0);
	const audioEnabledRef = useRef(false);
	const voiceActiveRef = useRef(false);
	const recognitionRef = useRef<any>(null);

	const lastSpokeRef = useRef(0);
	const lastSpokenTextRef = useRef('');
	const lastAnnouncedPeopleRef = useRef<string[]>([]);
	const lastAnnouncedHazardsRef = useRef<string[]>([]);
	const pendingUpdatesRef = useRef<string[]>([]);

	/* -------------------------------------------------------------- */
	/*  Response handler (ref so WS callback always calls latest)      */
	/* -------------------------------------------------------------- */
	const handleResponseRef = useRef((_data: any) => {});
	handleResponseRef.current = (data: any) => {
		const now = Date.now();
		setLatencyMs(sendTimeRef.current > 0 ? now - sendTimeRef.current : 0);
		waitingRef.current = false;

		console.log('[NaviSound] Raw response:', JSON.stringify(data).slice(0, 800));

		// Direction — top-level
		const dir = data.direction || '';
		const dist = data.distance_feet || 0;

		// Confidence
		const conf = data.confidence || 0;

		// Hazards array (contains obstacles too)
		const hazardsRaw: any[] = data.hazards || [];
		const haz: Hazard[] = hazardsRaw.map((h: any) => ({
			type: h.type || 'unknown',
			urgency: h.urgency || 'medium',
			direction: h.direction,
			distance_feet: h.distance_feet,
		}));

		// Audio params
		const audioParams = data.audio || {};
		const voiceInstruction = audioParams.voice_instruction || '';

		// Summary
		const sum = data.summary || data.hazard_action || '';

		// Spatial features
		const feats: string[] = data.spatial_features || [];

		// Update UI state
		if (dir) setDirection(dir);
		if (dist) setDistanceFeet(dist);
		setHazards(haz);
		if (conf > 0) setConfidence(conf);
		if (sum) setSummary(sum);
		if (feats.length > 0) setFeatures(feats);

		/* ---- SMART AUDIO FEEDBACK ---- */
		if (audioEnabledRef.current && audioRef.current) {
			// Spatial beep for direction
			if (dir) audioRef.current.playDirectionalCue(dir, dist);

			const speechParts: string[] = [];
			const timeSinceLast = now - lastSpokeRef.current;

			// === PEOPLE DETECTION (from hazards array) ===
			const people = hazardsRaw.filter((h: any) => 
				(h.type || '').toLowerCase().includes('person')
			);
			if (people.length > 0) {
				const peopleKey = people.map((p: any) => `${p.direction}-${p.distance_feet}`).join(',');
				if (!lastAnnouncedPeopleRef.current.includes(peopleKey)) {
					const personDesc = people.map((p: any) => 
						`${p.direction || 'nearby'}${p.distance_feet ? ', ' + p.distance_feet + ' feet' : ''}`
					).join(' and ');
					speechParts.push(`Person ${personDesc}`);
					lastAnnouncedPeopleRef.current = [peopleKey];
				}
			} else {
				lastAnnouncedPeopleRef.current = [];
			}

			// === CRITICAL HAZARDS ===
			const criticalHazards = hazardsRaw.filter((h: any) => 
				h.urgency === 'high' || h.urgency === 'WARNING' || h.urgency === 'CRITICAL'
			);
			if (criticalHazards.length > 0) {
				const hazardKey = criticalHazards.map((h: any) => h.type).join(',');
				if (!lastAnnouncedHazardsRef.current.includes(hazardKey)) {
					const hazardDesc = criticalHazards.map((h: any) => 
						(h.type || 'hazard').replace(/-/g, ' ')
					).join(', ');
					speechParts.push(`Warning: ${hazardDesc}`);
					lastAnnouncedHazardsRef.current = [hazardKey];
				}
			}

			// === NEW FEATURES (door, stairs) ===
			const importantFeats = feats.filter(f => 
				['door', 'stairs', 'step', 'curb', 'elevator'].some(k => f.toLowerCase().includes(k))
			);
			if (importantFeats.length > 0) {
				pendingUpdatesRef.current.push(`Ahead: ${importantFeats.join(', ')}`);
			}

			// === SPEAK LOGIC ===
			// Immediate for people and hazards
			if (speechParts.length > 0) {
				const text = speechParts.join('. ');
				console.log('[NaviSound] 🔊 IMMEDIATE:', text);
				audioRef.current.speak(text);
				lastSpokeRef.current = now;
			}
			// Batched updates every 15 seconds
			else if (pendingUpdatesRef.current.length > 0 && timeSinceLast > 15000) {
				// Use voice instruction from backend if available
				const text = voiceInstruction || pendingUpdatesRef.current.slice(0, 2).join('. ');
				console.log('[NaviSound] 📋 BATCHED:', text);
				audioRef.current.speak(text);
				pendingUpdatesRef.current = [];
				lastSpokeRef.current = now;
			}
		}

		// Continue capture loop
		if (streamingRef.current) {
			setTimeout(captureAndSend, 500);
		}
	};

	/* -------------------------------------------------------------- */
	/*  Build speech text from response data (fallback)               */
	/* -------------------------------------------------------------- */
	function buildSpeechText(
		dir: string, dist: number, sum: string,
		feats: string[], haz: Hazard[],
	): string {
		const critical = haz.filter(
			(h) => h.urgency === 'CRITICAL' || h.urgency === 'high',
		);
		if (critical.length > 0) {
			return 'Warning! ' + critical
				.map((h) => `${h.type}${h.direction ? ' on your ' + h.direction : ''}`)
				.join('. ');
		}
		const parts: string[] = [];
		if (dir && dist) parts.push(`Go ${dir.replace(/-/g, ' ')}, ${dist} feet`);
		else if (dir) parts.push(`Head ${dir.replace(/-/g, ' ')}`);
		if (sum) parts.push(sum);
		if (feats.length > 0) parts.push(`I see: ${feats.join(', ')}`);
		return parts.join('. ') || '';
	}

	/* -------------------------------------------------------------- */
	/*  Frame capture → send                                           */
	/* -------------------------------------------------------------- */
	function captureAndSend() {
		if (!streamingRef.current || waitingRef.current) return;
		const video = videoRef.current;
		const canvas = canvasRef.current;
		const client = wsRef.current;
		if (!video || !canvas || !client?.isConnected) {
			if (streamingRef.current) setTimeout(captureAndSend, 1000);
			return;
		}

		const ctx = canvas.getContext('2d');
		if (!ctx) return;
		canvas.width = 640;
		canvas.height = 480;
		ctx.drawImage(video, 0, 0, 640, 480);
		const b64 = canvas.toDataURL('image/jpeg', 0.7).split(',')[1];

		waitingRef.current = true;
		sendTimeRef.current = Date.now();
		setFramesSent((p) => p + 1);

		client.send({
			type: 'video_frame',
			data: b64,
			timestamp: Date.now() / 1000,
		});
	}

	/* -------------------------------------------------------------- */
	/*  Camera start / stop                                            */
	/* -------------------------------------------------------------- */
	async function startCamera() {
		try {
			const stream = await navigator.mediaDevices.getUserMedia({
				video: {
					width: { ideal: 640 },
					height: { ideal: 480 },
					frameRate: { ideal: 10 },
				},
			});
			mediaStreamRef.current = stream;
			if (videoRef.current) videoRef.current.srcObject = stream;
			setCameraActive(true);
			streamingRef.current = true;
			setTimeout(captureAndSend, 800); // allow stream to stabilise
		} catch (err) {
			console.error('Camera access denied:', err);
			setSummary('Camera access denied — use text queries below.');
		}
	}

	function stopCamera() {
		streamingRef.current = false;
		waitingRef.current = false;
		mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
		mediaStreamRef.current = null;
		if (videoRef.current) videoRef.current.srcObject = null;
		setCameraActive(false);
	}

	/* -------------------------------------------------------------- */
	/*  Audio toggle                                                   */
	/* -------------------------------------------------------------- */
	async function handleEnableAudio() {
		if (audioRef.current) await audioRef.current.ensureRunning();
		const next = !audioEnabled;
		setAudioEnabled(next);
		audioEnabledRef.current = next;
		if (next && audioRef.current) audioRef.current.speak('NaviSound audio enabled');
	}

	/* -------------------------------------------------------------- */
	/*  Voice recognition                                              */
	/* -------------------------------------------------------------- */
	function startVoice() {
		const SR =
			(window as any).SpeechRecognition ||
			(window as any).webkitSpeechRecognition;
		if (!SR) {
			setSummary('Speech recognition not supported in this browser.');
			return;
		}
		const recognition = new SR();
		recognition.continuous = true;
		recognition.interimResults = false;
		recognition.lang = 'en-US';

		recognition.onresult = (event: any) => {
			const last = event.results[event.results.length - 1];
			if (last.isFinal) {
				const text = last[0].transcript.trim();
				if (text && wsRef.current?.isConnected) {
					setSummary(`You said: "${text}"`);
					wsRef.current.send({
						type: 'text_query',
						destination: text,
						timestamp: Date.now() / 1000,
					});
				}
			}
		};

		recognition.onerror = (event: any) => {
			if (event.error !== 'no-speech' && event.error !== 'aborted') {
				console.error('Speech error:', event.error);
				voiceActiveRef.current = false;
				setVoiceActive(false);
			}
		};

		recognition.onend = () => {
			if (voiceActiveRef.current && recognitionRef.current) {
				try { recognitionRef.current.start(); } catch { /* */ }
			}
		};

		recognition.start();
		recognitionRef.current = recognition;
		setVoiceActive(true);
		voiceActiveRef.current = true;
	}

	function stopVoice() {
		voiceActiveRef.current = false;
		try { recognitionRef.current?.stop(); } catch { /* */ }
		recognitionRef.current = null;
		setVoiceActive(false);
	}

	function toggleVoice() {
		voiceActive ? stopVoice() : startVoice();
	}

	/* -------------------------------------------------------------- */
	/*  Text query                                                     */
	/* -------------------------------------------------------------- */
	function sendTextQuery() {
		const text = query.trim();
		if (!text || !wsRef.current?.isConnected) return;
		wsRef.current.send({
			type: 'text_query',
			destination: text,
			timestamp: Date.now() / 1000,
		});
		setQuery('');
	}

	/* -------------------------------------------------------------- */
	/*  Effects                                                        */
	/* -------------------------------------------------------------- */

	// WebSocket
	useEffect(() => {
		const client = new WebSocketClient();
		wsRef.current = client;
		client.onStatusChange = (s) => setConnStatus(s);
		client.onMessage = (data) => handleResponseRef.current(data);
		client.connect();
		return () => {
			client.disconnect();
			streamingRef.current = false;
			mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
			voiceActiveRef.current = false;
			try { recognitionRef.current?.stop(); } catch { /* */ }
		};
	}, []);

	// Audio engine
	useEffect(() => {
		audioRef.current = new SpatialAudioEngine();
	}, []);

	// Keyboard shortcuts
	useEffect(() => {
		function handler(e: KeyboardEvent) {
			if ((e.target as HTMLElement)?.tagName === 'INPUT') return;
			switch (e.code) {
				case 'Space': {
					e.preventDefault();
					const parts: string[] = [];
					if (direction) parts.push(`Direction: ${direction}`);
					if (distanceFeet > 0) parts.push(`${distanceFeet} feet`);
					if (confidence > 0) parts.push(`Confidence ${Math.round(confidence * 100)} percent`);
					if (hazards.length) parts.push(`${hazards.length} hazards nearby`);
					audioRef.current?.speak(parts.join('. ') || 'No guidance available.');
					break;
				}
				case 'KeyQ':
					wsRef.current?.send({
						type: 'text_query',
						destination: 'Where am I? Describe my current surroundings.',
						timestamp: Date.now() / 1000,
					});
					break;
				case 'KeyH':
					if (hazards.length === 0) {
						audioRef.current?.speak('No hazards detected.');
					} else {
						audioRef.current?.speak(
							'Hazards: ' + hazards.map((h) => `${h.type} ${h.urgency}`).join('. '),
						);
					}
					break;
				case 'KeyM':
					handleEnableAudio();
					break;
				case 'KeyV':
					toggleVoice();
					break;
			}
		}
		window.addEventListener('keydown', handler);
		return () => window.removeEventListener('keydown', handler);
		// eslint-disable-next-line react-hooks/exhaustive-deps
	}, [direction, distanceFeet, confidence, hazards, audioEnabled, voiceActive]);

	/* -------------------------------------------------------------- */
	/*  Helpers                                                        */
	/* -------------------------------------------------------------- */
	const dirEmoji = (d: string) => {
		const m: Record<string, string> = {
			forward: '⬆️', 'forward-left': '↖️', 'forward-right': '↗️',
			left: '⬅️', right: '➡️',
			'back-left': '↙️', 'back-right': '↘️', back: '⬇️',
			'slight-left': '↖️', 'slight-right': '↗️',
		};
		return m[d] || '🧭';
	};

	const connColor =
		connStatus === 'connected' ? '#22c55e' :
		connStatus === 'connecting' ? '#f59e0b' : '#ef4444';

	/* -------------------------------------------------------------- */
	/*  Render                                                         */
	/* -------------------------------------------------------------- */
	return (
		<main
			role="main"
			aria-label="NaviSound Navigation Interface"
			style={{
				background: '#0a0a12', color: '#f1f5f9',
				fontFamily: "'Inter','Segoe UI',Arial,sans-serif",
				minHeight: '100vh', display: 'flex', flexDirection: 'column',
			}}
		>
			{/* ===== Header ===== */}
			<header
				style={{
					padding: '14px 24px', background: '#111827',
					borderBottom: '1px solid #1f2937',
					display: 'flex', alignItems: 'center',
					justifyContent: 'space-between', flexWrap: 'wrap', gap: 10,
				}}
			>
				<div>
					<h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>
						<span style={{ color: '#3b82f6' }}>Navi</span>Sound
					</h1>
					<p style={{ margin: 0, fontSize: 12, color: '#94a3b8' }}>
						Real-time spatial audio navigation for blind users
					</p>
				</div>
				<div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
					<Btn
						color={audioEnabled ? '#22c55e' : '#3b82f6'}
						onClick={handleEnableAudio}
						aria-pressed={audioEnabled}
					>
						🔊 {audioEnabled ? 'Audio ON' : 'Enable Audio'}
					</Btn>
					<Btn
						color={cameraActive ? '#ef4444' : '#3b82f6'}
						onClick={cameraActive ? stopCamera : startCamera}
					>
						📷 {cameraActive ? 'Stop Camera' : 'Start Camera'}
					</Btn>
					<Btn
						color={voiceActive ? '#22c55e' : '#6b7280'}
						onClick={toggleVoice}
						aria-pressed={voiceActive}
					>
						🎙 Voice: {voiceActive ? 'ON' : 'OFF'}
					</Btn>
				</div>
			</header>

			{/* ===== Split screen ===== */}
			<div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
				{/* --- Camera panel --- */}
				<div
					style={{
						flex: '1 1 50%', background: '#000',
						display: 'flex', alignItems: 'center', justifyContent: 'center',
						position: 'relative', minHeight: 360,
					}}
				>
					<video
						ref={videoRef}
						autoPlay
						muted
						playsInline
						style={{
							width: '100%', height: '100%', objectFit: 'cover',
							display: cameraActive ? 'block' : 'none',
						}}
					/>
					<canvas ref={canvasRef} style={{ display: 'none' }} />

					{!cameraActive && (
						<div style={{ textAlign: 'center', color: '#6b7280', padding: 40 }}>
							<div style={{ fontSize: 48, marginBottom: 12 }}>📷</div>
							<p style={{ margin: 0, fontSize: 16 }}>Camera off</p>
							<p style={{ margin: '4px 0 0', fontSize: 13, color: '#4b5563' }}>
								Click &ldquo;Start Camera&rdquo; to begin streaming
							</p>
						</div>
					)}

					{cameraActive && (
						<div
							style={{
								position: 'absolute', top: 12, left: 12,
								background: 'rgba(0,0,0,.7)', padding: '4px 10px',
								borderRadius: 4, fontSize: 12, color: '#f87171',
								display: 'flex', alignItems: 'center', gap: 6,
							}}
						>
							<span
								style={{
									width: 8, height: 8, borderRadius: '50%',
									background: '#f87171', display: 'inline-block',
									animation: 'pulse 1.5s infinite',
								}}
							/>
							LIVE — {framesSent} frames
						</div>
					)}
				</div>

				{/* --- Guidance panel --- */}
				<div
					style={{
						flex: '1 1 50%', padding: '20px 24px', overflowY: 'auto',
						background: '#111827', borderLeft: '1px solid #1f2937',
						display: 'flex', flexDirection: 'column', gap: 16,
					}}
					aria-live="polite"
					aria-atomic="true"
				>
					{/* Direction */}
					<section aria-label="Current direction">
						<SectionTitle>Direction</SectionTitle>
						<div
							style={{
								background: direction ? '#1e3a5f' : '#1f2937',
								borderRadius: 8, padding: '16px 20px',
								display: 'flex', alignItems: 'center', gap: 16,
								border: direction
									? '1px solid #3b82f6'
									: '1px solid #374151',
							}}
						>
							<span style={{ fontSize: 36 }}>{dirEmoji(direction)}</span>
							<div>
								<div style={{ fontSize: 22, fontWeight: 700 }}>
									{direction || 'Waiting for camera…'}
								</div>
								{distanceFeet > 0 && (
									<div style={{ fontSize: 15, color: '#93c5fd' }}>
										{distanceFeet} feet
									</div>
								)}
							</div>
						</div>
					</section>

					{/* Spatial mini-map */}
					<SpatialAudioVisualizer
						direction={direction}
						distance={distanceFeet}
						confidence={confidence}
						hazardCount={hazards.length}
					/>

					{/* Hazards */}
					<section aria-label="Hazard warnings" aria-live="assertive">
						<SectionTitle>Hazards</SectionTitle>
						{hazards.length === 0 ? (
							<div style={{ color: '#22c55e', fontSize: 14, padding: '6px 0' }}>
								✓ No hazards detected
							</div>
						) : (
							<ul
								style={{
									listStyle: 'none', padding: 0, margin: 0,
									display: 'flex', flexDirection: 'column', gap: 6,
								}}
							>
								{hazards.map((h, i) => (
									<li
										key={i}
										role="alert"
										style={{
											padding: '10px 14px', borderRadius: 6,
											fontSize: 14, fontWeight: 600,
											background:
												h.urgency === 'CRITICAL' ? '#7f1d1d'
												: h.urgency === 'high' ? '#78350f'
												: '#1f2937',
											border: `1px solid ${
												h.urgency === 'CRITICAL' ? '#ef4444'
												: h.urgency === 'high' ? '#f59e0b'
												: '#374151'}`,
											color:
												h.urgency === 'CRITICAL' ? '#fca5a5'
												: h.urgency === 'high' ? '#fde68a'
												: '#d1d5db',
										}}
									>
										⚠ {h.type}
										{h.direction ? ` — ${h.direction}` : ''}
										{h.distance_feet ? `, ${h.distance_feet}ft` : ''}
										{' '}({h.urgency})
									</li>
								))}
							</ul>
						)}
					</section>

					{/* Spatial features */}
					{features.length > 0 && (
						<section aria-label="Detected features">
							<SectionTitle>Scene</SectionTitle>
							<div
								style={{
									display: 'flex', flexWrap: 'wrap', gap: 6,
								}}
							>
								{features.map((f, i) => (
									<span
										key={i}
										style={{
											background: '#1e3a5f', padding: '4px 10px',
											borderRadius: 12, fontSize: 13, color: '#93c5fd',
											border: '1px solid #2563eb44',
										}}
									>
										{f}
									</span>
								))}
							</div>
						</section>
					)}

					{/* Confidence */}
					<section aria-label="Confidence level">
						<SectionTitle>Confidence</SectionTitle>
						<div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
							<div
								style={{
									flex: 1, height: 8, background: '#1f2937',
									borderRadius: 4, overflow: 'hidden',
								}}
							>
								<div
									style={{
										width: `${confidence * 100}%`,
										height: '100%', borderRadius: 4,
										background:
											confidence > 0.7 ? '#22c55e'
											: confidence > 0.4 ? '#f59e0b'
											: '#ef4444',
										transition: 'width .3s',
									}}
								/>
							</div>
							<span style={{ fontSize: 16, fontWeight: 700, minWidth: 45, textAlign: 'right' }}>
								{confidence > 0 ? `${Math.round(confidence * 100)}%` : '—'}
							</span>
						</div>
					</section>

					{/* Summary / voice instruction */}
					{summary && (
						<section
							aria-label="Guidance summary"
							style={{
								background: '#1e293b', borderRadius: 8,
								padding: '12px 16px',
								borderLeft: '3px solid #3b82f6',
								fontSize: 15, lineHeight: 1.5,
							}}
						>
							💬 {summary}
						</section>
					)}
				</div>
			</div>

			{/* ===== Query bar ===== */}
			<div
				style={{
					padding: '10px 24px', background: '#111827',
					borderTop: '1px solid #1f2937',
					display: 'flex', gap: 8, alignItems: 'center',
				}}
			>
				<input
					type="text"
					value={query}
					onChange={(e) => setQuery(e.target.value)}
					onKeyDown={(e) => e.key === 'Enter' && sendTextQuery()}
					placeholder="Ask: Where is the exit? or What is around me?"
					aria-label="Navigation query"
					style={{
						flex: 1, padding: '10px 14px', borderRadius: 6,
						border: '1px solid #374151', background: '#1f2937',
						color: '#f1f5f9', fontSize: 15, outline: 'none',
					}}
				/>
				<Btn color="#3b82f6" onClick={sendTextQuery}>Ask</Btn>
			</div>

			{/* ===== Status bar ===== */}
			<div
				style={{
					padding: '8px 24px', background: '#0d1117',
					borderTop: '1px solid #1f2937',
					display: 'flex', justifyContent: 'space-between',
					alignItems: 'center', flexWrap: 'wrap',
					fontSize: 12, color: '#6b7280', gap: 8,
				}}
			>
				<div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
					<span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
						<span
							style={{
								width: 8, height: 8, borderRadius: '50%',
								background: connColor, display: 'inline-block',
							}}
						/>
						{connStatus}
					</span>
					<span>Latency: {latencyMs > 0 ? `${(latencyMs / 1000).toFixed(1)}s` : '—'}</span>
					<span>Frames: {framesSent}</span>
				</div>
				<div>
					<Kbd>SPACE</Kbd> scene{' '}
					<Kbd>Q</Kbd> query{' '}
					<Kbd>H</Kbd> hazards{' '}
					<Kbd>M</Kbd> audio{' '}
					<Kbd>V</Kbd> voice
				</div>
			</div>

			{/* CSS animation for the LIVE pulse */}
			<style>{`
				@keyframes pulse {
					0%, 100% { opacity: 1; }
					50% { opacity: .3; }
				}
			`}</style>
		</main>
	);
};

/* ------------------------------------------------------------------ */
/*  Tiny shared sub-components (inline to avoid extra files)           */
/* ------------------------------------------------------------------ */

function SectionTitle({ children }: { children: React.ReactNode }) {
	return (
		<h2
			style={{
				fontSize: 13, color: '#94a3b8', margin: '0 0 8px',
				textTransform: 'uppercase', letterSpacing: 1, fontWeight: 600,
			}}
		>
			{children}
		</h2>
	);
}

function Btn(
	props: React.ButtonHTMLAttributes<HTMLButtonElement> & { color: string },
) {
	const { color, style, ...rest } = props;
	return (
		<button
			{...rest}
			style={{
				padding: '8px 16px', borderRadius: 6, border: 'none',
				cursor: 'pointer', background: color, color: '#fff',
				fontSize: 14, fontWeight: 600, whiteSpace: 'nowrap',
				...style,
			}}
		/>
	);
}

function Kbd({ children }: { children: React.ReactNode }) {
	return (
		<kbd
			style={{
				display: 'inline-block', padding: '2px 6px', borderRadius: 3,
				background: '#1f2937', border: '1px solid #374151',
				fontSize: 11, fontFamily: 'monospace', marginRight: 2,
			}}
		>
			{children}
		</kbd>
	);
}
