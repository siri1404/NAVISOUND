/**
 * MediaStreamCapture - Browser camera + microphone capture service
 * 
 * Features:
 * - Video: 10fps frame capture (every 100ms) as base64 JPEG
 * - Audio: continuous Float32 PCM stream via AudioWorklet
 * - WAV encoding: little-endian 16-bit PCM
 */

export interface MediaFrame {
  type: 'video' | 'audio';
  data: string; // base64 encoded
  timestamp: number;
  metadata?: {
    width?: number;
    height?: number;
    sampleRate?: number;
    channels?: number;
  };
}

export interface MediaStreamConfig {
  video?: {
    width?: number;
    height?: number;
    frameRate?: number;
  };
  audio?: {
    sampleRate?: number;
    channelCount?: number;
  };
}

export class MediaStreamCapture {
  private videoStream: MediaStream | null = null;
  private audioStream: MediaStream | null = null;
  private videoElement: HTMLVideoElement | null = null;
  private canvas: HTMLCanvasElement | null = null;
  private ctx: CanvasRenderingContext2D | null = null;
  private audioContext: AudioContext | null = null;
  private audioWorkletNode: AudioWorkletNode | null = null;
  private frameIntervalId: number | null = null;
  private onFrameCallback: ((frame: MediaFrame) => void) | null = null;
  private isCapturing = false;

  constructor(private config: MediaStreamConfig = {}) {
    this.config.video = {
      width: 640,
      height: 480,
      frameRate: 10,
      ...config.video,
    };
    this.config.audio = {
      sampleRate: 16000,
      channelCount: 1,
      ...config.audio,
    };
  }

  /**
   * Initialize camera and microphone streams
   */
  async initialize(): Promise<void> {
    try {
      // Request video stream
      if (this.config.video) {
        this.videoStream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: this.config.video.width },
            height: { ideal: this.config.video.height },
            frameRate: { ideal: this.config.video.frameRate },
          },
        });

        // Setup video element and canvas for frame extraction
        this.videoElement = document.createElement('video');
        this.videoElement.srcObject = this.videoStream;
        this.videoElement.autoplay = true;
        this.videoElement.muted = true;

        await new Promise((resolve) => {
          this.videoElement!.onloadedmetadata = resolve;
        });

        this.canvas = document.createElement('canvas');
        this.canvas.width = this.config.video.width!;
        this.canvas.height = this.config.video.height!;
        this.ctx = this.canvas.getContext('2d');
      }

      // Request audio stream
      if (this.config.audio) {
        this.audioStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            sampleRate: this.config.audio.sampleRate,
            channelCount: this.config.audio.channelCount,
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true,
          },
        });

        // Setup AudioContext and AudioWorklet
        this.audioContext = new AudioContext({
          sampleRate: this.config.audio.sampleRate,
        });

        // Load audio processor worklet
        await this.audioContext.audioWorklet.addModule(
          '/audio-processor.worklet.js'
        );

        const source = this.audioContext.createMediaStreamSource(this.audioStream);
        this.audioWorkletNode = new AudioWorkletNode(
          this.audioContext,
          'audio-processor'
        );

        // Listen for processed audio chunks
        this.audioWorkletNode.port.onmessage = (event) => {
          if (event.data.type === 'audio-chunk') {
            this.handleAudioChunk(event.data.samples);
          }
        };

        source.connect(this.audioWorkletNode);
        this.audioWorkletNode.connect(this.audioContext.destination);
      }

      console.log('MediaStreamCapture initialized successfully');
    } catch (error) {
      console.error('Failed to initialize MediaStreamCapture:', error);
      throw error;
    }
  }

  /**
   * Start capturing frames
   */
  startCapture(onFrame: (frame: MediaFrame) => void): void {
    if (this.isCapturing) {
      console.warn('Capture already in progress');
      return;
    }

    this.onFrameCallback = onFrame;
    this.isCapturing = true;

    // Start video frame capture at 10fps (every 100ms)
    if (this.videoStream && this.videoElement && this.canvas && this.ctx) {
      this.frameIntervalId = window.setInterval(() => {
        this.captureVideoFrame();
      }, 100); // 10fps
    }

    console.log('MediaStreamCapture started');
  }

  /**
   * Stop capturing
   */
  stopCapture(): void {
    if (!this.isCapturing) return;

    this.isCapturing = false;

    if (this.frameIntervalId !== null) {
      clearInterval(this.frameIntervalId);
      this.frameIntervalId = null;
    }

    console.log('MediaStreamCapture stopped');
  }

  /**
   * Cleanup resources
   */
  destroy(): void {
    this.stopCapture();

    if (this.videoStream) {
      this.videoStream.getTracks().forEach((track) => track.stop());
      this.videoStream = null;
    }

    if (this.audioStream) {
      this.audioStream.getTracks().forEach((track) => track.stop());
      this.audioStream = null;
    }

    if (this.audioWorkletNode) {
      this.audioWorkletNode.disconnect();
      this.audioWorkletNode = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }

    this.videoElement = null;
    this.canvas = null;
    this.ctx = null;
    this.onFrameCallback = null;

    console.log('MediaStreamCapture destroyed');
  }

  /**
   * Capture a single video frame and emit as base64 JPEG
   */
  private captureVideoFrame(): void {
    if (!this.videoElement || !this.canvas || !this.ctx || !this.onFrameCallback) {
      return;
    }

    try {
      // Draw current video frame to canvas
      this.ctx.drawImage(this.videoElement, 0, 0, this.canvas.width, this.canvas.height);

      // Convert canvas to base64 JPEG
      const base64 = this.canvas.toDataURL('image/jpeg', 0.8).split(',')[1];

      const frame: MediaFrame = {
        type: 'video',
        data: base64,
        timestamp: Date.now(),
        metadata: {
          width: this.canvas.width,
          height: this.canvas.height,
        },
      };

      this.onFrameCallback(frame);
    } catch (error) {
      console.error('Failed to capture video frame:', error);
    }
  }

  /**
   * Handle audio chunk from AudioWorklet and convert to WAV base64
   */
  private handleAudioChunk(samples: Float32Array): void {
    if (!this.onFrameCallback) return;

    try {
      // Convert Float32 PCM to 16-bit PCM WAV
      const wavBase64 = this.encodeWAV(samples);

      const frame: MediaFrame = {
        type: 'audio',
        data: wavBase64,
        timestamp: Date.now(),
        metadata: {
          sampleRate: this.config.audio?.sampleRate,
          channels: this.config.audio?.channelCount,
        },
      };

      this.onFrameCallback(frame);
    } catch (error) {
      console.error('Failed to handle audio chunk:', error);
    }
  }

  /**
   * Encode Float32 PCM samples to WAV base64
   * Format: 16-bit little-endian PCM
   */
  private encodeWAV(samples: Float32Array): string {
    const sampleRate = this.config.audio?.sampleRate || 16000;
    const numChannels = this.config.audio?.channelCount || 1;
    const bitsPerSample = 16;
    const bytesPerSample = bitsPerSample / 8;

    // Convert Float32 [-1, 1] to Int16 [-32768, 32767]
    const int16Samples = new Int16Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      const s = Math.max(-1, Math.min(1, samples[i]));
      int16Samples[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }

    const dataLength = int16Samples.length * bytesPerSample;
    const buffer = new ArrayBuffer(44 + dataLength);
    const view = new DataView(buffer);

    // WAV header
    let offset = 0;

    // "RIFF" chunk descriptor
    this.writeString(view, offset, 'RIFF');
    offset += 4;
    view.setUint32(offset, 36 + dataLength, true); // file size - 8
    offset += 4;
    this.writeString(view, offset, 'WAVE');
    offset += 4;

    // "fmt " sub-chunk
    this.writeString(view, offset, 'fmt ');
    offset += 4;
    view.setUint32(offset, 16, true); // sub-chunk size
    offset += 4;
    view.setUint16(offset, 1, true); // audio format (1 = PCM)
    offset += 2;
    view.setUint16(offset, numChannels, true);
    offset += 2;
    view.setUint32(offset, sampleRate, true);
    offset += 4;
    view.setUint32(offset, sampleRate * numChannels * bytesPerSample, true); // byte rate
    offset += 4;
    view.setUint16(offset, numChannels * bytesPerSample, true); // block align
    offset += 2;
    view.setUint16(offset, bitsPerSample, true);
    offset += 2;

    // "data" sub-chunk
    this.writeString(view, offset, 'data');
    offset += 4;
    view.setUint32(offset, dataLength, true);
    offset += 4;

    // Write PCM samples as little-endian 16-bit
    for (let i = 0; i < int16Samples.length; i++) {
      view.setInt16(offset, int16Samples[i], true);
      offset += 2;
    }

    // Convert to base64
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  /**
   * Write ASCII string to DataView
   */
  private writeString(view: DataView, offset: number, str: string): void {
    for (let i = 0; i < str.length; i++) {
      view.setUint8(offset + i, str.charCodeAt(i));
    }
  }

  /**
   * Check if browser supports required APIs
   */
  static isSupported(): boolean {
    return !!(
      navigator.mediaDevices &&
      typeof navigator.mediaDevices.getUserMedia === 'function' &&
      window.AudioContext &&
      'audioWorklet' in AudioContext.prototype
    );
  }
}
