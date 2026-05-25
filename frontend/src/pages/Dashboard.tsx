import { useEffect, useState } from 'react';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from 'recharts';
import api from '../services/api';

const COLORS = ['#2563eb', '#16a34a', '#dc2626', '#eab308'];

export default function Dashboard() {
  const [stats, setStats] = useState({
    pending: 0,
    suspicious: 0,
    approved: 0,
    totalUploads: 0
  });

  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // In a real app, there would be a dedicated analytics endpoint.
    // For this MVP, we fetch the review endpoints and count the array length.
    const fetchDashboardStats = async () => {
      try {
        const [pendingRes, suspRes, approvedRes] = await Promise.all([
          api.get('/review/pending/').catch(() => ({ data: [] })),
          api.get('/review/suspicious/').catch(() => ({ data: [] })),
          api.get('/review/approved/').catch(() => ({ data: [] }))
        ]);

        setStats({
          pending: pendingRes.data.length,
          suspicious: suspRes.data.length,
          approved: approvedRes.data.length,
          totalUploads: 15 // Mock data for uploads
        });
      } catch (err) {
        console.error("Dashboard fetch error", err);
      } finally {
        setLoading(false);
      }
    };

    fetchDashboardStats();
  }, []);

  if (loading) return <div>Loading...</div>;

  const pieData = [
    { name: 'Pending', value: stats.pending },
    { name: 'Approved', value: stats.approved },
    { name: 'Suspicious', value: stats.suspicious },
  ];

  const barData = [
    { month: 'Jan', emissions: 4000 },
    { month: 'Feb', emissions: 3000 },
    { month: 'Mar', emissions: 2000 },
    { month: 'Apr', emissions: 2780 },
    { month: 'May', emissions: 1890 },
    { month: 'Jun', emissions: 2390 },
  ];

  return (
    <div>
      <h1>Analyst Dashboard</h1>
      
      <div className="dashboard-grid">
        <div className="card metric-card">
          <span className="metric-title">Pending Reviews</span>
          <span className="metric-value">{stats.pending}</span>
        </div>
        <div className="card metric-card">
          <span className="metric-title">Suspicious Records</span>
          <span className="metric-value" style={{ color: 'var(--danger-text)' }}>{stats.suspicious}</span>
        </div>
        <div className="card metric-card">
          <span className="metric-title">Approved Records</span>
          <span className="metric-value" style={{ color: 'var(--success-text)' }}>{stats.approved}</span>
        </div>
        <div className="card metric-card">
          <span className="metric-title">Total Upload Batches</span>
          <span className="metric-value">{stats.totalUploads}</span>
        </div>
      </div>

      <div className="dashboard-grid" style={{ gridTemplateColumns: '2fr 1fr' }}>
        <div className="card">
          <h2>Emissions Trend (YTD)</h2>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
              <BarChart data={barData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="month" axisLine={false} tickLine={false} />
                <YAxis axisLine={false} tickLine={false} />
                <Tooltip cursor={{fill: 'var(--bg-primary)'}} />
                <Bar dataKey="emissions" fill="var(--primary-color)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="card">
          <h2>Records by Status</h2>
          <div style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer>
              <PieChart>
                <Pie
                  data={pieData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={80}
                  paddingAngle={5}
                  dataKey="value"
                >
                  {pieData.map((_, index) => (
                    <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
}
