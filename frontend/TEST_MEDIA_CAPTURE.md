# MediaStream Capture Test

## Quick Test

To test camera and microphone permissions in the browser:

### Option 1: Using Python HTTP Server

```bash
cd frontend/public
python -m http.server 8080
```

Then open: http://localhost:8080/test-media-capture.html

### Option 2: Using Node HTTP Server

```bash
cd frontend
npm install
npm run test:media
```

### Option 3: Using VS Code Live Server

1. Install "Live Server" extension in VS Code
2. Right-click `frontend/public/test-media-capture.html`
3. Select "Open with Live Server"

## What to Test

1. **Click "Initialize"** - Browser should prompt for camera + microphone permissions
2. **Click "Start Capture"** - Should see:
   - Video preview from camera
   - Video frame count incrementing (~10 per second)
   - Audio chunk count incrementing
   - FPS around 10
   - Average frame size in KB

3. **Check Console** - Should show no errors
4. **Check Log** - Should show video/audio capture messages

## Expected Results

✅ Camera permission granted  
✅ Microphone permission granted  
✅ Video frames captured at ~10fps  
✅ Audio chunks captured continuously  
✅ Base64 encoding working  
✅ WAV encoding working (16-bit PCM little-endian)

## Troubleshooting

- **HTTPS Required**: Some browsers require HTTPS for media device access. Use `http://localhost` which is allowed.
- **Permissions Denied**: Check browser settings to allow camera/mic for localhost
- **AudioWorklet Not Found**: Ensure `audio-processor.worklet.js` is in the same directory
- **No Video**: Check if another app is using the camera

## Files

- `frontend/src/services/MediaStreamCapture.ts` - Main TypeScript service
- `frontend/public/audio-processor.worklet.js` - AudioWorklet processor
- `frontend/public/test-media-capture.html` - Validation test page
