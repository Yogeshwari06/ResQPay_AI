import React from 'react';
import { Link } from 'react-router-dom';
import '../styles.css';

const Navbar = () => {
    return (
        <nav className="navbar">
            <div className="navbar-brand">
                <h1>ResQPay AI</h1>
            </div>
            <ul className="navbar-links">
                <li><Link to="/">Dashboard</Link></li>
                <li><Link to="/alerts">Alerts</Link></li>
                <li><Link to="/incidents">Incident Management</Link></li>
                <li><Link to="/campaigns">Relief Campaigns</Link></li>
                <li><Link to="/donations">Donations</Link></li>
                <li><Link to="/settings">Settings</Link></li>
            </ul>
        </nav>
    );
};

export default Navbar;
