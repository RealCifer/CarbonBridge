import { useState, useEffect } from 'react';
import axios from 'axios';
import { 
  Activity, 
  Leaf, 
  Users, 
  ShieldCheck, 
  RefreshCw, 
  AlertTriangle, 
  CheckCircle,
  TrendingUp,
  TrendingDown,
  Globe,
  Database
} from 'lucide-react';

interface HealthResponse {
  status: string;
}

function App() {
  const [healthStatus, setHealthStatus] = useState<'connected' | 'disconnected' | 'loading'>('loading');
  const [healthData, setHealthData] = useState<HealthResponse | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [errorDetails, setErrorDetails] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);

  const checkBackendHealth = async () => {
    setIsRefreshing(true);
    setHealthStatus('loading');
    const startTime = performance.now();
    
    try {
      // Direct request to Django backend running on localhost:8000
      const response = await axios.get<HealthResponse>('http://localhost:8000/api/health/', {
        timeout: 5000 // 5 seconds timeout
      });
      
      const endTime = performance.now();
      setLatency(Math.round(endTime - startTime));
      setHealthData(response.data);
      
      if (response.data.status === 'ok') {
        setHealthStatus('connected');
        setErrorDetails(null);
      } else {
        setHealthStatus('disconnected');
        setErrorDetails('Invalid status response from server');
      }
    } catch (error: any) {
      setHealthStatus('disconnected');
      setHealthData(null);
      setLatency(null);
      if (error.response) {
        setErrorDetails(`Server Error: ${error.response.status} ${error.response.statusText}`);
      } else if (error.request) {
        setErrorDetails('No response from backend server. Make sure your Django backend is running on http://localhost:8000');
      } else {
        setErrorDetails(`Request setup error: ${error.message}`);
      }
    } finally {
      setIsRefreshing(false);
    }
  };

  useEffect(() => {
    checkBackendHealth();
  }, []);

  return (
    <>
      {/* Platform Header */}
      <header className="header">
        <div className="logo-container">
          <div className="logo-icon">
            <Leaf className="text-white" size={24} />
          </div>
          <h1 className="logo-text">CarbonBridge</h1>
        </div>
        <div className={`health-badge ${healthStatus}`}>
          <span className="pulse-dot"></span>
          {healthStatus === 'connected' && 'API Active'}
          {healthStatus === 'disconnected' && 'API Offline'}
          {healthStatus === 'loading' && 'Checking API...'}
        </div>
      </header>

      {/* Hero & Intro */}
      <section className="hero-section">
        <h2 className="hero-title">
          CarbonBridge <span>ESG Platform</span>
        </h2>
        <p className="hero-subtitle">
          Bridging the gap between ecological responsibility and corporate transparency. 
          CarbonBridge monitors, aggregates, and reports your Environmental, Social, and Governance metrics in real-time.
        </p>
      </section>

      {/* ESG Mock Metrics Grid */}
      <section className="dashboard-grid">
        {/* Environmental Card */}
        <div className="glass-panel metric-card e-metric">
          <div className="metric-header">
            <span>ENVIRONMENTAL</span>
            <Leaf size={20} className="text-emerald-500" style={{ color: '#10b981' }} />
          </div>
          <div className="panel-title">Net Carbon Intensity</div>
          <div className="metric-value">24.8 tCO₂e</div>
          <div className="metric-trend down">
            <TrendingDown size={16} />
            <span>-12.4% vs last Q</span>
          </div>
        </div>

        {/* Social Card */}
        <div className="glass-panel metric-card s-metric">
          <div className="metric-header">
            <span>SOCIAL</span>
            <Users size={20} className="text-blue-500" style={{ color: '#3b82f6' }} />
          </div>
          <div className="panel-title">Diversity & Inclusion</div>
          <div className="metric-value">86.4%</div>
          <div className="metric-trend up">
            <TrendingUp size={16} />
            <span>+4.2% YoY growth</span>
          </div>
        </div>

        {/* Governance Card */}
        <div className="glass-panel metric-card g-metric">
          <div className="metric-header">
            <span>GOVERNANCE</span>
            <ShieldCheck size={20} className="text-purple-500" style={{ color: '#8b5cf6' }} />
          </div>
          <div className="panel-title">Compliance Index</div>
          <div className="metric-value">99.8%</div>
          <div className="metric-trend up">
            <TrendingUp size={16} />
            <span>Excellent standing</span>
          </div>
        </div>

        {/* Backend Integration & Health Center */}
        <div className="glass-panel health-center-panel">
          <div className="health-status-info">
            <span className="health-status-label">System Health Center</span>
            
            <div className="health-status-value">
              {healthStatus === 'connected' && (
                <>
                  <CheckCircle size={28} style={{ color: '#10b981' }} />
                  <span style={{ color: '#10b981' }}>Connected</span>
                </>
              )}
              {healthStatus === 'disconnected' && (
                <>
                  <AlertTriangle size={28} style={{ color: '#ef4444' }} />
                  <span style={{ color: '#ef4444' }}>Service Interrupted</span>
                </>
              )}
              {healthStatus === 'loading' && (
                <>
                  <Activity size={28} className="animate-pulse" style={{ color: '#3b82f6' }} />
                  <span style={{ color: '#3b82f6' }}>Connecting...</span>
                </>
              )}
            </div>

            {healthStatus === 'connected' && healthData && (
              <div style={{ marginTop: '0.5rem', fontSize: '0.9rem', color: 'var(--text-secondary)' }}>
                <div>Backend returned status: <span className="api-endpoint-badge">{healthData.status}</span></div>
                {latency !== null && <div style={{ marginTop: '0.25rem' }}>Response Latency: <span style={{ color: '#10b981', fontWeight: 600 }}>{latency}ms</span></div>}
              </div>
            )}

            {healthStatus === 'disconnected' && errorDetails && (
              <div style={{ marginTop: '0.5rem', fontSize: '0.9rem', color: '#ef4444' }}>
                <strong>Details:</strong> {errorDetails}
              </div>
            )}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', alignItems: 'flex-start' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem', color: 'var(--text-muted)' }}>
              <Database size={14} />
              <span>Target: <span className="api-endpoint-badge">/api/health/</span></span>
            </div>
            
            <button 
              className="btn-refresh" 
              onClick={checkBackendHealth} 
              disabled={isRefreshing}
            >
              <RefreshCw size={16} className={isRefreshing ? 'animate-spin-slow' : ''} />
              {isRefreshing ? 'Re-Checking...' : 'Check Connection'}
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer">
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <Globe size={16} />
          <span>CarbonBridge ESG Protocol — Seed Node Alpha v1.0.0</span>
        </div>
        <p>&copy; {new Date().getFullYear()} CarbonBridge. Empowering sustainable corporate transitions.</p>
      </footer>
    </>
  );
}

export default App;
