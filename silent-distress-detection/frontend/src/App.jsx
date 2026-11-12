import React from 'react';
import { Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Dashboard from './pages/Dashboard';
import Alerts from './pages/Alerts';
import IncidentDashboard from './pages/IncidentDashboard';
import Settings from './pages/Settings';
import Campaigns from './pages/Campaigns';
import Donations from './pages/Donations';
import './styles.css';

const App = () => {
  return (
    <div className="app">
      <Navbar />
      <div className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/alerts" element={<Alerts />} />
          <Route path="/incidents" element={<IncidentDashboard />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/campaigns" element={<Campaigns />} />
          <Route path="/donations" element={<Donations />} />
        </Routes>
      </div>
    </div>
  );
};

export default App;
