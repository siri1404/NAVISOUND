import React, { useEffect, useState, useRef, useCallback } from 'react';

interface LandingPageProps {
  onStart: () => void;
}

export const LandingPage: React.FC<LandingPageProps> = ({ onStart }) => {
  const [entered, setEntered] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [listening, setListening] = useState(false);
  const [hint, setHint] = useState('press Enter to begin, or say "start"');
  const recognitionRef = useRef<any>(null);

  // Pre-load voices and announce keyboard instructions on mount
  useEffect(() => {
    if ('speechSynthesis' in window) window.speechSynthesis.getVoices();

    // Announce keyboard instruction to assistive technology users
    const announcer = document.createElement('div');
    announcer.setAttribute('role', 'status');
    announcer.setAttribute('aria-live', 'polite');
    announcer.setAttribute('aria-label', 'Instruction');
    announcer.style.position = 'absolute';
    announcer.style.left = '-10000px';
    announcer.textContent = 'NaviSound. Press Enter to begin, or say start.';
    document.body.appendChild(announcer);

    // Try immediate auto-play (may work if user has interacted or accessibility context)
    tryAutoPlay();

    return () => {
      if ('speechSynthesis' in window) window.speechSynthesis.cancel();
      if (recognitionRef.current) {
        try { recognitionRef.current.abort(); } catch (_) {}
      }
      document.body.removeChild(announcer);
    };
  }, []);

  // Keyboard support for accessibility
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      if ((e.key === 'Enter' || e.key === ' ') && !entered) {
        e.preventDefault();
        handleEnter();
      }
    };
    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, [entered]);

  function tryAutoPlay() {
    if (!('speechSynthesis' in window)) return;
    const synth = window.speechSynthesis;
    
    // Attempt auto-play welcome
    const u = new SpeechSynthesisUtterance(
      'Welcome to NaviSound. Your spatial audio guide awaits. Say start, and we\'ll begin your journey.'
    );
    const voices = synth.getVoices();
    const preferred =
      voices.find((v) => v.lang.startsWith('en') && v.name.toLowerCase().includes('female')) ||
      voices.find((v) => v.lang.startsWith('en')) ||
      voices[0];
    if (preferred) u.voice = preferred;
    u.rate = 0.92;
    u.pitch = 1.05;
    u.volume = 1;

    u.onstart = () => {
      setEntered(true);
      setSpeaking(true);
      setHint('');
    };
    u.onend = () => {
      setSpeaking(false);
      setHint('Say "start" to begin.');
      startListening();
    };

    try { synth.speak(u); } catch (_) {}
  }

  const startListening = useCallback(() => {
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) {
      setHint('Press Enter or say "start"');
      return;
    }

    const recognition = new SR();
    recognition.lang = 'en-US';
    recognition.interimResults = true;
    recognition.continuous = true;
    recognitionRef.current = recognition;

    recognition.onstart = () => setListening(true);

    recognition.onresult = (e: any) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const transcript = e.results[i][0].transcript.toLowerCase().trim();
        if (transcript.includes('start')) {
          recognition.abort();
          setListening(false);
          onStart();
          return;
        }
      }
    };

    recognition.onerror = () => {
      setListening(false);
      setHint('Press Enter or try again');
    };

    recognition.onend = () => {
      setListening(false);
      if (recognitionRef.current) {
        try { recognition.start(); } catch (_) {}
      }
    };

    try { recognition.start(); } catch (_) {}
  }, [onStart]);

  function handleEnter() {
    if (entered) return;
    setEntered(true);

    // Speak welcome via user gesture
    if ('speechSynthesis' in window) {
      const synth = window.speechSynthesis;
      synth.cancel();
      const u = new SpeechSynthesisUtterance(
        'Welcome to NaviSound. Your spatial audio guide awaits. Say start, and we\'ll begin your journey.'
      );
      const voices = synth.getVoices();
      const preferred =
        voices.find((v) => v.lang.startsWith('en') && v.name.toLowerCase().includes('female')) ||
        voices.find((v) => v.lang.startsWith('en')) ||
        voices[0];
      if (preferred) u.voice = preferred;
      u.rate = 0.92;
      u.pitch = 1.05;
      u.volume = 1;

      u.onstart = () => {
        setSpeaking(true);
        setHint('');
      };
      u.onend = () => {
        setSpeaking(false);
        setHint('Say "start" to begin.');
        startListening();
      };
      synth.speak(u);
    } else {
      setHint('Say "start" or press Enter again');
      startListening();
    }
  }

  // Second tap on globe → go to dashboard directly
  function handleGlobeTap() {
    if (!entered) {
      handleEnter();
    } else {
      onStart();
    }
  }

  const globeClass = [
    'globe',
    entered ? 'alive' : '',
    speaking ? 'speaking' : '',
  ].filter(Boolean).join(' ');

  return (
    <div className="landing" onClick={!entered ? handleEnter : undefined}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=Manrope:wght@300;400;500;600&display=swap');

        :root {
          --paper: #f4f1ed;
          --accent: #2e4b5f;
          --line: #d7d1c9;
          --muted: #9a958e;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }

        html, body, #root {
          height: 100%;
          overflow: hidden;
        }

        body {
          background: var(--paper);
          font-family: 'Manrope', 'Segoe UI', sans-serif;
        }

        /* ===== FULL-SCREEN CENTERED LAYOUT ===== */
        .landing {
          width: 100vw;
          height: 100vh;
          display: flex;
          flex-direction: column;
          align-items: center;
          justify-content: center;
          background: var(--paper);
          position: relative;
          cursor: default;
          user-select: none;
          -webkit-user-select: none;
        }

        /* ===== LOGO TOP-CENTER ===== */
        .logo {
          position: absolute;
          top: 18px;
          left: 50%;
          transform: translateX(-50%);
          font-family: 'Syne', 'Manrope', sans-serif;
          font-weight: 700;
          font-size: 20px;
          padding: 10px 22px;
          border-radius: 12px;
          letter-spacing: 4px;
          text-transform: uppercase;
          color: #ff6f3c; /* warm orange */
          background: rgba(255, 255, 255, 0.55);
          border: 1px solid rgba(255, 220, 200, 0.6);
          backdrop-filter: blur(8px);
          -webkit-backdrop-filter: blur(8px);
          z-index: 30;
        }

        /* ===== GLOBE ===== */
        .globe-area {
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .globe {
          width: 300px;
          height: 300px;
          border-radius: 50%;
          cursor: pointer;
          position: relative;
          background:
            radial-gradient(circle at 28% 22%, rgba(255,255,255,0.45), transparent 35%),
            radial-gradient(circle at 68% 28%, #ff8c42, transparent 50%),
            radial-gradient(circle at 30% 68%, #e85d26, transparent 55%),
            radial-gradient(circle at 75% 72%, #ffb347, transparent 50%),
            radial-gradient(circle at 50% 50%, #ff6f3c 0%, #f4a261 35%, #ffcb77 65%, #ffe0a3 90%, transparent 100%);
          backdrop-filter: blur(24px) saturate(170%);
          -webkit-backdrop-filter: blur(24px) saturate(170%);
          border: 1.5px solid rgba(255, 220, 180, 0.5);
          box-shadow:
            0 8px 36px rgba(230, 100, 50, 0.3),
            inset 0 -10px 28px rgba(255, 255, 255, 0.25),
            inset 0 10px 28px rgba(255, 160, 80, 0.2);
          transition: transform 0.4s cubic-bezier(.22,1,.36,1), box-shadow 0.4s ease;
        }

        /* subtle highlight streak */
        .globe::before {
          content: '';
          position: absolute;
          top: 14%;
          left: 18%;
          width: 45%;
          height: 28%;
          border-radius: 50%;
          background: linear-gradient(135deg, rgba(255,255,255,0.65), rgba(255,255,255,0) 80%);
          filter: blur(6px);
          pointer-events: none;
        }

        /* ===== ALIVE STATE — organic drift with heavy distortion ===== */
        .globe.alive {
          animation:
            drift 5s ease-in-out infinite,
            morph 6s ease-in-out infinite,
            shimmer 4s ease-in-out infinite;
        }

        /* ===== SPEAKING STATE — disoriented/agitated wobble ===== */
        .globe.speaking {
          animation:
            speakDrift 2s ease-in-out infinite,
            speakMorph 1.8s ease-in-out infinite,
            shimmer 2s ease-in-out infinite;
        }

        @keyframes drift {
          0%   { transform: translate(0, 0) rotate(0deg); }
          14%  { transform: translate(6px, -8px) rotate(1.5deg); }
          28%  { transform: translate(-8px, 4px) rotate(-2deg); }
          42%  { transform: translate(4px, 10px) rotate(1deg); }
          57%  { transform: translate(-6px, -6px) rotate(-1.5deg); }
          71%  { transform: translate(7px, 3px) rotate(2deg); }
          85%  { transform: translate(-3px, -9px) rotate(-1deg); }
          100% { transform: translate(0, 0) rotate(0deg); }
        }

        @keyframes morph {
          0%   { border-radius: 50%; }
          12%  { border-radius: 42% 58% 55% 45% / 56% 44% 56% 44%; }
          25%  { border-radius: 55% 45% 40% 60% / 44% 56% 42% 58%; }
          37%  { border-radius: 44% 56% 58% 42% / 58% 42% 55% 45%; }
          50%  { border-radius: 58% 42% 44% 56% / 42% 58% 44% 56%; }
          62%  { border-radius: 40% 60% 56% 44% / 55% 45% 58% 42%; }
          75%  { border-radius: 56% 44% 42% 58% / 44% 56% 40% 60%; }
          87%  { border-radius: 45% 55% 58% 42% / 60% 40% 56% 44%; }
          100% { border-radius: 50%; }
        }

        @keyframes speakDrift {
          0%   { transform: translate(0, 0) scale(1) rotate(0deg); }
          10%  { transform: translate(8px, -10px) scale(1.04) rotate(2.5deg); }
          25%  { transform: translate(-10px, 6px) scale(0.96) rotate(-3deg); }
          40%  { transform: translate(6px, 12px) scale(1.03) rotate(2deg); }
          55%  { transform: translate(-8px, -8px) scale(0.97) rotate(-2.5deg); }
          70%  { transform: translate(10px, 4px) scale(1.02) rotate(3deg); }
          85%  { transform: translate(-5px, -11px) scale(0.98) rotate(-1.5deg); }
          100% { transform: translate(0, 0) scale(1) rotate(0deg); }
        }

        @keyframes speakMorph {
          0%   { border-radius: 50%; }
          14%  { border-radius: 38% 62% 58% 42% / 60% 40% 62% 38%; }
          28%  { border-radius: 60% 40% 36% 64% / 38% 62% 40% 60%; }
          42%  { border-radius: 42% 58% 62% 38% / 64% 36% 58% 42%; }
          57%  { border-radius: 62% 38% 40% 60% / 40% 60% 36% 64%; }
          71%  { border-radius: 36% 64% 60% 40% / 58% 42% 64% 36%; }
          85%  { border-radius: 58% 42% 38% 62% / 42% 58% 38% 62%; }
          100% { border-radius: 50%; }
        }

        @keyframes shimmer {
          0%, 100% {
            box-shadow:
              0 8px 36px rgba(230,100,50,0.3),
              inset 0 -10px 28px rgba(255,255,255,0.25),
              inset 0 10px 28px rgba(255,160,80,0.2);
          }
          50% {
            box-shadow:
              0 14px 52px rgba(220,80,30,0.4),
              inset 0 -14px 36px rgba(255,255,255,0.35),
              inset 0 14px 36px rgba(255,140,60,0.25);
          }
        }

        /* ===== HINT TEXT ===== */
        .hint {
          margin-top: 28px;
          font-size: 18px;
          letter-spacing: 1px;
          text-transform: none;
          color: #0b0b0b;
          font-weight: 600;
          opacity: 1;
          transition: opacity 0.3s ease, transform 0.25s ease;
          text-align: center;
          min-height: 24px;
        }

        .hint.hidden { opacity: 0; }

        /* listening pulse ring */
        .listening-ring {
          position: absolute;
          width: 340px;
          height: 340px;
          border-radius: 50%;
          border: 1.5px solid rgba(46, 75, 95, 0.15);
          animation: pulseRing 2s ease-out infinite;
          pointer-events: none;
        }

        @keyframes pulseRing {
          0%   { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(1.25); opacity: 0; }
        }

        /* ===== RESPONSIVE ===== */
        @media (max-width: 600px) {
          .logo { top: 18px; font-size: 16px; padding: 8px 14px; letter-spacing: 3px; }
          .globe { width: 220px; height: 220px; }
          .listening-ring { width: 260px; height: 260px; }
          .hint { font-size: 15px; margin-top: 22px; }
        }

        @media (max-width: 380px) {
          .globe { width: 180px; height: 180px; }
          .listening-ring { width: 220px; height: 220px; }
        }
      `}</style>

      <div className="logo">NAVISOUND</div>

      <div className="globe-area">
        {listening && <div className="listening-ring" />}
        <div className={globeClass} onClick={handleGlobeTap} role="button" tabIndex={0} aria-label="Enter NaviSound" />
      </div>

      <div className={`hint ${!hint ? 'hidden' : ''}`}>{hint}</div>
    </div>
  );
};
