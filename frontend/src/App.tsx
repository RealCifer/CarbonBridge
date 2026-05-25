import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import Uploads from './pages/Uploads';
import PendingReview from './pages/PendingReview';
import SuspiciousRecords from './pages/SuspiciousRecords';
import ApprovedRecords from './pages/ApprovedRecords';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="uploads" element={<Uploads />} />
          <Route path="pending" element={<PendingReview />} />
          <Route path="suspicious" element={<SuspiciousRecords />} />
          <Route path="approved" element={<ApprovedRecords />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
