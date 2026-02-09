import React from 'react';

interface AudioVisualizerProps {
	direction: string;      // e.g. "forward-left", "right"
	distance: number;       // feet
	confidence: number;     // 0-1
	hazardCount: number;
}

/**
 * Renders an accessible top-down spatial map showing the user's
 * current direction, distance, and nearby hazard density.
 */
export const SpatialAudioVisualizer: React.FC<AudioVisualizerProps> = ({
	direction,
	distance,
	confidence,
	hazardCount,
}) => {
	// Map direction string to angle (degrees clockwise from top/forward)
	const angleMap: Record<string, number> = {
		forward: 0,
		'forward-right': 45,
		right: 90,
		'back-right': 135,
		back: 180,
		'back-left': 225,
		left: 270,
		'forward-left': 315,
	};

	const angle = angleMap[direction] ?? 0;
	const rad = (angle * Math.PI) / 180;
	const radius = Math.min(distance, 20) * 3; // scale to pixels, cap at 20ft
	const arrowX = 60 + Math.sin(rad) * radius;
	const arrowY = 60 - Math.cos(rad) * radius;

	const confidenceColor = confidence > 0.7 ? '#00cc66' : confidence > 0.4 ? '#ffaa00' : '#cc3333';

	return (
		<section
			aria-label={`Spatial map: direction ${direction}, ${distance} feet, confidence ${Math.round(confidence * 100)}%`}
			style={{ width: 140, height: 140, position: 'relative', margin: '12px auto' }}
		>
			<svg width="140" height="140" viewBox="0 0 120 120" role="img" aria-hidden="true">
				{/* Background circle */}
				<circle cx="60" cy="60" r="55" fill="#222" stroke="#555" strokeWidth="1" />
				{/* Confidence ring */}
				<circle cx="60" cy="60" r="55" fill="none" stroke={confidenceColor} strokeWidth="3" opacity={0.6} />
				{/* Center dot = user */}
				<circle cx="60" cy="60" r="4" fill="#ffffff" />
				{/* Direction arrow */}
				<line x1="60" y1="60" x2={arrowX} y2={arrowY} stroke="#00aaff" strokeWidth="3" strokeLinecap="round" />
				<circle cx={arrowX} cy={arrowY} r="5" fill="#00aaff" />
				{/* Hazard indicator */}
				{hazardCount > 0 && (
					<text x="100" y="18" fill="#ff4444" fontSize="14" fontWeight="bold" textAnchor="middle">
						{hazardCount}
					</text>
				)}
			</svg>
		</section>
	);
};
