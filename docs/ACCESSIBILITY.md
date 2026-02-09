# Accessibility

NaviSound is designed for blind and low-vision users. Every UI element and interaction follows WCAG 2.1 AA guidelines.

## Screen Reader Support

- All navigation guidance lives inside `aria-live="polite"` regions so changes are announced automatically.
- Hazard warnings use `aria-live="assertive"` with `role="alert"` to interrupt and announce immediately.
- Every interactive element has an `aria-label` describing its function.
- The top-level `<main>` carries `role="main"` and `aria-label="NaviSound Navigation Interface"`.

## Keyboard Navigation

| Key | Action |
|-----|--------|
| **Space** | Read current scene aloud (direction, confidence, hazard count) |
| **Q** | Ask "Where am I?" — sends a `text_query` to the backend |
| **H** | Announce hazard summary |
| **M** | Toggle audio/text mode |

All keyboard shortcuts work without modifier keys so they're easy to hit without looking.

## Spatial Audio

- Uses the Web Audio API **HRTF panning model** to place directional cues in 3D space around the user's head.
- Distance is encoded as volume attenuation (inverse distance model).
- Hazard type maps to distinct frequencies:
  - Furniture: 400 Hz
  - Person: 800 Hz
  - Vehicle: 200 Hz
  - Stairs: 1200 Hz
  - General warning: 1000 Hz
- Audio cues are short (200ms) to avoid masking speech synthesis output.

## Speech Synthesis

- `SpeechSynthesisUtterance` delivers longer text descriptions (scene summary, routing instructions).
- Rate set to 1.1x for slightly faster delivery preferred by experienced screen reader users.
- Speech is only triggered when `audioEnabled` is true, and can be toggled with **M**.

## High Contrast UI

- Default dark theme (background `#1a1a1a`, text `#ffffff`) meets 4.5:1 contrast ratio.
- Hazard badges use red (`#cc0000`) for high urgency and amber (`#ffaa00`) for medium, both on dark backgrounds.
- Direction display uses large text (28px bold) centered on a blue (`#0066cc`) background.

## Testing Protocol

See [USER_TESTING_PROTOCOL.md](USER_TESTING_PROTOCOL.md) for the beta testing procedure with blind participants including SUS and NPS scoring.
