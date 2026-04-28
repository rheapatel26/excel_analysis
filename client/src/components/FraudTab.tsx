import { AlertTriangle } from 'lucide-react';
import type { AnalysisData } from '../types';

export default function FraudTab({ data }: { data: AnalysisData }) {
  const allFlags = [...data.fraud_flags, ...(data.outliers || [])];
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-6 mb-8">
        <div className="p-4 bg-red-50 text-red-600 rounded-3xl">
          <AlertTriangle size={32} />
        </div>
        <div>
          <h2 className="text-3xl font-black text-[#001D4A]">Audit Intelligence</h2>
          <p className="text-slate-500 font-medium">{allFlags.length} claims flagged for manual review</p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {allFlags.map((flag: any, i: number) => (
          <div key={i} className="bg-white p-8 rounded-[32px] border border-slate-100 shadow-sm hover:shadow-md transition-all flex justify-between items-center group">
            <div className="flex gap-10 items-center">
              <div className="text-4xl font-black text-slate-300 group-hover:text-[#0068B1] transition-colors">
                {String(i + 1).padStart(2, '0')}
              </div>
              <div>
                <div className="text-xs font-black text-[#0068B1] tracking-widest uppercase mb-1">Claim: {flag.claim_id}</div>
                <div className="text-xl font-bold text-[#001D4A]">{flag.hospital}</div>
              </div>
            </div>
            <div className="flex flex-col items-end gap-3">
              <div className="text-2xl font-black text-[#001D4A]">₹{flag.amount?.toLocaleString()}</div>
              <div className="flex gap-2">
                {(flag.signals || ['High Value Outlier']).map((s: string, j: number) => (
                  <span key={j} className="px-4 py-2 bg-red-50 text-red-600 text-[10px] font-black uppercase tracking-widest rounded-full border border-red-100">
                    {s}
                  </span>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
