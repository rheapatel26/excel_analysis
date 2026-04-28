import { ShieldCheck } from 'lucide-react';

export default function PolicyAITab() {
  return (
    <div className="bg-white p-10 rounded-[40px] border border-slate-100 shadow-sm flex flex-col items-center justify-center min-h-[400px]">
      <ShieldCheck size={48} className="text-[#0068B1] mb-6 opacity-50" />
      <h2 className="text-2xl font-black text-[#001D4A] mb-2">Policy AI Assistant</h2>
      <p className="text-slate-500 font-medium max-w-md text-center">
        Upload policy documents and ask questions about coverage.
        <br />
        <span className="text-sm mt-2 block opacity-70">(Integration with /api/upload-policy and /api/policy-qa endpoints coming soon)</span>
      </p>
    </div>
  );
}
