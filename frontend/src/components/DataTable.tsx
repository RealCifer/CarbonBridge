import { useState, useMemo } from 'react';

interface Column<T> {
  header: string;
  accessor: keyof T | ((row: T) => React.ReactNode);
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[];
  searchPlaceholder?: string;
  searchFields?: (keyof T)[];
  itemsPerPage?: number;
}

export default function DataTable<T>({ 
  columns, 
  data, 
  searchPlaceholder = "Search...",
  searchFields = [],
  itemsPerPage = 10
}: DataTableProps<T>) {
  const [searchTerm, setSearchTerm] = useState("");
  const [currentPage, setCurrentPage] = useState(1);

  // Filter data based on search term
  const filteredData = useMemo(() => {
    if (!searchTerm) return data;
    const lowerSearch = searchTerm.toLowerCase();
    
    return data.filter(item => {
      // If no specific search fields are provided, search across all string values
      const fieldsToSearch = searchFields.length > 0 
        ? searchFields 
        : Object.keys(item as Record<string, unknown>) as (keyof T)[];
        
      return fieldsToSearch.some(field => {
        const val = item[field];
        if (val == null) return false;
        return String(val).toLowerCase().includes(lowerSearch);
      });
    });
  }, [data, searchTerm, searchFields]);

  // Pagination logic
  const totalPages = Math.ceil(filteredData.length / itemsPerPage);
  const paginatedData = useMemo(() => {
    const start = (currentPage - 1) * itemsPerPage;
    return filteredData.slice(start, start + itemsPerPage);
  }, [filteredData, currentPage, itemsPerPage]);

  const handleSearch = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchTerm(e.target.value);
    setCurrentPage(1); // reset to first page on search
  };

  return (
    <div className="table-container">
      <div className="table-header-controls">
        <input 
          type="text" 
          placeholder={searchPlaceholder} 
          className="search-input"
          value={searchTerm}
          onChange={handleSearch}
        />
        <div style={{fontSize: '0.875rem', color: 'var(--text-secondary)'}}>
          Showing {filteredData.length} records
        </div>
      </div>
      
      <div style={{overflowX: 'auto'}}>
        <table>
          <thead>
            <tr>
              {columns.map((col, idx) => (
                <th key={idx}>{col.header}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {paginatedData.length > 0 ? (
              paginatedData.map((row, rowIdx) => (
                <tr key={rowIdx}>
                  {columns.map((col, colIdx) => (
                    <td key={colIdx}>
                      {typeof col.accessor === 'function' 
                        ? col.accessor(row) 
                        : (row[col.accessor] as React.ReactNode)}
                    </td>
                  ))}
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan={columns.length} style={{textAlign: 'center', padding: '2rem'}}>
                  No records found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {totalPages > 1 && (
        <div className="pagination">
          <button 
            className="btn btn-outline" 
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
          >
            Previous
          </button>
          <span style={{fontSize: '0.875rem'}}>
            Page {currentPage} of {totalPages}
          </span>
          <button 
            className="btn btn-outline" 
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages}
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
