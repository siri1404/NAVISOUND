import React, { useEffect, useRef, useState } from 'react';
import { SpatialAudioEngine } from '../services/SpatialAudioEngine';
import { WebSocketClient } from '../services/WebSocketClient';
import { SensorCapture, SensorData } from '../services/SensorCapture';
import { SpatialAudioVisualizer } from './SpatialAudioVisualizer';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface Hazard {
	type: string;
	urgency: string;
	direction?: string;
	distance_feet?: number;
	bounding_box?: BBox;
}

interface BBox {
	ymin: number; xmin: number; ymax: number; xmax: number;
}

interface DetectionOverlay {
	label: string;
	box: BBox;
	color: string;          // CSS colour
	urgency?: string;
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
	const overlayCanvasRef = useRef<HTMLCanvasElement>(null);
	const wsRef = useRef<WebSocketClient | null>(null);
	const audioRef = useRef<SpatialAudioEngine | null>(null);
	const mediaStreamRef = useRef<MediaStream | null>(null);

	const streamingRef = useRef(false);
	const waitingRef = useRef(false);
	const sendTimeRef = useRef(0);
	const audioEnabledRef = useRef(false);
	const voiceActiveRef = useRef(false);
	const recognitionRef = useRef<any>(null);

	const sensorRef = useRef<SensorCapture | null>(null);
	const sensorDataRef = useRef<SensorData | null>(null);

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

		// Draw bounding-box overlays on camera feed
		drawDetections(data);

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

		// Play native Gemini-generated audio if present (bypasses browser TTS)
		if (data.native_audio_b64) {
			try {
				const audioCtx = new AudioContext({ sampleRate: 24000 });
				const raw = Uint8Array.from(atob(data.native_audio_b64), (c) => c.charCodeAt(0));
				// Gemini outputs 24kHz 16-bit mono PCM
				const float32 = new Float32Array(raw.length / 2);
				const view = new DataView(raw.buffer);
				for (let i = 0; i < float32.length; i++) {
					float32[i] = view.getInt16(i * 2, true) / 32768;
				}
				const buf = audioCtx.createBuffer(1, float32.length, 24000);
				buf.getChannelData(0).set(float32);
				const src = audioCtx.createBufferSource();
				src.buffer = buf;
				src.connect(audioCtx.destination);
				src.start();
				console.log('[NaviSound] Playing native Gemini audio:', float32.length, 'samples');
			} catch (e) {
				console.warn('[NaviSound] Native audio playback error:', e);
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
	/*  Bounding-box overlay rendering                                 */
	/* -------------------------------------------------------------- */
	function drawDetections(data: any): void {
		const overlay = overlayCanvasRef.current;
		const video = videoRef.current;
		if (!overlay || !video) return;

		// Match overlay size to video display size
		const rect = video.getBoundingClientRect();
		overlay.width = rect.width;
		overlay.height = rect.height;

		const ctx = overlay.getContext('2d');
		if (!ctx) return;
		ctx.clearRect(0, 0, overlay.width, overlay.height);

		const detections: DetectionOverlay[] = [];

		// Collect bounding boxes from hazards
		const hazardsRaw: any[] = data.hazards || [];
		for (const h of hazardsRaw) {
			if (h.bounding_box) {
				const urgency = h.urgency || 'medium';
				detections.push({
					label: h.type || 'hazard',
					box: h.bounding_box,
					urgency,
					color: urgency === 'high' || urgency === 'CRITICAL' || urgency === 'WARNING'
						? '#ef4444' : urgency === 'medium' ? '#f59e0b' : '#22c55e',
				});
			}
		}

		// Collect from spatial_features
		const spatial: any[] = data.spatial_features || [];
		for (const f of spatial) {
			const bb = typeof f === 'object' ? f.bounding_box : null;
			if (bb) {
				detections.push({
					label: f.label || f.name || 'feature',
					box: bb,
					color: '#3b82f6',
				});
			}
		}

		// Draw each detection
		const w = overlay.width;
		const h = overlay.height;

		for (const det of detections) {
			// Gemini normalises to 0-1000 range
			const x1 = (det.box.xmin / 1000) * w;
			const y1 = (det.box.ymin / 1000) * h;
			const x2 = (det.box.xmax / 1000) * w;
			const y2 = (det.box.ymax / 1000) * h;
			const bw = x2 - x1;
			const bh = y2 - y1;

			// Box outline
			ctx.strokeStyle = det.color;
			ctx.lineWidth = 2;
			ctx.strokeRect(x1, y1, bw, bh);

			// Semi-transparent fill
			ctx.fillStyle = det.color + '18'; // ~10% opacity
			ctx.fillRect(x1, y1, bw, bh);

			// Label background
			const label = `${det.label}${det.urgency ? ' (' + det.urgency + ')' : ''}`;
			ctx.font = 'bold 12px Manrope, sans-serif';
			const metrics = ctx.measureText(label);
			const labelH = 18;
			const labelY = y1 > labelH + 4 ? y1 - labelH - 2 : y1 + 2;
			ctx.fillStyle = det.color + 'cc'; // ~80% opacity
			ctx.fillRect(x1, labelY, metrics.width + 8, labelH);

			// Label text
			ctx.fillStyle = '#ffffff';
			ctx.fillText(label, x1 + 4, labelY + 13);
		}

		// Detection count badge in top-right
		if (detections.length > 0) {
			const badge = `${detections.length} detection${detections.length > 1 ? 's' : ''}`;
			ctx.font = 'bold 11px Manrope, sans-serif';
			const bm = ctx.measureText(badge);
			ctx.fillStyle = 'rgba(0,0,0,0.75)';
			ctx.fillRect(w - bm.width - 16, 8, bm.width + 12, 20);
			ctx.fillStyle = '#3b82f6';
			ctx.fillText(badge, w - bm.width - 10, 22);
		}
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

		const payload: any = {
			type: 'video_frame',
			data: b64,
			timestamp: Date.now() / 1000,
		};

		// Attach live sensor readings (GPS, compass, accelerometer)
		if (sensorDataRef.current) {
			payload.sensor_data = {
				lat: sensorDataRef.current.lat,
				lon: sensorDataRef.current.lon,
				accuracy: sensorDataRef.current.accuracy,
				heading: sensorDataRef.current.heading,
				speed: sensorDataRef.current.speed,
				pitch: sensorDataRef.current.pitch,
				roll: sensorDataRef.current.roll,
				accelX: sensorDataRef.current.accelX,
				accelY: sensorDataRef.current.accelY,
				accelZ: sensorDataRef.current.accelZ,
			};
		}

		client.send(payload);
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

			// Start sensor capture (GPS + compass + accelerometer)
			if (!sensorRef.current) {
				sensorRef.current = new SensorCapture();
			}
			sensorRef.current.start().catch(() => {});
			sensorRef.current.onUpdate((data) => { sensorDataRef.current = data; });

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
		sensorRef.current?.stop();
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
					// Use voice_command type so orchestrator can detect
					// "where" queries for spatial memory recall
					const lc = text.toLowerCase();
					if (lc.includes('where') || lc.includes('recall') || lc.includes('remember')) {
						wsRef.current.send({
							type: 'voice_command',
							text: text,
							timestamp: Date.now() / 1000,
						});
					} else {
						wsRef.current.send({
							type: 'text_query',
							destination: text,
							timestamp: Date.now() / 1000,
						});
					}
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
				background: '#0a0a0a', color: '#e0e0e0',
				fontFamily: "'Manrope','Segoe UI',Arial,sans-serif",
				minHeight: '100vh', display: 'flex', flexDirection: 'column',
			}}
		>
			<style>{`
				@import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=Manrope:wght@300;400;500;600&display=swap');
				body { font-family: 'Manrope', 'Segoe UI', sans-serif; }
				h1, h2, h3 { font-family: 'Syne', sans-serif; font-weight: 700; }
			`}</style>

			{/* ===== Header ===== */}
			<header
				style={{
					padding: '16px 24px', background: '#000000',
					borderBottom: '1px solid #1a1a1a',
					display: 'flex', alignItems: 'center',
					justifyContent: 'space-between', flexWrap: 'wrap', gap: 10,
					backdropFilter: 'blur(8px)',
				}}
			>
				<div>
					<h1 style={{ margin: 0, fontSize: 26, fontWeight: 700, letterSpacing: '2px', color: '#3b82f6' }}>
						NAVISOUND
					</h1>
					<p style={{ margin: '4px 0 0', fontSize: 12, color: '#9ca3af' }}>
						Real-time spatial audio navigation for blind users
					</p>
				</div>
				<div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
					<Btn
						color={audioEnabled ? '#10b981' : '#3b82f6'}
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
						color={voiceActive ? '#10b981' : '#6b7280'}
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
						flex: '1 1 50%', background: '#1a1a1a',
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

					{/* Bounding-box detection overlay */}
					{cameraActive && (
						<canvas
							ref={overlayCanvasRef}
							style={{
								position: 'absolute', top: 0, left: 0,
								width: '100%', height: '100%',
								pointerEvents: 'none',
								zIndex: 2,
							}}
							aria-hidden="true"
						/>
					)}

					{!cameraActive && (
				<div style={{ textAlign: 'center', color: '#9ca3af', padding: 40 }}>
					<div style={{ fontSize: 48, marginBottom: 12 }}>📷</div>
					<p style={{ margin: 0, fontSize: 16, color: '#d1d5db' }}>Camera off</p>
					<p style={{ margin: '4px 0 0', fontSize: 13, color: '#9ca3af' }}>
								Click &ldquo;Start Camera&rdquo; to begin streaming
							</p>
						</div>
					)}

					{cameraActive && (
						<div
							style={{
								position: 'absolute', top: 12, left: 12,
								background: 'rgba(0,0,0,.8)', padding: '6px 12px',
								borderRadius: 6, fontSize: 12, color: '#3b82f6',
								display: 'flex', alignItems: 'center', gap: 6,
								fontWeight: 600,
							}}
						>
							<span
								style={{
									width: 8, height: 8, borderRadius: '50%',
									background: '#3b82f6', display: 'inline-block',
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
					background: '#000000', borderLeft: '1px solid #1a1a1a',
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
								background: direction ? 'rgba(59, 130, 246, 0.05)' : '#0a0a0a',
								borderRadius: 8, padding: '16px 20px',
								display: 'flex', alignItems: 'center', gap: 16,
								border: direction
									? '1px solid #3b82f6'
									: '1px solid #1a1a1a',
							}}
						>
							<span style={{ fontSize: 36 }}>{dirEmoji(direction)}</span>
							<div>
								<div style={{ fontSize: 22, fontWeight: 700, color: '#e0e0e0', fontFamily: "'Syne', sans-serif" }}>
									{direction || 'Waiting for camera…'}
								</div>
								{distanceFeet > 0 && (
								<div style={{ fontSize: 15, color: '#60a5fa', fontWeight: 600 }}>
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
							<div style={{ color: '#10b981', fontSize: 14, padding: '6px 0' }}>
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
												h.urgency === 'CRITICAL' ? 'rgba(239, 68, 68, 0.15)'
												: h.urgency === 'high' ? 'rgba(59, 130, 246, 0.15)'
												: '#0a0a0a',
											border: `1px solid ${
												h.urgency === 'CRITICAL' ? '#ef4444'
												: h.urgency === 'high' ? '#3b82f6'
												: '#1a1a1a'}`,
											color:
												h.urgency === 'CRITICAL' ? '#fca5a5'
												: h.urgency === 'high' ? '#3b82f6'
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
							<span style={{ fontSize: 16, fontWeight: 700, minWidth: 45, textAlign: 'right', color: '#e0e0e0' }}>
								{confidence > 0 ? `${Math.round(confidence * 100)}%` : '—'}
							</span>
						</div>
					</section>

					{/* Summary / voice instruction */}
					{summary && (
						<section
							aria-label="Guidance summary"
							style={{
									background: 'rgba(59, 130, 246, 0.05)', borderRadius: 8,
								padding: '12px 16px',
								borderLeft: '3px solid #3b82f6',
								fontSize: 15, lineHeight: 1.5,
								color: '#e0e0e0',
								fontFamily: "'Manrope', sans-serif",
							}}
						>
							💬 {summary}
						</section>
					)}
				</div>
			</div>

		{/* ===== Status bar ===== */}
		<footer
			style={{
				padding: '24px 32px',
				background: '#000000',
				borderTop: '1px solid #1a1a1a',
				display: 'flex',
				justifyContent: 'space-between',
				alignItems: 'center',
				gap: 24,
				fontFamily: "'Manrope', sans-serif",
			}}
		>
			{/* Left: connection status */}
			<div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
				<span
					style={{
						width: 14,
						height: 14,
						borderRadius: '50%',
						background: connColor,
						display: 'inline-block',
					}}
				/>
				<div>
					<div style={{ fontSize: 18, fontWeight: 600, color: '#e0e0e0', textTransform: 'uppercase', letterSpacing: 1 }}>
						{connStatus}
					</div>
					<div style={{ fontSize: 13, color: '#60a5fa', marginTop: 4 }}>
						Latency: {latencyMs > 0 ? `${(latencyMs / 1000).toFixed(1)}s` : '—'}
					</div>
					<div style={{ fontSize: 13, color: '#60a5fa' }}>
						Frames: {framesSent}
					</div>
				</div>
			</div>

			{/* Right: keyboard shortcuts */}
			<div style={{ display: 'flex', flexDirection: 'column', gap: 8, textAlign: 'right' }}>
				<div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
					<div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
						<Kbd>SPACE</Kbd>
						<span style={{ fontSize: 14, color: '#d1d5db' }}>Scene</span>
					</div>
					<div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
						<Kbd>Q</Kbd>
						<span style={{ fontSize: 14, color: '#d1d5db' }}>Query</span>
					</div>
					<div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
						<Kbd>H</Kbd>
						<span style={{ fontSize: 14, color: '#d1d5db' }}>Hazards</span>
					</div>
					<div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
						<Kbd>M</Kbd>
						<span style={{ fontSize: 14, color: '#d1d5db' }}>Audio</span>
					</div>
					<div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
						<Kbd>V</Kbd>
						<span style={{ fontSize: 14, color: '#d1d5db' }}>Voice</span>
					</div>
				</div>
			</div>
		</footer>

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
				fontSize: 13, color: '#60a5fa', margin: '0 0 8px',
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
				background: '#1f2937', border: '1px solid #3b82f6',
				fontSize: 11, fontFamily: 'monospace', marginRight: 2,
			}}
		>
			{children}
		</kbd>
	);
}
