import { useEffect, useState } from 'react';
import api from '../services/api';
import DataTable from '../components/DataTable';
import StatusBadge from '../components/StatusBadge';
import type { NormalizedRecord } from '../types';
import { CheckCircle, XCircle } from 'lucide-react';

export default function PendingReview() {
  const [records, setRecords] = useState<NormalizedRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchRecords = async () => {
    try {
      const response = await api.get('/review/pending/');
      setRecords(response.data);
    } catch (error) {
      console.error("Error fetching pending records", error);
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
    { header: 'Score', accessor: 'confidence_score' as const },
    { 
      header: 'Status', 
      accessor: (r: NormalizedRecord) => <StatusBadge status={r.approval_status} /> 
    },
    {
      header: 'Actions',
      accessor: (r: NormalizedRecord) => (
        <div className="action-buttons">
          <button className="btn btn-success" onClick={() => handleApprove(r.id)} title="Approve">
            <CheckCircle size={16} />
          </button>
          <button className="btn btn-danger" onClick={() => handleReject(r.id)} title="Reject">
            <XCircle size={16} />
          </button>
        </div>
      )
    }
  ];

  if (loading) return <div>Loading...</div>;

  return (
    <div>
      <h1>Pending Review</h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
        Review and approve standardized ESG records before they enter the general ledger.
      </p>
      <DataTable 
        columns={columns} 
        data={records} 
        searchFields={['activity_type', 'normalized_unit', 'activity_date']} 
      />
    </div>
  );
}
