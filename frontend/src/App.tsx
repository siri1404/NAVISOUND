import React, { useState } from 'react';
import { LandingPage } from './components/LandingPage';
import { NavigationUI } from './components/NavigationUI';

export const App: React.FC = () => {
	const [started, setStarted] = useState(false);

	if (started) {
		return <NavigationUI />;
	}

	return <LandingPage onStart={() => setStarted(true)} />;
};
