import { useEffect, useState } from 'react';
import api from '../services/api';
import DataTable from '../components/DataTable';
import StatusBadge from '../components/StatusBadge';
import type { UploadBatch } from '../types';

export default function Uploads() {
  const [batches, setBatches] = useState<UploadBatch[]>([]);
  const [loading, setLoading] = useState(true);
  const [file, setFile] = useState<File | null>(null);
  const [sourceType, setSourceType] = useState('sap');
  const [uploading, setUploading] = useState(false);

  const fetchBatches = async () => {
    try {
      // Assuming a generic endpoint to list batches, though one might not exist yet.
      // We will mock it or try to fetch from an existing one if available.
      const response = await api.get('/upload/batches/').catch(() => ({ data: [] }));
      setBatches(response.data);
    } catch (error) {
      console.error("Error fetching batches", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBatches();
  }, []);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      await api.post(`/upload/${sourceType}/`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setFile(null);
      alert("Upload successful!");
      fetchBatches();
    } catch (error) {
      console.error("Upload failed", error);
      alert("Upload failed. Please check the console.");
    } finally {
      setUploading(false);
    }
  };

  const columns = [
    { header: 'Batch ID', accessor: 'id' as const },
    { header: 'Source Type', accessor: 'source' as const },
    { header: 'Upload Time', accessor: 'upload_timestamp' as const },
    { 
      header: 'Status', 
      accessor: (b: UploadBatch) => <StatusBadge status={b.status} /> 
    }
  ];

  return (
    <div>
      <h1>Data Uploads</h1>
      
      <div className="card" style={{ marginBottom: '2rem' }}>
        <h2>New Upload</h2>
        <form onSubmit={handleUpload} style={{ display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <select 
            value={sourceType} 
            onChange={e => setSourceType(e.target.value)}
            style={{ padding: '0.5rem', borderRadius: '4px', border: '1px solid var(--border-color)' }}
          >
            <option value="sap">SAP ERP (CSV)</option>
            <option value="utility">Utility Portal (CSV)</option>
            <option value="travel">Concur Travel (JSON)</option>
          </select>
          <input type="file" onChange={handleFileChange} accept=".csv,.json" />
          <button type="submit" className="btn btn-primary" disabled={!file || uploading}>
            {uploading ? 'Uploading...' : 'Upload Data'}
          </button>
        </form>
      </div>

      <div className="card">
        <h2>Recent Batches</h2>
        {loading ? (
          <div>Loading...</div>
        ) : (
          <DataTable 
            columns={columns} 
            data={batches} 
            searchFields={['id', 'status']} 
          />
        )}
      </div>
    </div>
  );
}
