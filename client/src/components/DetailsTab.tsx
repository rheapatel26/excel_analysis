import { Download } from 'lucide-react';
import type { AnalysisData } from '../types';

export default function DetailsTab({ data }: { data: AnalysisData }) {
  if (!data.details || data.details.length === 0) return null;
  const headers = Object.keys(data.details[0]);
  
  const downloadCSV = () => {
    const csvRows = [];
    csvRows.push(headers.join(','));
    
    for (const row of data.details) {
      const values = headers.map(header => {
        let val = row[header] === null || row[header] === undefined ? '' : String(row[header]);
        if (val.includes(',') || val.includes('"') || val.includes('\n')) {
          val = `"${val.replace(/"/g, '""')}"`;
        }
        return val;
      });
      csvRows.push(values.join(','));
    }
    
    const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const baseName = data.file ? data.file.split('.')[0] : 'audit_ledger';
    link.setAttribute('download', `${baseName}_export.csv`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div className="bg-white rounded-[40px] border border-slate-100 shadow-sm overflow-hidden">
      <div className="p-10 border-b border-slate-50 flex justify-between items-center bg-slate-50/30">
        <div>
          <h2 className="text-2xl font-black text-[#001D4A]">Institutional Audit Ledger</h2>
          <p className="text-sm text-slate-400 font-bold uppercase tracking-widest mt-1">Full Transaction History</p>
        </div>
        <button 
          onClick={downloadCSV}
          className="px-6 py-3 bg-white border border-slate-200 rounded-xl font-bold text-sm text-[#0068B1] hover:bg-slate-50 transition-all flex items-center gap-2"
        >
          <Download size={16} /> Download CSV
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left table-auto border-collapse">
          <thead>
            <tr className="bg-slate-50">
              {headers.map(h => (
                <th key={h} className="px-8 py-6 text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 border-r border-slate-100 last:border-0">
                  {h.replace(/_/g, ' ')}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.details.map((row: any, i: number) => (
              <tr key={i} className="hover:bg-blue-50/20 transition-colors">
                {headers.map(h => (
                  <td key={h} className="px-8 py-5 text-sm font-bold text-slate-600 border-r border-slate-100 last:border-0 whitespace-nowrap">
                    {String(row[h] || '\u2014')}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
