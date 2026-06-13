"use client";

import React, { useState, useEffect, useRef } from "react";
import { 
  Shield, 
  Send, 
  User, 
  Database, 
  FileText, 
  Lock, 
  Unlock,
  AlertTriangle,
  RefreshCw,
  LogOut,
  ChevronRight,
  BookOpen
} from "lucide-react";

interface Source {
  source_document: string;
  section_title: string;
  collection: string;
}

interface Message {
  id: string;
  sender: "user" | "bot";
  text: string;
  role?: string;
  retrieval_type?: "hybrid_rag" | "sql_rag";
  sources?: Source[];
  isBlocked?: boolean;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const DEMO_ACCOUNTS = [
  { username: "dr.mehta", role: "doctor", name: "Dr. Mehta", dept: "Clinical Services" },
  { username: "nurse.priya", role: "nurse", name: "Nurse Priya", dept: "Ward & ICU" },
  { username: "billing.ravi", role: "billing_executive", name: "Ravi Sharma", dept: "Billing & Claims" },
  { username: "tech.anand", role: "tech.anand", displayName: "tech.anand / technician", actualUsername: "tech.anand", roleLabel: "technician", name: "Anand Verma", dept: "Medical Equipment" },
  { username: "admin.sys", role: "admin", name: "Sys Admin", dept: "IT & Executive" }
];

const SUGGESTED_QUESTIONS: Record<string, { q: string; label: string; expectBlock?: boolean }[]> = {
  doctor: [
    { q: "What is the standard treatment protocol for managing diabetic patients?", label: "Clinical protocol" },
    { q: "Show me the standard drug formulary details.", label: "Drug formulary" },
    { q: "What are the ICU nursing procedures?", label: "Nursing guide" },
    { q: "Show me the insurance billing codes for cardiology.", label: "Try Billing (Adversarial)", expectBlock: true }
  ],
  nurse: [
    { q: "What are the ICU nursing procedures for patient care?", label: "Nursing guide" },
    { q: "What is the leave policy for staff?", label: "Leave policy (General)" },
    { q: "Show me standard treatment protocols.", label: "Try Clinical (Adversarial)", expectBlock: true },
    { q: "What is the calibration guide for equipment?", label: "Try Equipment (Adversarial)", expectBlock: true }
  ],
  billing_executive: [
    { q: "What is the procedure for cashless claim submission?", label: "Billing guide" },
    { q: "How many claims are pending in the cardiology department?", label: "Pending Claims count (SQL RAG)" },
    { q: "What is the total claimed amount for resolved claims?", label: "Claims statistics (SQL RAG)" },
    { q: "Show me the clinical treatment protocols for tuberculosis.", label: "Try Clinical (Adversarial)", expectBlock: true }
  ],
  technician: [
    { q: "What is the calibration schedule for infusion pumps?", label: "Equipment manual" },
    { q: "What is the code of conduct for hospital employees?", label: "General FAQs" },
    { q: "How many maintenance tickets are in progress?", label: "Try SQL RAG (Adversarial)", expectBlock: true },
    { q: "What are the nursing ICU guidelines?", label: "Try Nursing (Adversarial)", expectBlock: true }
  ],
  admin: [
    { q: "How many claims were submitted in 2024?", label: "Claims count (SQL RAG)" },
    { q: "Which campus raised the most maintenance tickets?", label: "Tickets analysis (SQL RAG)" },
    { q: "What are the diagnostic reference guidelines?", label: "Clinical reference" },
    { q: "What are the ICU infection control guidelines?", label: "Nursing reference" }
  ]
};

const COLLECTION_LABELS: Record<string, string> = {
  general: "General (HR & Policy)",
  clinical: "Clinical Protocols & Formulary",
  nursing: "Nursing Procedures",
  billing: "Billing & Claims",
  equipment: "Equipment Manuals"
};

export default function Home() {
  // Authentication State
  const [token, setToken] = useState<string | null>(null);
  const [userRole, setUserRole] = useState<string | null>(null);
  const [userName, setUserName] = useState<string | null>(null);
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);

  // Chat State
  const [messages, setMessages] = useState<Message[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [accessibleCollections, setAccessibleCollections] = useState<string[]>([]);
  const [apiStatus, setApiStatus] = useState<"connecting" | "healthy" | "error">("connecting");

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Check backend health on mount
  useEffect(() => {
    fetch(`${API_BASE}/health`)
      .then(res => res.json())
      .then(() => setApiStatus("healthy"))
      .catch(() => setApiStatus("error"));
  }, []);

  // Fetch allowed collections when role changes
  useEffect(() => {
    if (userRole) {
      fetch(`${API_BASE}/collections/${userRole}`)
        .then(res => res.json())
        .then(data => setAccessibleCollections(data.accessible_collections))
        .catch(err => console.error("Error fetching collections:", err));
    }
  }, [userRole]);

  // Scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, chatLoading]);

  // Handle Login
  const handleLogin = async (username: string, roleInput: string) => {
    setAuthLoading(true);
    setAuthError(null);
    try {
      // Passwords are set equal to the role name
      const res = await fetch(`${API_BASE}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password: roleInput }),
      });

      if (!res.ok) {
        throw new Error("Invalid credentials");
      }

      const data = await res.json();
      setToken(data.access_token);
      setUserRole(data.role);
      setUserName(data.username);
      
      // Clear previous chats
      setMessages([
        {
          id: "welcome",
          sender: "bot",
          text: `Welcome back, ${data.username}! You are logged in as **${data.role}**. I can answer clinical, database, or policy questions according to your role boundaries.`,
          role: data.role
        }
      ]);
    } catch (err: any) {
      setAuthError(err.message || "Failed to log in");
    } finally {
      setAuthLoading(false);
    }
  };

  // Handle Logout
  const handleLogout = () => {
    setToken(null);
    setUserRole(null);
    setUserName(null);
    setMessages([]);
    setAccessibleCollections([]);
  };

  // Handle Send Message
  const handleSendMessage = async (text: string) => {
    if (!text.trim() || chatLoading || !token) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: "user",
      text,
      role: userRole || undefined
    };

    setMessages(prev => [...prev, userMsg]);
    setInputMessage("");
    setChatLoading(true);

    try {
      const res = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: { 
          "Content-Type": "application/json",
          "Authorization": `Bearer ${token}`
        },
        body: JSON.stringify({ question: text }),
      });

      if (!res.ok) {
        const errorData = await res.json();
        throw new Error(errorData.detail || "Server error");
      }

      const data = await res.json();
      
      const isBlocked = data.answer.includes("Access Denied") || 
                        data.answer.includes("do not have access");

      const botMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: "bot",
        text: data.answer,
        role: data.role,
        retrieval_type: data.retrieval_type,
        sources: data.sources,
        isBlocked: isBlocked
      };

      setMessages(prev => [...prev, botMsg]);
    } catch (err: any) {
      setMessages(prev => [...prev, {
        id: (Date.now() + 1).toString(),
        sender: "bot",
        text: `Error: ${err.message || "Could not retrieve response from backend."}`,
        isBlocked: true
      }]);
    } finally {
      setChatLoading(false);
    }
  };

  if (!token) {
    // ----------------------------------------
    // LOGIN SCREEN
    // ----------------------------------------
    return (
      <main className="relative min-h-screen flex items-center justify-center p-4 bg-[#090d16] text-white">
        {/* Glow Effects */}
        <div className="glow-spot-blue -top-20 -left-20"></div>
        <div className="glow-spot-purple -bottom-20 -right-20"></div>

        <div className="w-full max-w-2xl glass-panel rounded-2xl p-8 border border-white/5 relative z-10">
          <div className="flex flex-col items-center mb-8">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-sky-500/20 mb-4">
              <Shield className="w-8 h-8 text-white" />
            </div>
            <h1 className="text-3xl font-extrabold tracking-tight bg-gradient-to-r from-white via-slate-200 to-sky-400 bg-clip-text text-transparent">
              MediBot Portal
            </h1>
            <p className="text-sm text-slate-400 mt-2 text-center max-w-md">
              Secure Clinical Intelligence & Role-Based Access Control Assistant for MediAssist Health Network.
            </p>
          </div>

          <div className="mb-6">
            <h2 className="text-lg font-semibold text-slate-200 mb-4 flex items-center gap-2">
              <User className="w-5 h-5 text-sky-400" /> Select a Demo Account
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {DEMO_ACCOUNTS.map((acc) => {
                const actualUsername = acc.username;
                const roleLabel = acc.role === "tech.anand" ? "technician" : acc.role;
                return (
                  <button
                    key={acc.username}
                    onClick={() => handleLogin(actualUsername, roleLabel)}
                    className="glass-card text-left p-4 rounded-xl flex flex-col justify-between group hover:scale-[1.01] active:scale-[0.99]"
                  >
                    <div className="flex items-center justify-between w-full">
                      <span className="font-semibold text-white group-hover:text-sky-400 transition-colors">
                        {acc.name}
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-slate-400 uppercase tracking-wider font-mono">
                        {roleLabel}
                      </span>
                    </div>
                    <div className="mt-2 text-xs text-slate-400 flex flex-col">
                      <span>Dept: {acc.dept}</span>
                      <span className="text-[10px] font-mono text-slate-500 mt-1">
                        User: {actualUsername} | Pass: {roleLabel}
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {authLoading && (
            <div className="flex justify-center items-center gap-2 text-sky-400 text-sm">
              <RefreshCw className="w-4 h-4 animate-spin" /> Authenticating Session...
            </div>
          )}

          {authError && (
            <div className="p-3 bg-red-950/50 border border-red-500/20 text-red-400 text-sm rounded-lg flex items-center gap-2 mb-4">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              <span>{authError}</span>
            </div>
          )}

          <div className="mt-8 border-t border-white/5 pt-6 flex items-center justify-between text-xs text-slate-500">
            <div className="flex items-center gap-2">
              <span className={`w-2.5 h-2.5 rounded-full ${apiStatus === "healthy" ? "bg-emerald-500 animate-pulse" : apiStatus === "connecting" ? "bg-amber-500 animate-pulse" : "bg-red-500"}`} />
              <span>Backend Server: {apiStatus}</span>
            </div>
            <span>MediAssist | Confidential</span>
          </div>
        </div>
      </main>
    );
  }

  // ----------------------------------------
  // CHAT SCREEN
  // ----------------------------------------
  const currentSuggested = SUGGESTED_QUESTIONS[userRole || ""] || [];

  return (
    <main className="relative min-h-screen flex bg-[#060810] text-slate-200">
      {/* Background radial glow */}
      <div className="glow-spot-blue top-0 left-0"></div>
      <div className="glow-spot-purple bottom-0 right-0"></div>

      {/* 1. SIDEBAR PANEL */}
      <aside className="w-80 border-r border-white/5 bg-[#090d16]/80 backdrop-blur-xl flex flex-col relative z-20">
        <div className="p-6 border-b border-white/5 flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-sky-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-sky-500/10">
            <Shield className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="font-bold text-white text-base">MediBot Console</h1>
            <span className="text-[10px] text-slate-400 uppercase tracking-wider font-mono">v1.2 Advanced RAG</span>
          </div>
        </div>

        {/* User Card */}
        <div className="p-6 border-b border-white/5 bg-white/[0.01]">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-full bg-sky-950 border border-sky-500/20 flex items-center justify-center">
              <User className="w-5 h-5 text-sky-400" />
            </div>
            <div className="overflow-hidden">
              <h2 className="font-semibold text-white text-sm truncate">{userName}</h2>
              <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-medium bg-sky-500/10 text-sky-400 border border-sky-500/20 uppercase tracking-wider mt-1 font-mono">
                {userRole}
              </span>
            </div>
          </div>
          <button
            onClick={handleLogout}
            className="w-full mt-4 py-2 px-3 rounded-lg bg-white/5 hover:bg-red-950/30 border border-white/10 hover:border-red-500/20 text-xs text-slate-400 hover:text-red-400 flex items-center justify-center gap-2 transition-all"
          >
            <LogOut className="w-3.5 h-3.5" /> Sign Out Portal
          </button>
        </div>

        {/* Access Matrix List */}
        <div className="flex-1 overflow-y-auto p-6">
          <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-4 flex items-center gap-2">
            <Unlock className="w-4 h-4 text-emerald-400" /> Authorized Collections
          </h3>
          <div className="space-y-3">
            {accessibleCollections.map((col) => (
              <div key={col} className="p-3 rounded-lg bg-white/[0.02] border border-white/5 flex items-center gap-3">
                <FileText className="w-4 h-4 text-sky-400 flex-shrink-0" />
                <span className="text-xs font-medium text-slate-300">
                  {COLLECTION_LABELS[col] || col}
                </span>
              </div>
            ))}
            
            {/* Show blocked collections for adversarial testing context */}
            {Object.keys(COLLECTION_LABELS).map((col) => {
              if (!accessibleCollections.includes(col)) {
                return (
                  <div key={col} className="p-3 rounded-lg bg-red-950/10 border border-red-950/30 flex items-center justify-between gap-3 opacity-60">
                    <div className="flex items-center gap-3">
                      <Lock className="w-4 h-4 text-red-500 flex-shrink-0" />
                      <span className="text-xs font-medium text-slate-500 line-through">
                        {COLLECTION_LABELS[col]}
                      </span>
                    </div>
                    <span className="text-[9px] font-mono text-red-400 bg-red-950/30 border border-red-500/10 px-1 py-0.5 rounded uppercase">Blocked</span>
                  </div>
                );
              }
              return null;
            })}
          </div>
        </div>
      </aside>

      {/* 2. MAIN CHAT AREA */}
      <section className="flex-1 flex flex-col min-w-0 relative z-10">
        {/* Top Header */}
        <header className="h-16 border-b border-white/5 bg-[#090d16]/40 backdrop-blur-xl px-8 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs text-slate-400">Security Access Enforced at retrieval level (Qdrant Metadata Filter)</span>
          </div>
          <div className="text-xs text-slate-500 font-mono">
            DB: {apiStatus === "healthy" ? "Connected" : "Not Found"}
          </div>
        </header>

        {/* Message Panel */}
        <div className="flex-1 overflow-y-auto p-8 space-y-6">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex flex-col max-w-3xl ${
                msg.sender === "user" ? "ml-auto items-end" : "mr-auto items-start"
              }`}
            >
              {/* Sender label */}
              <div className="flex items-center gap-2 mb-1 px-1">
                <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider font-mono">
                  {msg.sender === "user" ? "User" : "MediBot"}
                </span>
                {msg.retrieval_type && (
                  <span className={`text-[9px] px-2 py-0.5 rounded font-mono font-medium border uppercase ${
                    msg.retrieval_type === "sql_rag" 
                      ? "bg-purple-500/10 text-purple-400 border-purple-500/20" 
                      : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                  }`}>
                    {msg.retrieval_type === "sql_rag" ? "SQL RAG" : "Hybrid RAG"}
                  </span>
                )}
              </div>

              {/* Message Bubble */}
              <div
                className={`p-4 rounded-2xl border ${
                  msg.sender === "user"
                    ? "bg-sky-600/15 border-sky-500/30 text-white rounded-tr-none"
                    : msg.isBlocked
                    ? "bg-red-950/20 border-red-500/30 text-red-200 rounded-tl-none shadow-glow-red"
                    : "bg-[#0d1423] border-white/5 text-slate-200 rounded-tl-none"
                }`}
              >
                {/* Refusal / Warning sign */}
                {msg.isBlocked && (
                  <div className="flex items-center gap-2 text-red-400 font-semibold text-xs uppercase tracking-wider mb-2 border-b border-red-500/20 pb-2">
                    <Lock className="w-4 h-4" /> RBAC Access Denied
                  </div>
                )}
                
                {/* Text render (markdown support placeholder) */}
                <div className="text-sm leading-relaxed whitespace-pre-wrap select-text">
                  {msg.text}
                </div>

                {/* Sources list */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-4 border-t border-white/5 pt-3">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 flex items-center gap-1.5 mb-2">
                      <BookOpen className="w-3.5 h-3.5 text-sky-400" /> Cited Sources:
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {msg.sources.map((src, i) => (
                        <div
                          key={i}
                          title={`Collection: ${src.collection}`}
                          className="flex items-center gap-1.5 px-2 py-1 rounded bg-white/5 border border-white/5 text-[11px] text-slate-300 hover:border-sky-500/30 cursor-default transition-all"
                        >
                          <FileText className="w-3 h-3 text-sky-400" />
                          <span className="font-medium">{src.source_document}</span>
                          <ChevronRight className="w-2.5 h-2.5 text-slate-500" />
                          <span className="text-slate-400 font-light truncate max-w-[150px]">{src.section_title}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {chatLoading && (
            <div className="flex items-center gap-3 max-w-lg mr-auto">
              <div className="w-10 h-10 rounded-full bg-sky-950/30 border border-sky-500/20 flex items-center justify-center animate-spin">
                <RefreshCw className="w-5 h-5 text-sky-400" />
              </div>
              <div className="text-xs text-sky-400 animate-pulse font-mono">Retrieving context & running reranker...</div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Quick Suggested Queries Panel */}
        {currentSuggested.length > 0 && (
          <div className="px-8 py-3 border-t border-white/5 bg-[#080b13]/80">
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 block mb-2">Suggested Queries & Adversarial Checks</span>
            <div className="flex flex-wrap gap-2">
              {currentSuggested.map((item, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSendMessage(item.q)}
                  className={`px-3 py-1.5 rounded-lg text-xs border transition-all duration-200 text-left ${
                    item.expectBlock 
                      ? "bg-red-950/15 border-red-500/20 hover:border-red-500/50 text-red-300 hover:bg-red-950/30" 
                      : "bg-[#0f1525] border-white/5 hover:border-sky-500/30 text-slate-300 hover:text-white"
                  }`}
                >
                  <span className="font-semibold block text-[10px] opacity-75 uppercase tracking-wider mb-0.5">
                    {item.label}
                  </span>
                  <span>{item.q}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Input Bar */}
        <div className="p-8 border-t border-white/5 bg-[#090d16]/50">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSendMessage(inputMessage);
            }}
            className="flex gap-4"
          >
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder={`Ask about clinical protocols, SQLite queries, or general FAQs...`}
              disabled={chatLoading}
              className="flex-1 px-4 py-3 rounded-xl bg-[#090d16] border border-white/5 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-sky-500/40 focus:ring-1 focus:ring-sky-500/20 disabled:opacity-55"
            />
            <button
              type="submit"
              disabled={chatLoading || !inputMessage.trim()}
              className="px-5 py-3 rounded-xl bg-sky-600 hover:bg-sky-500 text-white font-medium flex items-center justify-center gap-2 shadow-lg shadow-sky-600/10 transition-all disabled:opacity-50 disabled:hover:bg-sky-600"
            >
              <Send className="w-4 h-4" /> Send Query
            </button>
          </form>
        </div>
      </section>
    </main>
  );
}
