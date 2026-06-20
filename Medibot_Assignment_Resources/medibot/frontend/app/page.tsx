"use client";

import { useEffect, useMemo, useRef, useState } from "react";

const API_BASE = "http://localhost:8000";
const DEMO_ACCOUNTS = [
  { label: "Doctor", username: "dr.mehta", password: "doctor" },
  { label: "Nurse", username: "nurse.priya", password: "nurse" },
  { label: "Billing Executive", username: "billing.ravi", password: "billing_executive" },
  { label: "Technician", username: "tech.anand", password: "technician" },
  { label: "Admin", username: "admin.sys", password: "admin" },
];

interface UserSession {
  username: string;
  role: string;
  token: string;
}

interface ChatMessage {
  id: string;
  speaker: "user" | "bot";
  text: string;
  retrievalType?: string;
  sources?: Array<{ source_document: string; section_title?: string | null; collection: string; text_snippet: string }>;
  warning?: boolean;
}

const fetcher = (url: string, token?: string) =>
  fetch(url, {
    method: token ? "GET" : "GET",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  }).then(async (res) => {
    if (!res.ok) {
      throw new Error(await res.text());
    }
    return res.json();
  });

export default function Home() {
  const [session, setSession] = useState<UserSession | null>(null);
  const [loginError, setLoginError] = useState("");
  const [question, setQuestion] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [collections, setCollections] = useState<string[]>([]);
  const questionInputRef = useRef<HTMLInputElement>(null);

  const roleLabel = useMemo(() => {
    if (!session) return "Guest";
    return session.role
      .split("_")
      .map((word) => word[0].toUpperCase() + word.slice(1))
      .join(" ");
  }, [session]);

  useEffect(() => {
    if (!session) return;
    fetch(`${API_BASE}/collections/${session.role}`, {
      headers: { Authorization: `Bearer ${session.token}` },
    })
      .then(async (res) => {
        if (!res.ok) {
          throw new Error(await res.text());
        }
        const data = await res.json();
        setCollections(data.collections || []);
      })
      .catch(() => {
        setCollections([]);
      });
  }, [session]);

  useEffect(() => {
    if (session && !isSubmitting) {
      questionInputRef.current?.focus();
    }
  }, [session, isSubmitting, messages.length]);

  const handleLogin = async (username: string, password: string) => {
    setLoginError("");
    try {
      const response = await fetch(`${API_BASE}/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      const data = await response.json();
      if (!response.ok) {
        setLoginError(data.detail || "Login failed. Please check your credentials.");
        return;
      }
      setSession({ username: data.username, role: data.role, token: data.access_token });
      setMessages([]);
    } catch (error) {
      setLoginError("Unable to reach the API. Is the backend running?");
    }
  };

  const handleLogout = () => {
    setSession(null);
    setCollections([]);
    setMessages([]);
    setQuestion("");
    setLoginError("");
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!session || !question.trim()) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      speaker: "user",
      text: question.trim(),
    };
    setMessages((current) => [...current, userMessage]);
    setIsSubmitting(true);

    try {
      const response = await fetch(`${API_BASE}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.token}`,
        },
        body: JSON.stringify({ question: question.trim() }),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Chat request failed.");
      }

      const botMessage: ChatMessage = {
        id: `bot-${Date.now()}`,
        speaker: "bot",
        text: data.answer || data.message || "No answer returned.",
        retrievalType: data.retrieval_type,
        sources: data.sources || [],
        warning: !!data.message && !data.answer,
      };
      setMessages((current) => [...current, botMessage]);
      setQuestion("");
    } catch (error: any) {
      setMessages((current) => [
        ...current,
        {
          id: `bot-error-${Date.now()}`,
          speaker: "bot",
          text: error.message || "An unexpected error occurred.",
          warning: true,
        },
      ]);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!session) {
    return (
      <main className="min-h-screen bg-gradient-to-br from-medibot-50 to-white text-slate-900">
        <div className="mx-auto flex min-h-screen max-w-5xl items-center justify-center px-4 py-10">
          <div className="w-full rounded-[32px] border border-white/60 bg-white/80 p-8 shadow-glass backdrop-blur-xl">
            <div className="mb-8 text-center">
              <p className="text-sm uppercase tracking-[0.35em] text-medibot-700">MediBot</p>
              <h1 className="mt-4 text-4xl font-semibold text-slate-900">Clinical AI Concierge</h1>
              <p className="mt-2 text-slate-600">Login with a demo role to try RBAC-aware retrieval and SQL analytics.</p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              {DEMO_ACCOUNTS.map((account) => (
                <button
                  key={account.username}
                  className="rounded-3xl border border-slate-200 bg-slate-50 px-4 py-4 text-left transition hover:border-medibot-400 hover:bg-medibot-100"
                  onClick={() => handleLogin(account.username, account.password)}
                >
                  <div className="text-sm font-semibold text-slate-900">{account.label}</div>
                  <div className="text-xs text-slate-500">{account.username} / {account.password}</div>
                </button>
              ))}
            </div>

            {loginError ? (
              <div className="mt-6 rounded-3xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
                {loginError}
              </div>
            ) : null}
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-slate-950 text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-6xl flex-col px-4 py-6 sm:px-6">
        <header className="mb-6 flex flex-col gap-4 rounded-[32px] border border-slate-800 bg-slate-900/90 p-5 shadow-glass backdrop-blur-xl sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.35em] text-medibot-300">MediBot</p>
            <h1 className="mt-2 text-3xl font-semibold">Healthcare AI Assistant</h1>
            <p className="mt-1 text-sm text-slate-400">Role-based access, citation-aware answers, and SQL analytics.</p>
          </div>
          <div className="flex items-center gap-3 text-sm">
            <div className="rounded-3xl bg-slate-800 px-4 py-2 text-slate-200 shadow-inner">
              <span className="block text-xs uppercase tracking-[0.3em] text-slate-500">Role</span>
              <span className="font-semibold">{roleLabel}</span>
            </div>
            <button
              onClick={handleLogout}
              className="rounded-3xl border border-slate-700 bg-slate-800 px-4 py-2 text-slate-200 transition hover:border-medibot-500 hover:text-white"
            >
              Logout
            </button>
          </div>
        </header>

        <div className="grid flex-1 gap-6 xl:grid-cols-[320px_1fr]">
          <aside className="rounded-[32px] border border-slate-800 bg-slate-900/80 p-6 shadow-glass backdrop-blur-xl">
            <p className="text-sm uppercase tracking-[0.35em] text-medibot-300">Welcome, {session.username}</p>
            <h2 className="mt-3 text-xl font-semibold">Accessible Collections</h2>
            <div className="mt-4 flex flex-wrap gap-3">
              {collections.length > 0 ? (
                collections.map((collection) => (
                  <span key={collection} className="rounded-2xl bg-slate-800 px-3 py-2 text-sm text-slate-200">
                    {collection}
                  </span>
                ))
              ) : (
                <span className="rounded-2xl bg-slate-800 px-3 py-2 text-sm text-slate-400">No collections loaded</span>
              )}
            </div>
            <div className="mt-6 rounded-3xl border border-slate-800 bg-slate-950/70 p-4 text-sm leading-6 text-slate-400">
              <p className="font-semibold text-slate-100">Tip</p>
              <p>Try billing questions with billing_executive or admin, and clinical questions with doctor/nurse.</p>
            </div>
          </aside>

          <section className="flex min-h-[60vh] flex-col rounded-[32px] border border-slate-800 bg-slate-900/80 p-6 shadow-glass backdrop-blur-xl">
            <div className="mb-4 flex items-center justify-between gap-4">
              <div>
                <p className="text-sm uppercase tracking-[0.35em] text-medibot-300">Conversation</p>
                <h2 className="text-2xl font-semibold">Ask MediBot anything</h2>
              </div>
              <div className="rounded-3xl bg-slate-800 px-4 py-2 text-sm text-slate-200">
                {messages.length} messages
              </div>
            </div>

            <div className="mb-6 flex-1 space-y-4 overflow-y-auto rounded-3xl border border-slate-800 bg-slate-950/80 p-4">
              {messages.length === 0 ? (
                <div className="rounded-3xl border border-dashed border-slate-700 bg-slate-900/70 p-8 text-center text-slate-400">
                  Start with a question about claims, equipment maintenance, or clinical policies.
                </div>
              ) : (
                messages.map((message) => (
                  <div
                    key={message.id}
                    className={`rounded-3xl p-4 ${
                      message.speaker === "user"
                        ? "ml-auto w-full max-w-[70%] bg-medibot-500/20 text-medibot-100"
                        : "bg-slate-800"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs uppercase tracking-[0.35em] text-slate-400">
                        {message.speaker === "user" ? "You" : message.warning ? "RBAC" : "MediBot"}
                      </span>
                      {message.retrievalType ? (
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.25em] ${
                            message.retrievalType === "sql_rag"
                              ? "bg-amber-500/15 text-amber-200"
                              : "bg-cyan-500/15 text-cyan-200"
                          }`}
                        >
                          {message.retrievalType === "sql_rag" ? "SQL RAG" : "Hybrid RAG"}
                        </span>
                      ) : null}
                    </div>
                    <p className={`mt-3 whitespace-pre-wrap ${message.warning ? "text-amber-100" : "text-slate-100"}`}>
                      {message.text}
                    </p>
                    {message.sources && message.sources.length > 0 ? (
                      <details className="mt-4 rounded-3xl bg-slate-950/90 p-4 text-sm text-slate-300">
                        <summary className="cursor-pointer font-semibold text-slate-100">Source citations</summary>
                        <div className="mt-3 space-y-3">
                          {message.sources.map((source, index) => (
                            <div key={`${message.id}-source-${index}`} className="rounded-2xl border border-slate-800 bg-slate-900/90 p-3">
                              <p className="text-sm font-semibold text-slate-100">{source.source_document}</p>
                              <p className="text-xs text-slate-500">{source.collection}</p>
                              {source.section_title ? (
                                <p className="mt-1 text-sm text-slate-300">{source.section_title}</p>
                              ) : null}
                            </div>
                          ))}
                        </div>
                      </details>
                    ) : null}
                  </div>
                ))
              )}
            </div>

            <form onSubmit={handleSubmit} className="mt-auto rounded-3xl border border-slate-800 bg-slate-950/95 p-4 shadow-inner">
              <label htmlFor="question" className="sr-only">
                Ask MediBot a question
              </label>
              <div className="flex gap-3">
                <input
                  id="question"
                  ref={questionInputRef}
                  className="min-h-[56px] flex-1 rounded-3xl border border-slate-800 bg-slate-900 px-4 py-3 text-slate-100 outline-none transition focus:border-medibot-400"
                  placeholder="Ask MediBot a question..."
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  disabled={isSubmitting}
                  autoFocus
                />
                <button
                  type="submit"
                  disabled={isSubmitting || !question.trim()}
                  className="inline-flex items-center justify-center rounded-3xl bg-medibot-500 px-6 py-3 text-sm font-semibold text-slate-950 transition hover:bg-medibot-400 disabled:cursor-not-allowed disabled:bg-slate-700"
                >
                  {isSubmitting ? "Sending..." : "Send"}
                </button>
              </div>
            </form>
          </section>
        </div>
      </div>
    </main>
  );
}
