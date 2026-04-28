import { Settings } from 'lucide-react';

export default function Header() {
  return (
    <header className="sticky top-0 z-50 bg-white/90 backdrop-blur-xl border-b border-slate-100 px-10 py-5 flex justify-between items-center shadow-sm">
      <div className="flex items-center gap-4">
        <img src="/assets/logo_horizontal.png" alt="Logo" className="h-10" />
      </div>
      
      <div className="flex items-center gap-10">
        <nav className="flex gap-8 font-bold text-xs uppercase tracking-[0.2em] text-slate-400">
          <a href="#" className="text-[#0068B1]">Dashboard</a>
          <a href="#" className="hover:text-slate-600 transition-all">Intelligence</a>
          <a href="#" className="hover:text-slate-600 transition-all">Support</a>
        </nav>
        <div className="flex items-center gap-4">
          <div className="px-4 py-2 rounded-full bg-slate-50 border border-slate-100 text-[10px] font-black tracking-widest text-slate-400 flex items-center gap-2">
             AI POWERED SYSTEM
          </div>
          <button className="p-2.5 rounded-xl bg-slate-50 border border-slate-100 text-slate-400 hover:text-slate-600 transition-all">
            <Settings size={20} />
          </button>
        </div>
      </div>
    </header>
  );
}
