import { useEffect, useState } from 'react';
import api from '../services/api';
import DataTable from '../components/DataTable';
import type { NormalizedRecord } from '../types';
import { CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

export default function SuspiciousRecords() {
  const [records, setRecords] = useState<NormalizedRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchRecords = async () => {
    try {
      const response = await api.get('/review/suspicious/');
      setRecords(response.data);
    } catch (error) {
      console.error("Error fetching suspicious records", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRecords();
  }, []);

  const handleApprove = async (id: number) => {
    try {
      await api.post('/review/approve/', { record_id: id });
      fetchRecords();
    } catch (err) {
      console.error("Approve failed", err);
    }
  };

  const handleReject = async (id: number) => {
    try {
      await api.post('/review/reject/', { record_id: id });
      fetchRecords();
    } catch (err) {
      console.error("Reject failed", err);
    }
  };

  const columns = [
    { header: 'ID', accessor: 'id' as const },
    { header: 'Type', accessor: 'activity_type' as const },
    { header: 'Value', accessor: (r: NormalizedRecord) => `${r.normalized_value} ${r.normalized_unit}` },
    { header: 'Date', accessor: 'activity_date' as const },
    { 
      header: 'Score', 
      accessor: (r: NormalizedRecord) => (
        <span style={{ color: 'var(--danger-text)', fontWeight: 600 }}>
          {r.confidence_score}
        </span>
      ) 
    },
    { 
      header: 'Warning', 
      accessor: () => (
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', color: 'var(--danger-text)' }}>
          <AlertTriangle size={16} />
          Flagged by System
        </div>
      ) 
    },
    {
      header: 'Actions',
      accessor: (r: NormalizedRecord) => (
        <div className="action-buttons">
          <button className="btn btn-success" onClick={() => handleApprove(r.id)} title="Approve">
            <CheckCircle size={16} /> Force Approve
          </button>
          <button className="btn btn-danger" onClick={() => handleReject(r.id)} title="Reject">
            <XCircle size={16} /> Reject
          </button>
        </div>
      )
    }
  ];

  if (loading) return <div>Loading...</div>;

  return (
    <div>
      <h1>Suspicious Records</h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
        Records flagged with a low confidence score due to missing data or historical anomalies.
      </p>
      <DataTable 
        columns={columns} 
        data={records} 
        searchFields={['activity_type', 'normalized_unit']} 
      />
    </div>
  );
}
