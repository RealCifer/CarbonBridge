import { NavLink, Outlet } from 'react-router-dom';
import { LayoutDashboard, Upload, Clock, AlertTriangle, CheckCircle, Leaf } from 'lucide-react';

export default function Layout() {
  return (
    <div className="app-container">
      {/* Sidebar */}
      <aside className="sidebar">
        <div className="sidebar-header">
          <Leaf className="text-green-400" /> {/* Just an icon */}
          CarbonBridge
        </div>
        <nav className="sidebar-nav">
          <NavLink to="/" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"} end>
            <LayoutDashboard size={20} />
            Dashboard
          </NavLink>
          <NavLink to="/uploads" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <Upload size={20} />
            Uploads
          </NavLink>
          <NavLink to="/pending" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <Clock size={20} />
            Pending Review
          </NavLink>
          <NavLink to="/suspicious" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <AlertTriangle size={20} />
            Suspicious Records
          </NavLink>
          <NavLink to="/approved" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>
            <CheckCircle size={20} />
            Approved Records
          </NavLink>
        </nav>
      </aside>

      {/* Main Content Area */}
      <main className="main-content">
        <header className="top-header">
          <div className="search-bar">
            {/* Global Search Placeholder */}
            <input type="text" placeholder="Search..." className="search-input" />
          </div>
          <div className="user-profile">
            <div className="badge info">Analyst</div>
          </div>
        </header>

        <section className="page-content">
          <Outlet />
        </section>
      </main>
    </div>
  );
}
