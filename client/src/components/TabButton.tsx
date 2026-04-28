import React from 'react';

interface TabButtonProps {
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}

export default function TabButton({ active, onClick, icon, label }: TabButtonProps) {
  return (
    <button
      onClick={onClick}
      className={`pb-4 px-2 flex items-center gap-3 font-bold text-sm uppercase tracking-widest transition-all ${
        active 
          ? 'text-[#0068B1] border-b-2 border-[#0068B1]' 
          : 'text-slate-400 opacity-60 hover:opacity-100 hover:text-slate-600'
      }`}
    >
      {icon} {label}
    </button>
  );
}
