/**
 * SensorCapture — GPS (Geolocation API) + Motion (DeviceOrientation/DeviceMotion)
 *
 * Collects real-time sensor data from the device and packages it for
 * transmission to the backend via WebSocket.
 */

export interface SensorData {
  /** GPS latitude (WGS84) */
  lat: number | null;
  /** GPS longitude (WGS84) */
  lon: number | null;
  /** GPS accuracy in metres */
  accuracy: number | null;
  /** Compass heading in degrees (0-360, null if unavailable) */
  heading: number | null;
  /** Speed in m/s (null if unavailable) */
  speed: number | null;
  /** Device tilt — pitch (beta) in degrees (-180 to 180) */
  pitch: number | null;
  /** Device tilt — roll (gamma) in degrees (-90 to 90) */
  roll: number | null;
  /** Accelerometer X (m/s²) */
  accelX: number | null;
  /** Accelerometer Y (m/s²) */
  accelY: number | null;
  /** Accelerometer Z (m/s²) */
  accelZ: number | null;
  /** Timestamp of most recent reading */
  timestamp: number;
}

export class SensorCapture {
  private watchId: number | null = null;
  private orientationHandler: ((e: DeviceOrientationEvent) => void) | null = null;
  private motionHandler: ((e: DeviceMotionEvent) => void) | null = null;
  private _latest: SensorData = this._empty();
  private _listeners: Array<(data: SensorData) => void> = [];
  private _active = false;

  /** Most recent sensor snapshot */
  get latest(): SensorData {
    return { ...this._latest };
  }

  /** Whether the capture loop is running */
  get active(): boolean {
    return this._active;
  }

  /**
   * Request permissions and start collecting data.
   *
   * On iOS 13+ DeviceOrientationEvent.requestPermission() is required.
   */
  async start(): Promise<void> {
    if (this._active) return;
    this._active = true;

    // --- Geolocation ---
    if ('geolocation' in navigator) {
      this.watchId = navigator.geolocation.watchPosition(
        (pos) => {
          this._latest.lat = pos.coords.latitude;
          this._latest.lon = pos.coords.longitude;
          this._latest.accuracy = pos.coords.accuracy;
          this._latest.heading = pos.coords.heading;
          this._latest.speed = pos.coords.speed;
          this._latest.timestamp = pos.timestamp;
          this._emit();
        },
        (err) => console.warn('[SensorCapture] Geolocation error:', err.message),
        { enableHighAccuracy: true, maximumAge: 2000, timeout: 5000 },
      );
    }

    // --- DeviceOrientation (compass heading + tilt) ---
    // iOS 13+ requires explicit permission
    const DOE = DeviceOrientationEvent as any;
    if (typeof DOE.requestPermission === 'function') {
      try {
        const perm = await DOE.requestPermission();
        if (perm !== 'granted') {
          console.warn('[SensorCapture] DeviceOrientation permission denied');
        }
      } catch (e) {
        console.warn('[SensorCapture] DeviceOrientation permission error:', e);
      }
    }

    this.orientationHandler = (e: DeviceOrientationEvent) => {
      // e.alpha = compass heading on Android; on iOS use webkitCompassHeading
      const heading = (e as any).webkitCompassHeading ?? e.alpha;
      if (heading !== null && heading !== undefined) {
        this._latest.heading = Math.round(heading);
      }
      if (e.beta !== null) this._latest.pitch = Math.round(e.beta * 10) / 10;
      if (e.gamma !== null) this._latest.roll = Math.round(e.gamma * 10) / 10;
      this._latest.timestamp = Date.now();
      this._emit();
    };
    window.addEventListener('deviceorientation', this.orientationHandler, true);

    // --- DeviceMotion (accelerometer) ---
    const DME = DeviceMotionEvent as any;
    if (typeof DME.requestPermission === 'function') {
      try {
        const perm = await DME.requestPermission();
        if (perm !== 'granted') {
          console.warn('[SensorCapture] DeviceMotion permission denied');
        }
      } catch (e) {
        console.warn('[SensorCapture] DeviceMotion permission error:', e);
      }
    }

    this.motionHandler = (e: DeviceMotionEvent) => {
      const acc = e.accelerationIncludingGravity;
      if (acc) {
        this._latest.accelX = acc.x !== null ? Math.round(acc.x * 100) / 100 : null;
        this._latest.accelY = acc.y !== null ? Math.round(acc.y * 100) / 100 : null;
        this._latest.accelZ = acc.z !== null ? Math.round(acc.z * 100) / 100 : null;
      }
      this._latest.timestamp = Date.now();
      this._emit();
    };
    window.addEventListener('devicemotion', this.motionHandler, true);

    console.log('[SensorCapture] Started');
  }

  /** Stop all sensor streams and clean up. */
  stop(): void {
    this._active = false;

    if (this.watchId !== null) {
      navigator.geolocation.clearWatch(this.watchId);
      this.watchId = null;
    }
    if (this.orientationHandler) {
      window.removeEventListener('deviceorientation', this.orientationHandler, true);
      this.orientationHandler = null;
    }
    if (this.motionHandler) {
      window.removeEventListener('devicemotion', this.motionHandler, true);
      this.motionHandler = null;
    }

    this._listeners = [];
    console.log('[SensorCapture] Stopped');
  }

  /** Register a callback that fires on every sensor update. */
  onUpdate(cb: (data: SensorData) => void): () => void {
    this._listeners.push(cb);
    return () => {
      this._listeners = this._listeners.filter((l) => l !== cb);
    };
  }

  /** Check if the browser supports required APIs. */
  static isSupported(): boolean {
    return 'geolocation' in navigator || 'DeviceOrientationEvent' in window;
  }

  // --- internal ---

  private _emit(): void {
    const snapshot = { ...this._latest };
    for (const cb of this._listeners) {
      try {
        cb(snapshot);
      } catch {
        // isolate listener errors
      }
    }
  }

  private _empty(): SensorData {
    return {
      lat: null,
      lon: null,
      accuracy: null,
      heading: null,
      speed: null,
      pitch: null,
      roll: null,
      accelX: null,
      accelY: null,
      accelZ: null,
      timestamp: Date.now(),
    };
  }
}
