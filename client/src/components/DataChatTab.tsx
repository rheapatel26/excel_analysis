import { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import { Send, Bot, User, Loader2, Sparkles, FileSpreadsheet, CloudCheck } from 'lucide-react';
import type { AnalysisData } from '../types';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  resultHtml?: string;
  code?: string;
  error?: string;
}

const API_BASE = 'http://127.0.0.1:5001';

export default function DataChatTab({ data }: { data: AnalysisData }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleSend = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!input.trim()) return;

    const question = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: question }]);
    setLoading(true);

    try {
      const res = await axios.post(`${API_BASE}/api/chat`, { 
        question: question, 
        file: data.file,
        history: messages 
      });

      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: res.data.explanation || 'I have processed your query.',
        resultHtml: res.data.result_html,
        code: res.data.code,
        error: res.data.error
      }]);
    } catch (err: any) {
      setMessages(prev => [...prev, { 
        role: 'assistant', 
        content: 'Sorry, I encountered an error while analyzing the cloud dataset.',
        error: err.response?.data?.error || err.message
      }]);
    } finally {
      setLoading(false);
    }
  };

  const renderContent = (content: string) => {
    // Handle newlines
    let html = content.replace(/\n/g, '<br/>');
    // Handle bolding **text**
    html = html.replace(/\*\*(.*?)\*\*/g, '<strong class="font-bold text-[#001D4A]">$1</strong>');
    return html;
  };

  return (
    <div className="bg-white rounded-[24px] border border-slate-200 shadow-sm overflow-hidden flex flex-col h-[750px] relative">
      
      {/* Minimal Header with Cloud Badge */}
      <div className="absolute top-0 w-full h-14 bg-white/80 backdrop-blur-md border-b border-slate-100 flex items-center justify-between px-6 z-10">
        <div className="flex items-center gap-2 text-slate-500 font-medium text-sm">
          <FileSpreadsheet size={16} />
          <span className="truncate max-w-[300px]">{data.file}</span>
        </div>
        <div className="flex items-center gap-1.5 bg-blue-50 text-blue-600 px-3 py-1 rounded-full border border-blue-100">
          <div className="w-1.5 h-1.5 bg-blue-500 rounded-full animate-pulse" />
          <span className="text-[10px] font-bold uppercase tracking-wider">Cloud Persisted (Supabase)</span>
        </div>
      </div>

      {/* Chat Area */}
      <div className="flex-1 overflow-y-auto p-4 pt-20 pb-40 space-y-6 scroll-smooth">
        {messages.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center max-w-2xl mx-auto text-center mt-[-50px]">
            <div className="w-16 h-16 bg-blue-50 text-blue-600 rounded-full flex items-center justify-center mb-6 shadow-sm">
              <Sparkles size={32} />
            </div>
            <h2 className="text-3xl font-semibold text-slate-800 mb-6 tracking-tight">How can I help you analyze this portfolio?</h2>
            <div className="grid grid-cols-2 gap-3 w-full">
              {[
                "What is the average claim amount?",
                "Which hospital had the highest total claims?",
                "List the top 5 chronic diseases by cost.",
                "Plot a monthly trend of claim volume."
              ].map((suggestion, i) => (
                <button 
                  key={i}
                  onClick={() => { setInput(suggestion); }}
                  className="p-4 rounded-xl border border-slate-200 text-left hover:bg-slate-50 transition-colors text-sm text-slate-600 shadow-sm font-medium"
                >
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        )}
        
        <div className="max-w-3xl mx-auto space-y-8">
          {messages.map((m, i) => (
            <div key={i} className={`flex gap-4 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              
              {/* Assistant Avatar */}
              {m.role === 'assistant' && (
                <div className="w-8 h-8 rounded-full border border-slate-200 flex items-center justify-center shrink-0 bg-white shadow-sm mt-1">
                  <Sparkles size={16} className="text-blue-600" />
                </div>
              )}

              {/* Message Content */}
              <div className={`max-w-[85%] ${m.role === 'user' ? 'bg-[#001D4A] text-white px-5 py-3 rounded-2xl rounded-tr-sm shadow-md' : 'text-slate-800 py-1'}`}>
                {m.role === 'user' ? (
                  <p className="text-[15px] font-medium">{m.content}</p>
                ) : (
                  <div className="space-y-4">
                    {m.error ? (
                      <div className="flex items-center gap-2 text-red-600 font-medium bg-red-50 p-4 rounded-xl border border-red-100">
                        <p className="text-sm">{m.error}</p>
                      </div>
                    ) : (
                      <>
                        <div 
                          className="text-[16px] leading-relaxed font-medium text-slate-700"
                          dangerouslySetInnerHTML={{ __html: renderContent(m.content) }}
                        />
                        
                        {m.resultHtml && (
                          <div className="mt-4 overflow-x-auto rounded-2xl border border-slate-200 bg-white shadow-sm [&_table]:w-full [&_table]:text-sm [&_th]:text-left [&_th]:p-3 [&_th]:bg-slate-50 [&_th]:text-slate-600 [&_th]:font-bold [&_th]:uppercase [&_th]:text-[10px] [&_th]:tracking-wider [&_th]:border-b [&_th]:border-slate-200 [&_td]:p-3 [&_td]:border-b [&_td]:border-slate-100 [&_tr:last-child_td]:border-0 [&_tr:hover]:bg-slate-50 transition-all">
                            <div dangerouslySetInnerHTML={{ __html: m.resultHtml }} />
                          </div>
                        )}
                        
                        {m.code && (
                          <details className="mt-4 group border border-slate-200 rounded-xl overflow-hidden shadow-sm transition-all">
                            <summary className="px-4 py-3 bg-slate-50 text-[10px] font-bold text-slate-500 cursor-pointer hover:bg-slate-100 transition-colors flex items-center gap-2 uppercase tracking-widest">
                              <span>Intelligence Source Code</span>
                            </summary>
                            <pre className="p-4 bg-[#0F172A] text-blue-300 text-[12px] overflow-x-auto leading-relaxed">
                              <code>{m.code}</code>
                            </pre>
                          </details>
                        )}
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex gap-4 justify-start">
              <div className="w-8 h-8 rounded-full border border-slate-200 flex items-center justify-center shrink-0 bg-white shadow-sm mt-1">
                <Sparkles size={16} className="text-blue-600" />
              </div>
              <div className="py-2 flex items-center gap-3 text-slate-500 bg-slate-50 px-4 rounded-full border border-slate-100 shadow-sm">
                <Loader2 className="w-4 h-4 animate-spin text-blue-600" />
                <span className="text-xs font-bold uppercase tracking-widest">Analyzing Cloud Dataset...</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* GPT-style Input Area positioned at bottom */}
      <div className="absolute bottom-0 w-full bg-gradient-to-t from-white via-white to-transparent pt-10 pb-6 px-4">
        <div className="max-w-3xl mx-auto relative">
          <form onSubmit={handleSend} className="relative flex items-center shadow-[0_8px_30px_rgb(0,0,0,0.04)] rounded-2xl bg-white border border-slate-200 focus-within:border-blue-400 focus-within:ring-4 focus-within:ring-blue-50/50 transition-all">
            <input 
              type="text"
              placeholder="Ask anything about your claims data..." 
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={loading}
              className="w-full pl-5 pr-14 py-5 bg-transparent outline-none text-slate-800 text-[15px] font-medium placeholder:text-slate-400 disabled:opacity-50 rounded-2xl"
            />
            <button 
              type="submit" 
              disabled={loading || !input.trim()}
              className="absolute right-2.5 p-2.5 bg-[#001D4A] text-white rounded-xl hover:bg-blue-700 transition-all active:scale-95 disabled:opacity-30 disabled:bg-slate-200 disabled:text-slate-500 disabled:active:scale-100 shadow-sm"
            >
              <Send size={18} />
            </button>
          </form>
          <div className="text-center mt-3 text-[10px] text-slate-400 font-bold uppercase tracking-widest">
            AI-Driven Claims Intelligence • Powered by Supabase Cloud
          </div>
        </div>
      </div>
    </div>
  );
}
