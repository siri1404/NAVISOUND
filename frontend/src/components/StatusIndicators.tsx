import React from 'react';

type ConnectionStatus = 'connected' | 'disconnected' | 'ready';

interface StatusIndicatorsProps {
	connectionStatus: ConnectionStatus;
	confidence: number | null; // 0-1
	hazardCount: number;
	audioEnabled: boolean;
}

/**
 * Accessible status bar showing connection state, confidence level,
 * hazard count, and audio mode.
 */
export const StatusIndicators: React.FC<StatusIndicatorsProps> = ({
	connectionStatus,
	confidence,
	hazardCount,
	audioEnabled,
}) => {
	const connectionColors: Record<ConnectionStatus, string> = {
		connected: '#00cc66',
		disconnected: '#cc3333',
		ready: '#ffaa00',
	};

	const confPct = confidence !== null ? Math.round(confidence * 100) : null;
	const confColor = confPct !== null ? (confPct > 70 ? '#00cc66' : confPct > 40 ? '#ffaa00' : '#cc3333') : '#888';

	const pillStyle: React.CSSProperties = {
		display: 'inline-flex',
		alignItems: 'center',
		gap: 6,
		padding: '6px 12px',
		borderRadius: 20,
		fontSize: 14,
		fontWeight: 600,
		marginRight: 10,
		marginBottom: 6,
	};

	return (
		<div role="status" aria-live="polite" aria-label="System status" style={{ padding: '8px 0' }}>
			{/* Connection */}
			<span
				style={{ ...pillStyle, background: '#222', border: `2px solid ${connectionColors[connectionStatus]}` }}
				aria-label={`Connection: ${connectionStatus}`}
			>
				<span
					style={{
						width: 10,
						height: 10,
						borderRadius: '50%',
						background: connectionColors[connectionStatus],
						display: 'inline-block',
					}}
				/>
				{connectionStatus}
			</span>

			{/* Confidence */}
			{confPct !== null && (
				<span
					style={{ ...pillStyle, background: '#222', border: `2px solid ${confColor}` }}
					aria-label={`Confidence ${confPct} percent`}
				>
					{confPct}%
				</span>
			)}

			{/* Hazards */}
			{hazardCount > 0 && (
				<span
					style={{ ...pillStyle, background: '#441111', border: '2px solid #cc3333', color: '#ff6666' }}
					role="alert"
					aria-label={`${hazardCount} hazards nearby`}
				>
					{hazardCount} hazard{hazardCount > 1 ? 's' : ''}
				</span>
			)}

			{/* Audio mode */}
			<span
				style={{ ...pillStyle, background: '#222', border: '2px solid #555' }}
				aria-label={`Audio ${audioEnabled ? 'enabled' : 'disabled'}`}
			>
				{audioEnabled ? 'Audio ON' : 'Audio OFF'}
			</span>
		</div>
	);
};
