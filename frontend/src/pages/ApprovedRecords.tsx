import { useEffect, useState } from 'react';
import api from '../services/api';
import DataTable from '../components/DataTable';
import StatusBadge from '../components/StatusBadge';
import type { NormalizedRecord } from '../types';

export default function ApprovedRecords() {
  const [records, setRecords] = useState<NormalizedRecord[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchRecords = async () => {
    try {
      const response = await api.get('/review/approved/');
      setRecords(response.data);
    } catch (error) {
      console.error("Error fetching approved records", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRecords();
  }, []);

  const columns = [
    { header: 'ID', accessor: 'id' as const },
    { header: 'Type', accessor: 'activity_type' as const },
    { header: 'Value', accessor: (r: NormalizedRecord) => `${r.normalized_value} ${r.normalized_unit}` },
    { header: 'Date', accessor: 'activity_date' as const },
    { header: 'Score', accessor: 'confidence_score' as const },
    { 
      header: 'Status', 
      accessor: (r: NormalizedRecord) => <StatusBadge status={r.approval_status} /> 
    }
  ];

  if (loading) return <div>Loading...</div>;

  return (
    <div>
      <h1>Approved Records</h1>
      <p style={{ color: 'var(--text-secondary)', marginBottom: '1.5rem' }}>
        These records have been reviewed and committed to the immutable ledger. They cannot be edited.
      </p>
      <DataTable 
        columns={columns} 
        data={records} 
        searchFields={['activity_type', 'normalized_unit', 'activity_date']} 
      />
    </div>
  );
}
