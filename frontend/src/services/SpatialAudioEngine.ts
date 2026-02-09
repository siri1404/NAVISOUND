export class SpatialAudioEngine {
	private audioContext: AudioContext;
	private panner: PannerNode;
	private gainNode: GainNode;

	constructor() {
		// Create/resume on user gesture in app; creating here is fine for modern browsers
		const AC = (window as any).AudioContext || (window as any).webkitAudioContext;
		this.audioContext = new AC();
		this.panner = this.audioContext.createPanner();
		this.gainNode = this.audioContext.createGain();

		this.panner.connect(this.gainNode);
		this.gainNode.connect(this.audioContext.destination);

		this.panner.panningModel = 'HRTF';
		this.panner.distanceModel = 'inverse';
		this.panner.refDistance = 1;
		this.panner.maxDistance = 100;
	}

	async ensureRunning() {
		if (this.audioContext.state === 'suspended') {
			try {
				await this.audioContext.resume();
			} catch (e) {
				// ignore
			}
		}
	}

	playDirectionalCue(direction: string, distance: number, hazard_type?: string) {
		const angleMap: Record<string, number> = {
			forward: 0,
			'forward-left': -45,
			'forward-right': 45,
			left: -90,
			'left-forward': -45,
			right: 90,
			'right-forward': 45,
			'back-left': -135,
			'back-right': 135,
			back: 180,
			center: 0,
			'slight-left': -30,
			'slight-right': 30,
		};

		const angle = angleMap[direction] ?? 0;
		const radians = (angle * Math.PI) / 180;

		const x = Math.sin(radians) * (distance || 0) / 10;
		const z = Math.cos(radians) * (distance || 0) / 10;
		const y = 1.5;

		try {
			this.panner.positionX.setValueAtTime(x, this.audioContext.currentTime);
			this.panner.positionY.setValueAtTime(y, this.audioContext.currentTime);
			this.panner.positionZ.setValueAtTime(z, this.audioContext.currentTime);
		} catch (e) {
			// Some browsers use setPosition
			if ((this.panner as any).setPosition) {
				(this.panner as any).setPosition(x, y, z);
			}
		}

		const frequency = this.hazardTypeToFrequency(hazard_type || 'unknown');

		const osc = this.audioContext.createOscillator();
		osc.frequency.setValueAtTime(frequency, this.audioContext.currentTime);
		osc.type = 'sine';
		osc.connect(this.panner);

		this.gainNode.gain.setValueAtTime(0.3, this.audioContext.currentTime);
		osc.start();
		osc.stop(this.audioContext.currentTime + 0.2);
	}

	private hazardTypeToFrequency(hazard?: string): number {
		const map: Record<string, number> = {
			furniture: 400,
			person: 800,
			vehicle: 200,
			stairs: 1200,
			unknown: 600,
			warning: 1000,
		};
		return map[hazard || 'unknown'] || 600;
	}

	/** Speak text using SpeechSynthesis. Throttles to avoid cancel-loops. */
	speak(text: string, rate = 1.1): void {
		if (!text) return;
		if (!('speechSynthesis' in window)) {
			console.warn('[NaviSound] SpeechSynthesis not available');
			return;
		}
		// Cancel any queued/in-progress speech
		speechSynthesis.cancel();

		// Small delay after cancel to let browser clean up (Chrome needs this)
		setTimeout(() => {
			const u = new SpeechSynthesisUtterance(text);
			u.rate = rate;
			u.volume = 1.0;
			u.pitch = 1.0;
			// Pick a voice if available
			const voices = speechSynthesis.getVoices();
			const english = voices.find(v => v.lang.startsWith('en'));
			if (english) u.voice = english;
			u.onerror = (e) => console.warn('[NaviSound] Speech error:', e.error);
			speechSynthesis.speak(u);
		}, 50);
	}
}
