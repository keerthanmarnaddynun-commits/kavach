import React, { useState } from 'react';
import LandingPage from './components/LandingPage';
import TerminalWorkspace from './components/TerminalWorkspace';

export default function App() {
  const [currentView, setCurrentView] = useState('landing');

  return (
    <div className="w-full min-h-screen bg-black">
      {currentView === 'landing' ? (
        <LandingPage onLaunchTerminal={() => setCurrentView('terminal')} />
      ) : (
        <TerminalWorkspace onBackToLanding={() => setCurrentView('landing')} />
      )}
    </div>
  );
}

