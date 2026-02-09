# NaviSound Beta Testing Protocol

## Participant Requirements
- Legally blind or low vision
- Age 18+
- No prior NaviSound use
- Consent to record video/audio
- $25 incentive

## Testing Environment
- Indoor room with ~200 sq ft space
- Pre-placed obstacles: 2 chairs, 1 box, 1 table
- Clear path from start to 3 destination objects (cone, bell, door handle)
- Good lighting (no dark room testing on Day 1)

## Tasks (20 minutes)
1. **Calibration (3 min)**: User holds phone normally, hears sample cues
2. **Guided Route (5 min)**: Navigate to orange cone while listening to directions
3. **Free Exploration (5 min)**: Explore room, ask "Where am I?" queries
4. **Hazard Avoidance (4 min)**: Navigate to bell while avoiding obstacles
5. **Post-Test Survey (3 min)**: Confidence score, usability, likelihood to use

## Metrics Collected
- Task completion: Y/N for each route
- Errors: Number of collisions with obstacles
- Navigation time: Seconds per route
- SUS Score: Standardized usability (0-100)
- NPS: "Likelihood to recommend" (0-10)
- Open feedback: Record user's own words

## User Testing Execution (Days 6-7)
- Run the 20-minute session per participant.
- Aim for 3-4 participants on Day 6 (beta), iterate fixes on Day 7 morning.

## Iteration Guidance
Most likely issues (Day 6): Audio too quiet, directions confusing, latency noticeable

Fixes to implement (Day 7 morning):
- If too quiet: Increase system audio volume parameter in the audio engine
- If confusing: Add confirmation phrasing (e.g., "Moving forward, 8 feet") before directional cue
- If latency noticeable: Reduce video to 5fps, increase frame buffer

## Day 6 Deliverable
- 3-4 real users tested
- Metrics documented (CSV export)
- Critical bugs fixed and confidence scores improved


---
Notes:
- Ensure consent and safety checks are performed before testing.
- Record qualitative feedback (short voice memo) to capture phrasing issues.
