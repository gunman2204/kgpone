import React, { useState, useRef, useEffect, useCallback } from 'react';
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import {
  Bot, User, Send, Network, Database, Sparkles, BookOpen, Download,
  Filter, ChevronLeft, ImageIcon, Sigma, Table2, FileText,
  Zap, Brain, Key, ChevronDown, Eye, EyeOff, Lock, MessageSquare, Plus, Share2, Settings as SettingsIcon, Trash2, Loader2, CheckCircle2, AlertCircle, WifiOff,
  Activity, RefreshCw, FolderOpen, HardDrive, CheckCircle, XCircle
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import api from '../lib/api';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import 'katex/dist/katex.min.css';
import { useAcademic } from '../context/AcademicContext';

const remarkPlugins = [remarkGfm, remarkMath];
const rehypePlugins = [rehypeKatex];

/* ── Inline styles injected once ──────────────────────────────────────── */
const GLOBAL_STYLES = `
@keyframes kgp-cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
@keyframes kgp-slide-up {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes kgp-dot-bounce {
  0%, 80%, 100% { transform: translateY(0); }
  40% { transform: translateY(-6px); }
}
.kgp-msg-enter { animation: kgp-slide-up 0.35s cubic-bezier(0.22,1,0.36,1) both; }
.kgp-cursor { display: inline-block; width: 2px; height: 1em; background: currentColor;
  margin-left: 2px; vertical-align: text-bottom;
  animation: kgp-cursor-blink 0.8s step-start infinite; }
.kgp-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: currentColor; margin: 0 2px; }
.kgp-dot:nth-child(1) { animation: kgp-dot-bounce 1.2s ease-in-out infinite 0s; }
.kgp-dot:nth-child(2) { animation: kgp-dot-bounce 1.2s ease-in-out infinite 0.2s; }
.kgp-dot:nth-child(3) { animation: kgp-dot-bounce 1.2s ease-in-out infinite 0.4s; }
@keyframes kgp-byok-open {
  from { opacity: 0; transform: translateY(-8px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes kgp-shimmer {
  0%   { background-position: -200% center; }
  100% { background-position: 200% center; }
}
.kgp-byok-open { animation: kgp-byok-open 0.28s cubic-bezier(0.22,1,0.36,1) both; }
.kgp-advanced-shimmer {
  background: linear-gradient(90deg, #7c3aed, #a855f7, #ec4899, #7c3aed);
  background-size: 200% auto;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  animation: kgp-shimmer 3s linear infinite;
}
`;

if (typeof document !== 'undefined' && !document.getElementById('kgp-chat-styles')) {
  const s = document.createElement('style');
  s.id = 'kgp-chat-styles';
  s.textContent = GLOBAL_STYLES;
  document.head.appendChild(s);
}

/* ── Chunk-type config ────────────────────────────────────────────────── */
const CHUNK_TYPE_CONFIG = {
  equation: {
    icon: Sigma,
    label: 'EQ',
    color: 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300',
    border: 'border-violet-200 dark:border-violet-800',
  },
  figure: {
    icon: ImageIcon,
    label: 'FIG',
    color: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
    border: 'border-emerald-200 dark:border-emerald-800',
  },
  table_row: {
    icon: Table2,
    label: 'TBL',
    color: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
    border: 'border-amber-200 dark:border-amber-800',
  },
  text: {
    icon: FileText,
    label: 'TXT',
    color: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
    border: 'border-slate-200 dark:border-slate-700',
  },
};

const getChunkConfig = (chunk_type) =>
  CHUNK_TYPE_CONFIG[chunk_type] || CHUNK_TYPE_CONFIG.text;

/* ── Markdown components ───────────────────────────────────────────────── */
const MarkdownComponents = {
  a: ({ node, href, children, ...props }) => {
    if (href && href.startsWith('#CIT-')) {
      return (
        <a
          href={href}
          className="text-primary font-semibold hover:underline cursor-pointer bg-primary/10 px-1 rounded-sm mx-0.5"
          onClick={(e) => {
            e.preventDefault();
            document.getElementById(href.substring(1))?.scrollIntoView({ behavior: 'smooth', block: 'center' });
          }}
        >
          {children}
        </a>
      );
    }
    return (
      <a href={href} className="text-primary font-medium hover:underline" target="_blank" rel="noreferrer" {...props}>
        {children}
      </a>
    );
  },
  img: ({ node, src, alt, ...props }) => (
    <figure className="my-4 flex flex-col items-center gap-2">
      <div className="rounded-xl overflow-hidden border border-slate-200 dark:border-slate-700 shadow-md hover:shadow-lg transition-shadow duration-200 max-w-full">
        <img
          src={src}
          alt={alt || 'Figure'}
          className="max-w-full h-auto object-contain transition-transform duration-300 hover:scale-105"
          style={{ maxHeight: '480px' }}
          onError={(e) => { e.target.style.display = 'none'; }}
          {...props}
        />
      </div>
      {alt && alt !== 'Figure' && (
        <figcaption className="text-xs text-slate-500 dark:text-slate-400 text-center italic">
          {alt}
        </figcaption>
      )}
    </figure>
  ),
  code: ({ node, inline, className, children, ...props }) => {
    if (inline) {
      return (
        <code className="bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-200 px-1.5 py-0.5 rounded text-[13px] font-mono" {...props}>
          {children}
        </code>
      );
    }
    return (
      <div className="my-3 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-700">
        <div className="bg-slate-100 dark:bg-slate-800 px-4 py-2 text-xs font-mono text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
          {className?.replace('language-', '') || 'code'}
        </div>
        <pre className="bg-slate-50 dark:bg-slate-900 px-4 py-3 overflow-x-auto text-[13px] font-mono leading-relaxed">
          <code className={className} {...props}>{children}</code>
        </pre>
      </div>
    );
  },
  table: ({ node, children, ...props }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700 shadow-sm">
      <table className="min-w-full divide-y divide-slate-200 dark:divide-slate-700 text-sm" {...props}>
        {children}
      </table>
    </div>
  ),
  th: ({ node, children, ...props }) => (
    <th className="bg-slate-50 dark:bg-slate-800 px-4 py-2 text-left text-xs font-semibold text-slate-600 dark:text-slate-300 uppercase tracking-wider" {...props}>
      {children}
    </th>
  ),
  td: ({ node, children, ...props }) => (
    <td className="px-4 py-2 text-slate-700 dark:text-slate-300 border-t border-slate-100 dark:border-slate-800" {...props}>
      {children}
    </td>
  ),
};

/* ── Citation card ─────────────────────────────────────────────────────── */
const CitationCard = React.memo(({ cit, onCitationClick }) => {
  const isClickable = (cit.document_id && cit.document_id !== 'GRAPH') || cit.source_url;

  return (
    <div className="relative group">
      <div
        id={cit.citation_id}
        onClick={isClickable ? (e) => onCitationClick(e, cit) : undefined}
        className={`flex items-center gap-1.5 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-lg px-2.5 py-1.5 shadow-sm text-xs transition-all duration-200 hover:shadow-md select-none
          ${isClickable ? 'cursor-pointer hover:border-primary/50 hover:bg-primary/5' : 'cursor-default'}`}
      >
        <span className={`font-mono text-[10px] font-bold ${isClickable ? 'text-primary' : 'text-slate-400'}`}>
          [{cit.citation_id}]
        </span>
        <span
          className={`font-medium max-w-[160px] truncate ${isClickable ? 'text-slate-700 dark:text-slate-300' : 'text-slate-500'}`}
          title={cit.source_title}
        >
          {cit.source_title}
        </span>
        {cit.page_number && (
          <span className="text-slate-400 font-normal text-[10px]">p.{cit.page_number}</span>
        )}
      </div>

      {/* Rich hover tooltip */}
      <div className="absolute bottom-full left-0 mb-2 hidden group-hover:flex flex-col z-50 w-80 bg-slate-900 dark:bg-slate-800 text-white text-xs rounded-2xl shadow-2xl border border-slate-700 opacity-0 group-hover:opacity-100 transition-all duration-200 pointer-events-none overflow-hidden">
        {/* Tooltip header */}
        <div className="px-3 pt-3 pb-2 border-b border-slate-700/60">
          <div className="font-semibold text-slate-100 truncate">{cit.source_title}</div>
          <div className="flex items-center gap-2 mt-1 flex-wrap">
            {cit.section && (
              <span className="text-primary-400 text-[10px] italic truncate max-w-[200px]" title={cit.section}>
                {cit.section}
              </span>
            )}
            {cit.page_number && (
              <span className="text-slate-400 text-[10px]">· Page {cit.page_number}</span>
            )}
          </div>
        </div>

        {/* Equation block */}
        {cit.chunk_type === 'equation' && cit.raw_latex && (
          <div className="px-3 py-2 border-b border-slate-700/60">
            <div className="text-[10px] text-violet-400 font-semibold mb-1 flex items-center gap-1">
              <Sigma className="w-3 h-3" />
              {cit.equation_label ? `Equation (${cit.equation_label})` : 'Equation'}
            </div>
            <code className="block bg-slate-950 rounded-lg px-2 py-1.5 font-mono text-violet-300 text-[11px] break-all leading-relaxed">
              {cit.raw_latex}
            </code>
          </div>
        )}

        {/* Figure image preview */}
        {cit.chunk_type === 'figure' && cit.image_url && (
          <div className="px-3 py-2 border-b border-slate-700/60">
            <div className="text-[10px] text-emerald-400 font-semibold mb-1.5 flex items-center gap-1">
              <ImageIcon className="w-3 h-3" /> Figure Preview
            </div>
            <img
              src={cit.image_url}
              alt="Figure from document"
              className="w-full rounded-lg object-contain max-h-36 bg-slate-950"
              onError={(e) => { e.target.style.display = 'none'; }}
            />
          </div>
        )}

        {/* Text snippet */}
        <div className="px-3 py-2">
          <p className="italic text-slate-300 break-words line-clamp-5 leading-relaxed text-[11px]">
            "{cit.text_snippet}"
          </p>
        </div>

        {/* Confidence */}
        <div className="px-3 pb-2.5 flex items-center justify-between">
          <span className="text-[9px] text-slate-500 uppercase tracking-wider">{cit.confidence}</span>
          <span className="text-[9px] font-mono text-slate-500">{(cit.score * 100).toFixed(0)}% match</span>
        </div>

        {/* Tooltip arrow */}
        <div className="absolute top-full left-6 -mt-px border-4 border-transparent border-t-slate-900 dark:border-t-slate-800" />
      </div>
    </div>
  );
});

/* ── Chat message ──────────────────────────────────────────────────────── */
const ChatMessage = React.memo(({ msg, index, isStreaming, handleCitationClick, renderBackendBadge }) => {
  return (
    <div
      className={`flex gap-4 kgp-msg-enter ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'}`}
      style={{ animationDelay: `${Math.min(index * 30, 150)}ms` }}
    >
      {/* Avatar */}
      <div className={`flex-shrink-0 w-9 h-9 rounded-full flex items-center justify-center shadow-sm ${
        msg.role === 'user'
          ? 'bg-primary text-primary-foreground'
          : msg.isError
            ? 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400'
            : 'bg-white dark:bg-slate-800 border text-slate-600 dark:text-slate-300'
      }`}>
        {msg.role === 'user' ? <User className="w-5 h-5" /> : <Bot className="w-5 h-5" />}
      </div>

      {/* Content */}
      <div className={`flex flex-col max-w-[85%] ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>

        {/* Intent & Backend badges */}
        {msg.metadata && (
          <div className="flex flex-wrap gap-2 mb-2 items-center">
            {msg.metadata.intent && (
              <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400 uppercase tracking-wider border">
                {msg.metadata.intent.replace('_', ' ')}
              </span>
            )}
            {msg.metadata.backends_used?.map(b => renderBackendBadge(b))}
          </div>
        )}

        {/* Bubble */}
        <div className={`px-5 py-4 rounded-3xl shadow-sm text-[15px] ${
          msg.role === 'user'
            ? 'bg-primary text-primary-foreground rounded-tr-sm'
            : msg.isError
              ? 'bg-red-50 text-red-900 border border-red-200 dark:bg-red-950/50 dark:text-red-200 dark:border-red-900 rounded-tl-sm'
              : 'bg-white border border-slate-200/60 text-slate-800 dark:bg-slate-900 dark:border-slate-800 dark:text-slate-200 rounded-tl-sm'
        }`}>
          {msg.role === 'user' ? (
            <div className="whitespace-pre-wrap leading-relaxed">{msg.content}</div>
          ) : msg.isThinking ? (
            <div className="animate-pulse text-slate-400 italic whitespace-pre-wrap leading-relaxed flex items-center gap-2">
              <Sparkles className="w-4 h-4 text-primary" /> {msg.content}
            </div>
          ) : (
            <div className="prose prose-slate dark:prose-invert max-w-none break-words leading-relaxed">
              <ReactMarkdown
                remarkPlugins={remarkPlugins}
                rehypePlugins={rehypePlugins}
                components={MarkdownComponents}
              >
                {msg.content}
              </ReactMarkdown>
              {/* Blinking streaming cursor */}
              {isStreaming && <span className="kgp-cursor" aria-hidden="true" />}
            </div>
          )}
        </div>

        {/* Citations */}
        {msg.metadata?.citations?.length > 0 && (
          <div className="mt-3 w-full flex flex-col gap-2">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider ml-1">Sources</p>
            <div className="flex flex-wrap gap-2">
              {msg.metadata.citations.map((cit, cidx) => (
                <CitationCard
                  key={cidx}
                  cit={cit}
                  onCitationClick={handleCitationClick}
                />
              ))}
            </div>
          </div>
        )}

        {/* Related Documents (Download Links) */}
        {(() => {
          const docsWithUrls = msg.metadata?.citations?.filter(c => c.document_download_url) || [];
          // Deduplicate by normalized source_title to prevent duplicates of the same PDF
          const uniqueDocsMap = new Map();
          docsWithUrls.forEach(c => {
            const key = (c.source_title || '').toLowerCase().trim() || c.document_id;
            if (key && !uniqueDocsMap.has(key)) {
              uniqueDocsMap.set(key, c);
            }
          });
          const uniqueDocs = Array.from(uniqueDocsMap.values());
          if (uniqueDocs.length === 0) return null;
          return (
            <div className="mt-4 w-full flex flex-col gap-2 border-t border-slate-100 dark:border-slate-800 pt-3">
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider ml-1">Related Documents</p>
              <div className="flex flex-col gap-2">
                {uniqueDocs.map(doc => (
                  <a
                    key={doc.document_id}
                    href={doc.document_download_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-between bg-slate-50 hover:bg-slate-100 dark:bg-slate-800/50 dark:hover:bg-slate-800 px-4 py-2.5 rounded-lg border border-slate-200 dark:border-slate-700 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <FileText className="w-5 h-5 text-primary" />
                      <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
                        {doc.source_title}
                      </span>
                    </div>
                    <span className="flex items-center gap-1.5 text-xs font-medium bg-primary text-white px-3 py-1.5 rounded-md shadow-sm hover:bg-primary/90 transition-colors">
                      <Download className="w-3.5 h-3.5" />
                      Download
                    </span>
                  </a>
                ))}
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
});

/* ── Loading dots ─────────────────────────────────────────────────────── */
const LoadingDots = () => (
  <div className="flex gap-4 kgp-msg-enter">
    <div className="flex-shrink-0 w-9 h-9 rounded-full bg-white dark:bg-slate-800 border text-slate-600 dark:text-slate-300 flex items-center justify-center shadow-sm">
      <Bot className="w-5 h-5" />
    </div>
    <div className="px-5 py-4 rounded-3xl bg-white border border-slate-200/60 dark:bg-slate-900 dark:border-slate-800 rounded-tl-sm shadow-sm flex items-center gap-1.5 text-slate-500 dark:text-slate-400">
      <span className="kgp-dot" />
      <span className="kgp-dot" />
      <span className="kgp-dot" />
    </div>
  </div>
);

/* ── Main Chat component ───────────────────────────────────────────────── */
const Chat = () => {
  const navigate = useNavigate();
  const { departments, courses: allCourses } = useAcademic();
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Hello! I am the **KnowledgeOS Assistant**. Ask me about your curriculum, prerequisites, formulas, or any concept from your course materials.',
    }
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [streamingIdx, setStreamingIdx] = useState(null); // index of the message being streamed
  const [useCitations, setUseCitations] = useState(true);

  // Settings UI Toggle
  const [settingsOpen, setSettingsOpen] = useState(false);

  // Analysis mode: 'basic' | 'advanced'
  const [analysisMode, setAnalysisMode] = useState('basic');

  // BYOK — keys are used per-request only, never stored server-side
  const [byokOpen, setByokOpen] = useState(false);
  const [byokProvider, setByokProvider] = useState('');
  const [byokModel, setByokModel] = useState('');
  const [byokKey, setByokKey] = useState('');
  const [byokKeyVisible, setByokKeyVisible] = useState(false);

  // Chat History State
  const [conversations, setConversations] = useState([]);
  const [activeConversationId, setActiveConversationId] = useState(null);
  const [isShared, setIsShared] = useState(false);
  const [isChatLoading, setIsChatLoading] = useState(false);

  // Memories State
  const [memories, setMemories] = useState([]);
  const [memoriesLoading, setMemoriesLoading] = useState(false);
  const [memoriesOpen, setMemoriesOpen] = useState(false);
  const [diagnosticsOpen, setDiagnosticsOpen] = useState(false);
  const [systemDiagnostics, setSystemDiagnostics] = useState(null);
  const [isDiagnosticsLoading, setIsDiagnosticsLoading] = useState(false);

  // Offline Mode State
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [isOfflineModeActive, setIsOfflineModeActive] = useState(() => {
    return !navigator.onLine || localStorage.getItem('kgpone_offline_mode') === 'true';
  });
  const [localDocuments, setLocalDocuments] = useState([]);
  const [selectedLocalDocIds, setSelectedLocalDocIds] = useState([]);
  const [watcherHealth, setWatcherHealth] = useState(null);

  const setOfflineMode = (active) => {
    setIsOfflineModeActive(active);
    if (active) {
      localStorage.setItem('kgpone_offline_mode', 'true');
    } else {
      localStorage.removeItem('kgpone_offline_mode');
    }
  };

  const fetchDiagnostics = useCallback(async () => {
    setIsDiagnosticsLoading(true);
    try {
      const res = await api.get('/api/v1/system/diagnostics');
      setSystemDiagnostics(res.data?.data || null);
    } catch (err) {
      console.error("Failed to fetch diagnostics", err);
    } finally {
      setIsDiagnosticsLoading(false);
    }
  }, []);

  const openDiagnosticsModal = () => {
    setDiagnosticsOpen(true);
    fetchDiagnostics();
  };

  useEffect(() => {
    const handleOnline = () => {
      setIsOnline(true);
      // Don't forcefully deactivate if user deliberately set offline mode
      if (localStorage.getItem('kgpone_offline_mode') !== 'true') {
        setIsOfflineModeActive(false);
      }
    };
    const handleOffline = () => {
      setIsOnline(false);
      setOfflineMode(true);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  const fetchLocal = useCallback(() => {
    api.get('/api/v1/documents/local')
      .then(res => setLocalDocuments(res.data.data || []))
      .catch(err => console.error("Failed to fetch local documents", err));
      
    api.get('/api/v1/documents/watcher-health')
      .then(res => setWatcherHealth(res.data.data))
      .catch(err => console.error("Failed to fetch watcher health", err));
  }, []);

  useEffect(() => {
    if (!isOfflineModeActive) return;

    fetchLocal(); // Immediate fetch on mode switch

    const interval = setInterval(fetchLocal, 5000);
    return () => clearInterval(interval);
  }, [isOfflineModeActive, fetchLocal]);

  const toggleLocalDoc = (id) => {
    setSelectedLocalDocIds(prev => 
      prev.includes(id) ? prev.filter(d => d !== id) : [...prev, id]
    );
  };

  const fetchConversations = useCallback(async () => {
    try {
      const res = await api.get('/api/v1/chat/conversations');
      setConversations(res.data || []);
    } catch (err) {
      console.error("Failed to fetch conversations", err);
    }
  }, []);

  useEffect(() => {
    fetchConversations();
  }, [fetchConversations]);

  const loadConversation = async (id) => {
    if (id === activeConversationId) return;
    setIsChatLoading(true);
    const previousId = activeConversationId;
    setActiveConversationId(id); // Optimistic update
    
    try {
      const res = await api.get(`/api/v1/chat/conversations/${id}`);
      const conv = res.data;
      setIsShared(conv.is_shared);
      
      if (conv.messages && conv.messages.length > 0) {
        const loadedMsgs = conv.messages.map(m => ({
          role: m.role,
          content: m.content,
          metadata: m.metadata_payload
        }));
        setMessages(loadedMsgs);
      } else {
        setMessages([{ role: 'assistant', content: 'Hello! I am the **KnowledgeOS Assistant**.' }]);
      }
    } catch (err) {
      console.error("Failed to load conversation", err);
      toast({ title: 'Error', description: 'Failed to load conversation', variant: 'destructive' });
      setActiveConversationId(previousId); // Revert on failure
    } finally {
      setIsChatLoading(false);
    }
  };

  const createNewChat = () => {
    setActiveConversationId(null);
    setIsShared(false);
    setMessages([{ role: 'assistant', content: 'Hello! I am the **KnowledgeOS Assistant**.' }]);
  };

  const deleteConversation = async (id, e) => {
    e.stopPropagation();
    if (!window.confirm("Are you sure you want to delete this chat?")) return;
    try {
      await api.delete(`/api/v1/chat/conversations/${id}`);
      setConversations(prev => prev.filter(c => c.id !== id));
      if (activeConversationId === id) {
        createNewChat();
      }
      toast({ title: 'Success', description: 'Chat deleted' });
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to delete chat', variant: 'destructive' });
    }
  };

  const clearMemories = async () => {
    if (!window.confirm("Are you sure you want to clear all learned facts about you? This action cannot be undone.")) return;
    try {
      await api.delete('/api/v1/chat/memories');
      setMemories([]);
      toast({ title: 'Success', description: 'Personalization memory cleared' });
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to clear memory', variant: 'destructive' });
    }
  };

  const fetchMemories = async () => {
    setMemoriesLoading(true);
    try {
      const res = await api.get('/api/v1/chat/memories');
      setMemories(res.data);
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to load memories', variant: 'destructive' });
    } finally {
      setMemoriesLoading(false);
    }
  };

  useEffect(() => {
    if (memoriesOpen) {
      fetchMemories();
    }
  }, [memoriesOpen]);

  const handleShareToggle = async () => {
    if (!activeConversationId) return;
    try {
      const res = await api.patch(`/api/v1/chat/conversations/${activeConversationId}/share`, { is_shared: !isShared });
      setIsShared(res.data.is_shared);
      toast({ title: 'Success', description: res.data.is_shared ? 'Chat is now public' : 'Chat is now private' });
      if (res.data.is_shared) {
        const link = `${window.location.origin}/chat/shared/${activeConversationId}`;
        navigator.clipboard.writeText(link);
        toast({ title: 'Link Copied', description: 'Public link copied to clipboard!' });
      }
    } catch (err) {
      toast({ title: 'Error', description: 'Failed to update share settings', variant: 'destructive' });
    }
  };

  // Cascading selection (persisted)
  const [selectedDeptId, setSelectedDeptId] = useState(() => localStorage.getItem('kgpone_chat_dept_id') || '');
  const [selectedCourseId, setSelectedCourseId] = useState(() => localStorage.getItem('kgpone_chat_course_id') || '');
  const [selectedOfferingId, setSelectedOfferingId] = useState(() => localStorage.getItem('kgpone_chat_offering_id') || '');

  useEffect(() => { localStorage.setItem('kgpone_chat_dept_id', selectedDeptId); }, [selectedDeptId]);
  useEffect(() => { localStorage.setItem('kgpone_chat_course_id', selectedCourseId); }, [selectedCourseId]);
  useEffect(() => { localStorage.setItem('kgpone_chat_offering_id', selectedOfferingId); }, [selectedOfferingId]);

  const [filteredCourses, setFilteredCourses] = useState([]);
  const [offerings, setOfferings] = useState([]);
  const { toast } = useToast();
  const scrollRef = useRef(null);

  useEffect(() => {
    if (selectedDeptId) {
      setFilteredCourses(allCourses.filter(c => String(c.department_id) === String(selectedDeptId)));
    } else {
      setFilteredCourses([]);
    }
  }, [selectedDeptId, allCourses]);

  useEffect(() => {
    if (selectedCourseId) {
      api.get(`/api/v1/academic/${selectedCourseId}/offerings`)
        .then(res => setOfferings(res.data.data || []))
        .catch(err => console.error("Failed to fetch offerings", err));
    } else {
      setOfferings([]);
    }
  }, [selectedCourseId]);

  // Smooth scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
    }
  }, [messages, isLoading]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    const userMessage = input.trim();
    setInput('');

    const assistantIdx = messages.length + 1; // after user message

    if (!activeConversationId) {
      setConversations(prev => [{id: 'temp', title: 'New Conversation...'}, ...prev]);
      setActiveConversationId('temp');
    }

    setMessages(prev => [
      ...prev,
      { role: 'user', content: userMessage },
      { role: 'assistant', content: 'Assistant is thinking...', isThinking: true, metadata: null },
    ]);
    setIsLoading(true);
    setStreamingIdx(null);

    try {
      let courseCode = null;
      if (selectedCourseId) {
        const selectedCourse = allCourses.find(c => c.id === selectedCourseId);
        courseCode = selectedCourse?.code ?? null;
      }

      const baseURL = api.defaults.baseURL || 'http://127.0.0.1:8000';
      const token = isOfflineModeActive 
        ? (localStorage.getItem('offline_access_token') || localStorage.getItem('access_token'))
        : localStorage.getItem('access_token');

      const response = await fetch(`${baseURL}/api/v1/query/ask_stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(isOfflineModeActive ? { 'X-Offline-Mode': 'true' } : {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          query: userMessage,
          course_code: courseCode || (isOfflineModeActive ? 'local' : null),
          course_offering_id: selectedOfferingId || null,
          use_citations: useCitations,
          analysis_mode: analysisMode,
          conversation_id: activeConversationId || undefined,
          document_ids: isOfflineModeActive ? selectedLocalDocIds : undefined,
          ...(analysisMode === 'advanced' && byokProvider && byokKey ? {
            byok_provider: byokProvider,
            byok_api_key: byokKey,
            byok_model: byokModel || undefined,
          } : {}),
        }),
      });

      if (!response.ok) throw new Error('Stream request failed');

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let assistantContent = '';
      let buffer = '';

      setIsLoading(false);

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.substring(6));
            if (data.type === 'status') {
              // Update status message with live server progress
              setMessages(prev => {
                const next = [...prev];
                const msg = next[next.length - 1];
                if (msg && msg.isThinking) {
                  msg.content = data.content || (data.stage === 'generating' 
                    ? (isOfflineModeActive ? 'Synthesizing local response with Phi-3...' : 'Synthesizing answer...') 
                    : 'Searching notes and vector index...');
                }
                return next;
              });
            } else if (data.type === 'chunk') {
              assistantContent += data.content;
              setStreamingIdx(assistantIdx);
              setMessages(prev => {
                const next = [...prev];
                const msg = next[next.length - 1];
                if (msg.isThinking) {
                  msg.isThinking = false;
                  msg.content = ''; // Clear placeholder
                }
                msg.content = assistantContent;
                return next;
              });
            } else if (data.type === 'error') {
              setStreamingIdx(null);
              setMessages(prev => {
                const next = [...prev];
                const msg = next[next.length - 1];
                msg.isThinking = false;
                msg.isError = true;
                msg.content = `⚠️ Pipeline Failure: ${data.content || data.message || 'An error occurred during response generation'}.\n\n*Diagnostics:* Verify that Local Qdrant and Ollama (phi3:mini) are active, or inspect the System Diagnostics panel in the sidebar.`;
                return next;
              });
            } else if (data.type === 'metadata') {
              setStreamingIdx(null); // stop cursor
              setMessages(prev => {
                const next = [...prev];
                next[next.length - 1] = { ...next[next.length - 1], metadata: data };
                return next;
              });
              if (data.conversation_id && data.conversation_id !== activeConversationId) {
                setActiveConversationId(data.conversation_id);
                fetchConversations();
              }
            }
          } catch {
            /* ignore parse errors on partial lines */
          }
        }
      }
      setStreamingIdx(null);
    } catch (error) {
      console.error('Chat error:', error);
      toast({
        title: 'Connection Issue',
        description: error.message || 'Failed to communicate with KnowledgeOS backend.',
        variant: 'destructive',
      });
      setMessages(prev => {
        const next = [...prev];
        next[next.length - 1] = {
          role: 'assistant',
          content: `⚠️ Communication Failure: ${error.message || 'Failed to connect to backend server'}.\n\n*Troubleshooting Tips:*\n1. Check if the backend is running (` + '`./start_web.sh`' + `)\n2. If offline, ensure **Offline Local Mode** is toggled in the sidebar.\n3. Open **System Diagnostics** (activity icon in the sidebar) to verify subsystems.`,
          isError: true,
        };
        return next;
      });
      setIsLoading(false);
      setStreamingIdx(null);
    }
  };

  const handleCitationClick = useCallback(async (e, cit) => {
    e.preventDefault();
    if (cit.document_id && cit.document_id !== 'GRAPH') {
      try {
        const response = await api.get(`/api/v1/documents/${cit.document_id}/download`);
        if (response.data?.data) {
          window.open(response.data.data, '_blank');
        } else {
          toast({ title: 'Error', description: 'Could not generate download link', variant: 'destructive' });
        }
      } catch (err) {
        toast({ title: 'Error', description: 'Failed to download document', variant: 'destructive' });
      }
    } else if (cit.source_url) {
      window.open(cit.source_url, '_blank');
    }
  }, [toast]);

  const renderBackendBadge = useCallback((backend) => {
    if (backend === 'neo4j') return (
      <span key="neo4j" className="inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
        <Network className="w-3 h-3" /> Graph
      </span>
    );
    if (backend === 'qdrant') return (
      <span key="qdrant" className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[10px] font-semibold bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400 uppercase tracking-wider border">
        <Database className="w-3 h-3" /> Vector
      </span>
    );
    if (backend === 'postgresql') return (
      <span key="postgresql" className="inline-flex items-center gap-1 px-2 py-1 rounded text-[10px] font-medium bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400">
        <Database className="w-3 h-3" /> Catalog
      </span>
    );
    return null;
  }, []);

  return (
    <div className="flex flex-col md:flex-row h-screen w-full bg-slate-50/50 dark:bg-slate-950 p-4 gap-6">

      {/* ── Sidebar ──────────────────────────────────────────────────── */}
      <div className="w-full md:w-80 shrink-0 flex flex-col bg-white/90 dark:bg-slate-900/90 backdrop-blur-md rounded-2xl border shadow-sm p-4 overflow-hidden h-[calc(100vh-2rem)]">
        
        {/* Brand Header */}
        <div className="flex items-center justify-between pb-3 border-b border-slate-100 dark:border-slate-800 shrink-0">
          <div className="flex items-center gap-2.5">
            <Button
              variant="ghost" size="icon"
              onClick={() => navigate(-1)}
              className="h-8 w-8 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800 shrink-0"
            >
              <ChevronLeft className="w-4 h-4 text-slate-600 dark:text-slate-300" />
            </Button>
            <div className="p-2 bg-gradient-to-br from-primary/20 to-primary/5 rounded-lg text-primary shadow-sm border border-primary/10">
              <Sparkles className="w-4 h-4" />
            </div>
            <div>
              <h1 className="text-sm font-bold leading-none mb-0.5 text-slate-800 dark:text-slate-100">KnowledgeOS</h1>
              <p className="text-[10px] text-slate-500 font-medium uppercase tracking-wider">Academic AI</p>
            </div>
          </div>

          <Button
            variant="ghost"
            size="icon"
            onClick={openDiagnosticsModal}
            className="h-7 w-7 rounded-lg text-slate-400 hover:text-primary hover:bg-slate-100 dark:hover:bg-slate-800"
            title="System Diagnostics & Telemetry"
          >
            <Activity className="w-4 h-4" />
          </Button>
        </div>

        {/* Mode Switcher Segmented Control */}
        <div className="flex bg-slate-100 dark:bg-slate-800/80 p-1 rounded-xl my-3 shrink-0">
          <button
            onClick={() => setOfflineMode(false)}
            className={`flex-1 py-1.5 text-[11px] font-semibold rounded-lg transition-all flex items-center justify-center gap-1.5 ${
              !isOfflineModeActive
                ? 'bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 shadow-sm'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            Campus Courses
          </button>
          <button
            onClick={() => setOfflineMode(true)}
            className={`flex-1 py-1.5 text-[11px] font-semibold rounded-lg transition-all flex items-center justify-center gap-1.5 ${
              isOfflineModeActive
                ? 'bg-amber-500 text-white shadow-sm'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
            }`}
          >
            <Zap className="w-3.5 h-3.5" />
            Local Dropzone
          </button>
        </div>

        {/* ── Mode 1: Offline Local Library ── */}
        {isOfflineModeActive ? (
          <div className="flex flex-col flex-1 min-h-0 animate-in fade-in duration-200">
            {/* Watcher Health Card */}
            <div className="bg-amber-50/80 dark:bg-amber-950/20 border border-amber-200/80 dark:border-amber-900/40 rounded-xl p-2.5 mb-3 shrink-0">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-amber-800 dark:text-amber-300 flex items-center gap-1.5">
                  <FolderOpen className="w-3.5 h-3.5" /> Dropzone Active
                </span>
                <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold uppercase ${
                  watcherHealth?.status === 'running' 
                    ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/50 dark:text-emerald-400' 
                    : 'bg-red-100 text-red-700'
                }`}>
                  {watcherHealth?.status === 'running' ? 'Watcher: OK' : 'Watcher: Error'}
                </span>
              </div>
              <p className="text-[10px] text-amber-700/80 dark:text-amber-400/80 mt-1 font-mono truncate">
                ~/KgpOne_Dropzone
              </p>
            </div>

            {/* Document Header & Select All */}
            <div className="flex items-center justify-between pb-2 mb-1 border-b border-slate-100 dark:border-slate-800 shrink-0">
              <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                <HardDrive className="w-3.5 h-3.5" /> Local Library ({localDocuments.length})
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={fetchLocal}
                  className="p-1 text-slate-400 hover:text-slate-600 transition-colors"
                  title="Refresh library"
                >
                  <RefreshCw className="w-3 h-3" />
                </button>
                {localDocuments.length > 0 && (
                  <button
                    onClick={() => {
                      const completed = localDocuments.filter(d => d.status === 'COMPLETED');
                      if (selectedLocalDocIds.length === completed.length) {
                        setSelectedLocalDocIds([]);
                      } else {
                        setSelectedLocalDocIds(completed.map(d => d.id));
                      }
                    }}
                    className="text-[10px] text-primary hover:underline font-medium"
                  >
                    {selectedLocalDocIds.length === localDocuments.filter(d=>d.status==='COMPLETED').length ? 'Deselect' : 'Select All'}
                  </button>
                )}
              </div>
            </div>

            {/* Document Cards Scroll Area */}
            <div className="flex-1 overflow-y-auto min-h-0 space-y-1.5 pr-1 py-1">
              {localDocuments.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-8 text-center px-2">
                  <WifiOff className="w-7 h-7 text-slate-300 dark:text-slate-700 mb-2" />
                  <p className="text-[11px] font-medium text-slate-600 dark:text-slate-400">No local files yet</p>
                  <p className="text-[10px] text-slate-400 mt-1">
                    Drop a PDF into <code className="text-amber-600 font-mono">~/KgpOne_Dropzone</code> to automatically index.
                  </p>
                </div>
              ) : (
                localDocuments.map(doc => {
                  const isCompleted = doc.status === 'COMPLETED';
                  const isPending = doc.status === 'PENDING';
                  const isProcessing = doc.status === 'PROCESSING';
                  const isSelected = selectedLocalDocIds.includes(doc.id);

                  return (
                    <label
                      key={doc.id}
                      className={`flex items-start gap-2.5 p-2 rounded-xl border transition-all ${
                        isCompleted
                          ? isSelected
                            ? 'bg-amber-500/10 border-amber-500/30 text-amber-900 dark:text-amber-200 cursor-pointer shadow-xs'
                            : 'bg-white dark:bg-slate-900/60 border-slate-200/80 dark:border-slate-800 hover:border-amber-300 cursor-pointer'
                          : 'opacity-60 cursor-not-allowed border-slate-100 bg-slate-50 dark:bg-slate-900/20'
                      }`}
                    >
                      {isCompleted ? (
                        <input
                          type="checkbox"
                          className="mt-0.5 h-3.5 w-3.5 rounded border-slate-300 text-amber-500 focus:ring-amber-400 transition-all shrink-0"
                          checked={isSelected}
                          onChange={() => toggleLocalDoc(doc.id)}
                        />
                      ) : (
                        <div className="mt-0.5 h-3.5 w-3.5 shrink-0 flex items-center justify-center">
                          {(isPending || isProcessing) && <Loader2 className="w-3 h-3 text-amber-400 animate-spin" />}
                        </div>
                      )}
                      <div className="flex flex-col min-w-0 flex-1">
                        <span className="text-[11px] font-semibold truncate leading-tight" title={doc.title}>
                          {doc.title}
                        </span>
                        <div className="flex items-center gap-1.5 mt-1 text-[9px] text-slate-400">
                          <span>{doc.format} • {((doc.file_size_bytes || 0) / 1024 / 1024).toFixed(1)} MB</span>
                          <span className={`px-1 py-0.2 rounded font-bold uppercase text-[8px] ${
                            isCompleted ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400' :
                            isProcessing ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-400' :
                            'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400'
                          }`}>
                            {isCompleted ? '✓ Ready' : isProcessing ? 'Indexing' : 'Queued'}
                          </span>
                        </div>
                      </div>
                    </label>
                  );
                })
              )}
            </div>

            {/* Bottom Local Status Banner */}
            <div className="pt-2 mt-2 border-t border-slate-100 dark:border-slate-800 shrink-0">
              <div className="text-[10px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 rounded-lg p-2 border border-amber-200/60 dark:border-amber-800/40 flex items-center justify-between">
                <span className="flex items-center gap-1 font-medium">
                  <CheckCircle2 className="w-3 h-3" />
                  {selectedLocalDocIds.length} file(s) active in RAG
                </span>
                <button
                  onClick={createNewChat}
                  className="text-primary hover:underline font-semibold"
                >
                  + New Chat
                </button>
              </div>
            </div>
          </div>
        ) : (
          /* ── Mode 2: Online Campus Courses ── */
          <div className="flex flex-col flex-1 min-h-0 animate-in fade-in duration-200">
            {/* Settings Accordion */}
            <div className="flex flex-col mb-3 shrink-0">
              <button
                onClick={() => setSettingsOpen(o => !o)}
                className="flex items-center justify-between w-full py-1.5 group border-b border-slate-100 dark:border-slate-800"
              >
                <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5 group-hover:text-slate-700 dark:group-hover:text-slate-300 transition-colors">
                  <SettingsIcon size={13} className="text-slate-400" /> Course Settings
                </h2>
                <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-200 ${settingsOpen ? 'rotate-180' : ''}`} />
              </button>

              {settingsOpen && (
                <div className="flex flex-col gap-3 pt-3 animate-in slide-in-from-top-1 fade-in duration-150">
                  <Select value={selectedDeptId} onValueChange={(val) => {
                    setSelectedDeptId(val === 'all' ? '' : val);
                    setSelectedCourseId('');
                    setSelectedOfferingId('');
                  }}>
                    <SelectTrigger className="h-8 text-[11px] rounded-lg bg-slate-50/50 dark:bg-slate-900 border-slate-200 dark:border-slate-700 shadow-sm">
                      <SelectValue placeholder="1. Department" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Any Department</SelectItem>
                      {departments.map(d => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}
                    </SelectContent>
                  </Select>

                  <Select value={selectedCourseId} onValueChange={(val) => {
                    setSelectedCourseId(val === 'all' ? '' : val);
                    setSelectedOfferingId('');
                  }} disabled={!selectedDeptId}>
                    <SelectTrigger className="h-8 text-[11px] rounded-lg bg-slate-50/50 dark:bg-slate-900 border-slate-200 dark:border-slate-700 shadow-sm" disabled={!selectedDeptId}>
                      <SelectValue placeholder="2. Course" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Any Course</SelectItem>
                      {filteredCourses.map(c => <SelectItem key={c.id} value={c.id}>{c.code}</SelectItem>)}
                    </SelectContent>
                  </Select>

                  <div className="pt-0.5">
                    <label className="text-[11px] font-medium text-slate-600 dark:text-slate-300 flex items-center cursor-pointer select-none">
                      <input
                        type="checkbox"
                        checked={useCitations}
                        onChange={(e) => setUseCitations(e.target.checked)}
                        className="mr-2 h-3 w-3 rounded border-slate-300 text-primary"
                      />
                      Enable Inline Citations
                    </label>
                  </div>

                  {/* Analysis Mode Toggle */}
                  <div className="flex rounded-lg overflow-hidden border border-slate-200 dark:border-slate-700 shadow-xs">
                    <button
                      onClick={() => setAnalysisMode('general')}
                      className={`flex-1 py-1.5 text-[10px] font-semibold transition-all ${
                        analysisMode === 'general' ? 'bg-slate-700 text-white' : 'bg-slate-50 dark:bg-slate-900 text-slate-500'
                      }`}
                    >
                      General
                    </button>
                    <button
                      onClick={() => setAnalysisMode('basic')}
                      className={`flex-1 py-1.5 text-[10px] font-semibold transition-all ${
                        analysisMode === 'basic' ? 'bg-primary text-white' : 'bg-slate-50 dark:bg-slate-900 text-slate-500'
                      }`}
                    >
                      Basic
                    </button>
                    <button
                      onClick={() => setAnalysisMode('advanced')}
                      className={`flex-1 py-1.5 text-[10px] font-semibold transition-all ${
                        analysisMode === 'advanced' ? 'bg-gradient-to-r from-violet-600 to-pink-600 text-white' : 'bg-slate-50 dark:bg-slate-900 text-slate-500'
                      }`}
                    >
                      Agent
                    </button>
                  </div>
                </div>
              )}
            </div>

            {/* Recent Chats */}
            <div className="flex flex-col flex-1 min-h-0 pt-2 border-t border-slate-100 dark:border-slate-800">
              <div className="flex items-center justify-between mb-1.5 shrink-0">
                <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                  <MessageSquare size={13} className="text-slate-400" /> Recent Chats
                </h2>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-6 w-6 rounded hover:bg-slate-100 dark:hover:bg-slate-800"
                  onClick={createNewChat}
                  title="New Chat"
                >
                  <Plus className="w-3.5 h-3.5 text-slate-500" />
                </Button>
              </div>

              <div className="flex-1 overflow-y-auto min-h-0 space-y-1 pr-1">
                {conversations.length === 0 ? (
                  <p className="text-[11px] text-slate-400 py-3 text-center">No recent chats</p>
                ) : (
                  conversations.map(conv => (
                    <div key={conv.id} className="relative group">
                      <button
                        onClick={() => loadConversation(conv.id)}
                        className={`w-full text-left px-2 py-1.5 pr-7 text-[11px] rounded-lg transition-all truncate border ${
                          activeConversationId === conv.id
                            ? 'bg-primary/10 border-primary/20 text-primary font-medium dark:bg-primary/20'
                            : 'bg-transparent border-transparent text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800'
                        }`}
                      >
                        {conv.title || 'Untitled Conversation'}
                      </button>
                      <button
                        onClick={(e) => deleteConversation(conv.id, e)}
                        className="absolute right-1.5 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-red-500 opacity-0 group-hover:opacity-100 transition-opacity"
                        title="Delete Chat"
                      >
                        <Trash2 className="w-3 h-3" />
                      </button>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        )}

        {/* Footer actions */}
        <div className="pt-2 mt-auto border-t border-slate-100 dark:border-slate-800 shrink-0 flex items-center justify-between text-[11px]">
          <button
            onClick={() => setMemoriesOpen(true)}
            className="text-slate-500 hover:text-primary flex items-center gap-1 py-1"
          >
            <Sparkles className="w-3 h-3" /> Memory
          </button>
          <button
            onClick={openDiagnosticsModal}
            className="text-slate-500 hover:text-primary flex items-center gap-1 py-1"
          >
            <Activity className="w-3 h-3" /> Diagnostics
          </button>
        </div>
      </div>

      {/* ── Main chat area ────────────────────────────────────────────── */}
      <div className="flex-1 flex flex-col min-h-0 bg-transparent rounded-2xl max-w-5xl mx-auto w-full relative">
        
        {/* Top Header / Share */}
        <div className="absolute top-2 right-2 z-10 flex gap-2">
          {activeConversationId && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleShareToggle}
              className={`h-8 gap-1.5 rounded-full text-[11px] font-medium border-slate-200 dark:border-slate-800 shadow-sm bg-white/80 dark:bg-slate-900/80 backdrop-blur ${isShared ? 'text-primary border-primary/30' : 'text-slate-500 hover:text-slate-700'}`}
            >
              <Share2 className="w-3.5 h-3.5" />
              {isShared ? 'Shared Publicly' : 'Share'}
            </Button>
          )}
        </div>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-2 py-4 space-y-8 no-scrollbar scroll-smooth">
          {isChatLoading ? (
            <div className="flex flex-col gap-8 p-4">
              <div className="flex gap-4">
                <div className="w-9 h-9 rounded-full bg-slate-200 dark:bg-slate-800 animate-pulse shrink-0"></div>
                <div className="h-24 bg-white border border-slate-200 dark:bg-slate-900 dark:border-slate-800 animate-pulse rounded-3xl rounded-tl-sm w-3/4 shadow-sm"></div>
              </div>
              <div className="flex gap-4 flex-row-reverse">
                <div className="w-9 h-9 rounded-full bg-slate-200 dark:bg-slate-800 animate-pulse shrink-0"></div>
                <div className="h-16 bg-primary/20 animate-pulse rounded-3xl rounded-tr-sm w-1/2 shadow-sm"></div>
              </div>
              <div className="flex gap-4">
                <div className="w-9 h-9 rounded-full bg-slate-200 dark:bg-slate-800 animate-pulse shrink-0"></div>
                <div className="h-32 bg-white border border-slate-200 dark:bg-slate-900 dark:border-slate-800 animate-pulse rounded-3xl rounded-tl-sm w-2/3 shadow-sm"></div>
              </div>
            </div>
          ) : (
            messages.map((msg, idx) => {
              if (msg.role === 'assistant' && msg.content === '' && !msg.metadata && !msg.isError) return null;
              return (
                <ChatMessage
                  key={idx}
                  index={idx}
                  msg={msg}
                  isStreaming={streamingIdx === idx}
                  handleCitationClick={handleCitationClick}
                  renderBackendBadge={renderBackendBadge}
                />
              );
            })
          )}
          {isLoading && !isChatLoading && <LoadingDots />}
        </div>

        {/* Input */}
        <div className="pt-4 pb-2 shrink-0">
          <form onSubmit={handleSubmit} className="flex items-end gap-3 max-w-4xl mx-auto">
            <div className="relative flex-1 bg-white dark:bg-slate-900 rounded-3xl shadow-sm border border-slate-200/80 dark:border-slate-800 focus-within:ring-4 focus-within:ring-primary/10 focus-within:border-primary/30 transition-all duration-300">
              <Input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder={selectedCourseId ? 'Ask about the selected course...' : 'Ask about a topic, prerequisites, formulas, or figures...'}
                className="py-4 px-6 h-auto min-h-[60px] text-[15px] bg-transparent border-none shadow-none focus-visible:ring-0 resize-none rounded-3xl"
                disabled={isLoading}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit(e); }
                }}
              />
            </div>
            <Button
              type="submit"
              size="icon"
              disabled={!input.trim() || isLoading}
              className="h-[60px] w-[60px] rounded-3xl shadow-md shrink-0 bg-primary hover:bg-primary/90 transition-all duration-200 hover:scale-[1.04] active:scale-95 disabled:opacity-50 disabled:hover:scale-100"
            >
              <Send className="w-5 h-5 ml-0.5" />
            </Button>
          </form>
          <div className="flex items-center justify-between mt-3 px-1">
            <div className="flex items-center gap-1.5 text-[11px] text-slate-400 font-medium uppercase tracking-wide">
              <Bot className="w-3.5 h-3.5" />
              <span>AI responses may be inaccurate.</span>
            </div>
            <div className="flex items-center gap-1.5">
              {analysisMode === 'advanced' && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-gradient-to-r from-violet-100 to-pink-100 dark:from-violet-900/30 dark:to-pink-900/30 text-violet-700 dark:text-violet-300 border border-violet-200 dark:border-violet-800">
                  <Brain className="w-2.5 h-2.5" /> Agent
                </span>
              )}
              {byokKey && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 dark:bg-emerald-900/30 text-emerald-700 dark:text-emerald-400 border border-emerald-200 dark:border-emerald-800">
                  <Lock className="w-2.5 h-2.5" /> BYOK
                </span>
              )}
            </div>
          </div>
        </div>
      </div>
      {/* Memory Viewer Dialog */}
      <Dialog open={memoriesOpen} onOpenChange={setMemoriesOpen}>
        <DialogContent className="sm:max-w-md max-h-[80vh] flex flex-col p-0">
          <DialogHeader className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 shrink-0">
            <DialogTitle className="flex items-center gap-2 text-primary">
              <Sparkles className="w-5 h-5" />
              AI Memory
            </DialogTitle>
          </DialogHeader>
          
          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
            <p className="text-[13px] text-slate-500 mb-4 leading-relaxed">
              These are the facts the assistant has learned about you across all conversations to personalize its responses.
            </p>
            
            {memoriesLoading ? (
              <div className="space-y-3">
                {[1, 2, 3].map(i => (
                  <div key={i} className="animate-pulse flex p-3 rounded-xl border border-slate-100 bg-slate-50 dark:bg-slate-900/50 dark:border-slate-800">
                    <div className="h-4 bg-slate-200 dark:bg-slate-800 rounded w-3/4"></div>
                  </div>
                ))}
              </div>
            ) : memories.length === 0 ? (
              <div className="text-center py-10 bg-slate-50 dark:bg-slate-900/50 rounded-xl border border-slate-100 dark:border-slate-800 border-dashed">
                <Sparkles className="w-8 h-8 text-slate-300 dark:text-slate-700 mx-auto mb-2" />
                <div className="text-slate-500 font-medium text-sm">No memories found</div>
                <div className="text-slate-400 text-xs mt-1">The assistant hasn't learned any specific facts about you yet.</div>
              </div>
            ) : (
              <ul className="space-y-3 pb-2">
                {memories.map(memory => (
                  <li key={memory.id} className="p-3.5 rounded-xl border border-slate-200 bg-white shadow-sm dark:bg-slate-900/80 dark:border-slate-800/80 text-[13px] flex gap-3 text-slate-700 dark:text-slate-300 items-start">
                    <div className="bg-primary/10 text-primary p-1 rounded-full mt-0.5 shrink-0">
                      <Sparkles className="w-3.5 h-3.5" />
                    </div>
                    <span className="leading-relaxed pt-0.5">{memory.fact}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </DialogContent>
      </Dialog>

      {/* System Diagnostics & Telemetry Dialog */}
      <Dialog open={diagnosticsOpen} onOpenChange={setDiagnosticsOpen}>
        <DialogContent className="sm:max-w-lg max-h-[85vh] flex flex-col p-0">
          <DialogHeader className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 shrink-0">
            <div className="flex items-center justify-between">
              <DialogTitle className="flex items-center gap-2 text-primary text-base">
                <Activity className="w-5 h-5 text-primary" />
                System Health & Diagnostics
              </DialogTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={fetchDiagnostics}
                disabled={isDiagnosticsLoading}
                className="h-7 text-xs gap-1.5 text-slate-500 hover:text-primary"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isDiagnosticsLoading ? 'animate-spin' : ''}`} />
                Refresh
              </Button>
            </div>
          </DialogHeader>

          <div className="flex-1 overflow-y-auto px-6 py-4 space-y-3">
            <p className="text-[12px] text-slate-500 leading-relaxed">
              Live status across hybrid online/offline subsystems. Pinpoints offline fallbacks, connection drops, and service statuses.
            </p>

            {isDiagnosticsLoading && !systemDiagnostics ? (
              <div className="space-y-2 py-4">
                {[1, 2, 3, 4].map(i => (
                  <div key={i} className="h-12 bg-slate-100 dark:bg-slate-800 animate-pulse rounded-xl" />
                ))}
              </div>
            ) : systemDiagnostics ? (
              <div className="space-y-2.5">
                {/* Cloud DB */}
                <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 flex items-center justify-between bg-white dark:bg-slate-900 shadow-xs">
                  <div>
                    <div className="text-[12px] font-semibold text-slate-800 dark:text-slate-200">Cloud PostgreSQL (Neon)</div>
                    <div className="text-[10px] text-slate-500">{systemDiagnostics.cloud_database?.description}</div>
                    {systemDiagnostics.cloud_database?.action && (
                      <div className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5">{systemDiagnostics.cloud_database.action}</div>
                    )}
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                    systemDiagnostics.cloud_database?.status === 'online' 
                      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400' 
                      : 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-400'
                  }`}>
                    {systemDiagnostics.cloud_database?.status}
                  </span>
                </div>

                {/* Local DB */}
                <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 flex items-center justify-between bg-white dark:bg-slate-900 shadow-xs">
                  <div>
                    <div className="text-[12px] font-semibold text-slate-800 dark:text-slate-200">Local Database (SQLite)</div>
                    <div className="text-[10px] text-slate-500">kgpone_offline.db • {systemDiagnostics.local_database?.active_documents || 0} active local documents</div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
                    {systemDiagnostics.local_database?.status}
                  </span>
                </div>

                {/* Local Ollama */}
                <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 flex items-center justify-between bg-white dark:bg-slate-900 shadow-xs">
                  <div>
                    <div className="text-[12px] font-semibold text-slate-800 dark:text-slate-200">Local AI Daemon (Ollama)</div>
                    <div className="text-[10px] text-slate-500">
                      {systemDiagnostics.local_llm_ollama?.models?.length > 0 
                        ? `Available Models: ${systemDiagnostics.local_llm_ollama.models.join(', ')}` 
                        : 'Host: 127.0.0.1:11434'}
                    </div>
                    {systemDiagnostics.local_llm_ollama?.action && (
                      <div className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5">{systemDiagnostics.local_llm_ollama.action}</div>
                    )}
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                    systemDiagnostics.local_llm_ollama?.status === 'ready' 
                      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400' 
                      : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                  }`}>
                    {systemDiagnostics.local_llm_ollama?.status}
                  </span>
                </div>

                {/* Local Qdrant */}
                <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 flex items-center justify-between bg-white dark:bg-slate-900 shadow-xs">
                  <div>
                    <div className="text-[12px] font-semibold text-slate-800 dark:text-slate-200">Local Vector Store</div>
                    <div className="text-[10px] text-slate-500">{systemDiagnostics.local_vector_store?.description}</div>
                  </div>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400">
                    {systemDiagnostics.local_vector_store?.status}
                  </span>
                </div>

                {/* Dropzone Watcher */}
                <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 flex items-center justify-between bg-white dark:bg-slate-900 shadow-xs">
                  <div>
                    <div className="text-[12px] font-semibold text-slate-800 dark:text-slate-200">Dropzone Ingestion Supervisor</div>
                    <div className="text-[10px] text-slate-500">
                      Directory: ~/KgpOne_Dropzone ({systemDiagnostics.dropzone_watcher?.pdf_files_in_folder || 0} PDFs in folder)
                    </div>
                  </div>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                    systemDiagnostics.dropzone_watcher?.status === 'running' 
                      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-400' 
                      : 'bg-red-100 text-red-700'
                  }`}>
                    {systemDiagnostics.dropzone_watcher?.status}
                  </span>
                </div>
              </div>
            ) : (
              <div className="text-center py-6 text-slate-400 text-xs">
                Could not retrieve diagnostics data.
              </div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
};

export default Chat;
