export interface NormalizedRecord {
  id: number;
  tenant: number;
  source_type: string;
  activity_type: string;
  scope: string;
  original_unit: string;
  normalized_unit: string;
  original_value: string;
  normalized_value: string;
  activity_date: string;
  confidence_score: string;
  suspicious_flag: boolean;
  approval_status: string;
  approved_by: number | null;
  source_reference: string | null;
  created_at: string;
}

export interface UploadBatch {
  id: number;
  source: number;
  upload_timestamp: string;
  uploaded_by: number | null;
  status: string;
}
