"use client";

import {
  AlertCircle,
  AlertTriangle,
  ArrowUp,
  BookOpen,
  Bot,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  FileText,
  Loader2,
  MessageSquare,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  User,
} from "lucide-react";
import Link from "next/link";
import * as React from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Textarea } from "@/components/ui/textarea";
import {
  downloadReportDocx,
  downloadReportPdf,
  recommend,
  type Citation,
  type RecommendResponse,
  type StructuredReport,
} from "@/lib/api";
import { formatMs } from "@/lib/format";
import { cn } from "@/lib/utils";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  question?: string;
  citations?: Citation[];
  unsupported_citations?: string[];
  warnings?: string[];
  grounded?: boolean;
  mode?: string;
  generator?: string;
  report?: StructuredReport | null;
  took_ms?: number;
  timestamp: Date;
  error?: boolean;
}

const SUGGESTIONS = [
  "What standard applies to drinking water quality?",
  "Which BIS standards apply to LED street lights?",
  "Is IS 456 current or superseded?",
  "Find standards related to electrical safety in domestic appliances.",
];

export function ChatPanel() {
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [copiedId, setCopiedId] = React.useState<string | null>(null);
  const [exportingKey, setExportingKey] = React.useState<string | null>(null);
  const [exportError, setExportError] = React.useState<string | null>(null);

  const messagesEndRef = React.useRef<HTMLDivElement>(null);
  const textareaRef = React.useRef<HTMLTextAreaElement>(null);

  const scrollToBottom = React.useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  React.useEffect(() => {
    scrollToBottom();
  }, [messages, loading, scrollToBottom]);

  async function handleExport(msg: ChatMessage, format: "docx" | "pdf") {
    const key = `${msg.id}-${format}`;
    setExportingKey(key);
    setExportError(null);
    try {
      const payload: Partial<RecommendResponse> = {
        question: msg.question || msg.content.slice(0, 120),
        answer: msg.content,
        mode: msg.mode as "llm" | "extractive",
        generator: msg.generator || "",
        grounded: msg.grounded ?? true,
        report: msg.report ?? undefined,
        citations: msg.citations || [],
        warnings: msg.warnings || [],
        unsupported_citations: msg.unsupported_citations || [],
      };
      if (format === "docx") {
        await downloadReportDocx(payload);
      } else {
        await downloadReportPdf(payload);
      }
    } catch (err: unknown) {
      const errorMsg = err instanceof Error ? err.message : "Failed to generate document.";
      setExportError(errorMsg);
      setTimeout(() => setExportError(null), 5000);
    } finally {
      setExportingKey(null);
    }
  }

  async function handleSend(textToSend?: string) {
    const query = (textToSend ?? input).trim();
    if (!query || loading) return;

    const userMessageId = `user-${Date.now()}`;
    const userMessage: ChatMessage = {
      id: userMessageId,
      role: "user",
      content: query,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const response: RecommendResponse = await recommend({
        query,
        top_k: 6,
        include_passages: false,
      });

      const assistantMessage: ChatMessage = {
        id: `asst-${Date.now()}`,
        role: "assistant",
        content: response.answer,
        question: query,
        citations: response.citations ?? [],
        unsupported_citations: response.unsupported_citations ?? [],
        warnings: response.warnings ?? [],
        grounded: response.grounded,
        mode: response.mode,
        generator: response.generator,
        report: response.report,
        took_ms: response.took_ms,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: unknown) {
      const errorMessage =
        err instanceof Error
          ? err.message
          : "An unexpected error occurred while communicating with the BIS Standards engine.";

      const assistantError: ChatMessage = {
        id: `err-${Date.now()}`,
        role: "assistant",
        content: errorMessage,
        error: true,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantError]);
    } finally {
      setLoading(false);
      setTimeout(() => textareaRef.current?.focus(), 50);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  function copyToClipboard(id: string, text: string) {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }

  function resetChat() {
    setMessages([]);
    setInput("");
    textareaRef.current?.focus();
  }

  return (
    <div className="flex h-[calc(100vh-12rem)] min-h-[550px] flex-col rounded-xl border bg-background shadow-sm">
      {/* Top action bar */}
      <div className="flex items-center justify-between border-b px-4 py-2.5">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-gradient-to-br from-tricolor-saffron to-tricolor-green text-white shadow-xs">
            <Bot className="h-4 w-4" />
          </span>
          <div className="flex flex-col leading-tight">
            <span className="text-xs font-semibold">Grounded BIS RAG Session</span>
            <span className="text-[10px] text-muted-foreground">
              {messages.length > 0 ? `${messages.length} message(s)` : "Ready for query"}
            </span>
          </div>
        </div>

        {messages.length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            onClick={resetChat}
            disabled={loading}
            className="h-8 gap-1 text-xs text-muted-foreground hover:text-foreground"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            Clear chat
          </Button>
        )}
      </div>

      {/* Message list / empty state */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-6">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-gradient-to-br from-tricolor-saffron/15 to-tricolor-green/15 text-tricolor-saffron shadow-sm">
              <Sparkles className="h-7 w-7" />
            </div>

            <h3 className="mt-4 text-xl font-semibold tracking-tight">
              Ask about Indian Standards
            </h3>
            <p className="mt-2 max-w-md text-sm text-muted-foreground">
              Conversational technical assistant grounded directly on the Bureau of Indian
              Standards corpus with automatic citation verification.
            </p>

            <div className="mt-8 grid w-full max-w-xl gap-2 sm:grid-cols-2">
              {SUGGESTIONS.map((suggestion) => (
                <button
                  key={suggestion}
                  onClick={() => handleSend(suggestion)}
                  disabled={loading}
                  className="group flex items-start gap-2.5 rounded-lg border bg-card p-3 text-left text-xs transition-all hover:border-tricolor-saffron/50 hover:bg-accent/50 hover:shadow-xs"
                >
                  <MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 text-tricolor-saffron transition-transform group-hover:scale-110" />
                  <span className="leading-snug text-foreground/90">{suggestion}</span>
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={cn(
                  "flex gap-3",
                  msg.role === "user" ? "justify-end" : "justify-start"
                )}
              >
                {/* Assistant avatar */}
                {msg.role === "assistant" && (
                  <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-tricolor-saffron to-tricolor-green text-white shadow-xs">
                    <Bot className="h-4 w-4" />
                  </span>
                )}

                {/* Message Content Bubble */}
                <div
                  className={cn(
                    "max-w-3xl space-y-3 rounded-2xl p-4 text-sm leading-relaxed",
                    msg.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : msg.error
                      ? "border border-destructive/30 bg-destructive/10 text-destructive"
                      : "border bg-card text-card-foreground shadow-xs"
                  )}
                >
                  {/* Assistant metadata header */}
                  {msg.role === "assistant" && !msg.error && (
                    <div className="flex flex-wrap items-center justify-between gap-2 pb-1 text-xs">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <Badge variant={msg.mode === "llm" ? "default" : "outline"} className="text-[11px]">
                          {msg.mode === "llm" ? (
                            <span className="flex items-center gap-1">
                              <Sparkles className="h-3 w-3 text-tricolor-saffron" />
                              LLM Generated
                            </span>
                          ) : (
                            <span className="flex items-center gap-1">
                              <BookOpen className="h-3 w-3 text-tricolor-saffron" />
                              Extracted
                            </span>
                          )}
                        </Badge>

                        {msg.grounded ? (
                          <Badge variant="success" className="gap-1 text-[11px]">
                            <CheckCircle2 className="h-3 w-3" />
                            Verified against indexed evidence
                          </Badge>
                        ) : (
                          <Badge variant="warning" className="gap-1 text-[11px]">
                            <AlertTriangle className="h-3 w-3" />
                            Unverified standard reference
                          </Badge>
                        )}
                      </div>

                      <div className="flex items-center gap-2">
                        {typeof msg.took_ms === "number" && (
                          <span className="text-[11px] text-muted-foreground">
                            {formatMs(msg.took_ms)}
                          </span>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 text-muted-foreground hover:text-foreground"
                          onClick={() => copyToClipboard(msg.id, msg.content)}
                          title="Copy answer"
                        >
                          {copiedId === msg.id ? (
                            <Check className="h-3.5 w-3.5 text-emerald-600" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </Button>
                      </div>
                    </div>
                  )}

                  {/* Main prose */}
                  <div className="whitespace-pre-line leading-relaxed">
                    {msg.content}
                  </div>

                  {/* Error Retry Affordance */}
                  {msg.error && (
                    <div className="flex items-center gap-2 pt-2">
                      <AlertCircle className="h-4 w-4 shrink-0" />
                      <span className="text-xs">
                        Check that the backend server is running on port 8000.
                      </span>
                    </div>
                  )}

                  {/* Unsupported citations warning */}
                  {msg.unsupported_citations && msg.unsupported_citations.length > 0 && (
                    <div className="rounded-lg border border-amber-300/80 bg-amber-500/15 p-3 text-xs text-amber-900 dark:border-amber-700/60 dark:bg-amber-950/40 dark:text-amber-200">
                      <p className="flex items-center gap-1.5 font-semibold">
                        <AlertTriangle className="h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                        Unverified Standard Reference
                      </p>
                      <div className="mt-1 space-y-1 text-xs leading-relaxed">
                        {msg.unsupported_citations.map((desig) => (
                          <p key={desig}>
                            The model mentioned <strong>{desig}</strong>, but this standard is not currently available in the indexed BIS knowledge base. Therefore, a verified citation cannot be provided.
                          </p>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Supersession warnings */}
                  {msg.warnings && msg.warnings.length > 0 && (
                    <div className="rounded-lg border border-amber-300/70 bg-amber-500/10 p-2.5 text-xs text-amber-900 dark:text-amber-200">
                      <p className="flex items-center gap-1.5 font-medium">
                        <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
                        Supersession & compliance warnings:
                      </p>
                      <ul className="mt-1 list-disc space-y-0.5 pl-4">
                        {msg.warnings.map((w, idx) => (
                          <li key={idx}>{w}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Citations section */}
                  {msg.citations && msg.citations.length > 0 && (
                    <>
                      <Separator className="my-2" />
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between">
                          <p className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1">
                            <ShieldCheck className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
                            Verified Citations ({msg.citations.length})
                          </p>
                          <span className="text-[10px] text-muted-foreground">Indexed evidence</span>
                        </div>
                        <div className="grid gap-2 sm:grid-cols-2">
                          {msg.citations.map((c, i) => (
                            <div
                              key={`${c.designation}-${i}`}
                              className="flex flex-col justify-between rounded-lg border bg-muted/40 p-2.5 text-xs"
                            >
                              <div className="flex items-start justify-between gap-1.5">
                                <Link
                                  href={`/standards?q=${encodeURIComponent(c.designation)}`}
                                  className="font-mono font-semibold text-primary hover:text-tricolor-saffron hover:underline"
                                >
                                  {c.designation}
                                </Link>
                                {c.is_current ? (
                                  <Badge variant="success" className="h-4 px-1.5 text-[10px]">
                                    Current
                                  </Badge>
                                ) : (
                                  <Badge variant="warning" className="h-4 px-1.5 text-[10px]">
                                    Superseded
                                  </Badge>
                                )}
                              </div>
                              <p className="mt-1 line-clamp-2 text-[11px] leading-snug text-muted-foreground">
                                {c.title}
                              </p>
                              {c.superseded_by && (
                                <p className="mt-1 text-[10px] font-medium text-amber-700 dark:text-amber-400">
                                  Replaced by {c.superseded_by}
                                </p>
                              )}
                              {c.archive_url && (
                                <a
                                  href={c.archive_url}
                                  target="_blank"
                                  rel="noreferrer noopener"
                                  className="mt-1.5 inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground hover:underline"
                                >
                                  Public standard archive <ExternalLink className="h-2.5 w-2.5" />
                                </a>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    </>
                  )}

                  {/* Download Procurement Report Actions */}
                  {msg.role === "assistant" && !msg.error && (
                    <>
                      <Separator className="my-2" />
                      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
                        <span className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
                          <FileText className="h-3 w-3 text-tricolor-navy" />
                          Download Procurement Report:
                        </span>
                        <div className="flex flex-wrap items-center gap-1.5">
                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 px-2.5 text-xs font-medium gap-1 hover:border-blue-500 hover:text-blue-600 dark:hover:text-blue-400"
                            disabled={exportingKey === `${msg.id}-docx` || exportingKey === `${msg.id}-pdf`}
                            onClick={() => handleExport(msg, "docx")}
                            title="Download formatted Word document"
                          >
                            {exportingKey === `${msg.id}-docx` ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-600" />
                            ) : (
                              <FileText className="h-3.5 w-3.5 text-blue-600" />
                            )}
                            <span>DOCX</span>
                          </Button>

                          <Button
                            variant="outline"
                            size="sm"
                            className="h-7 px-2.5 text-xs font-medium gap-1 hover:border-red-500 hover:text-red-600 dark:hover:text-red-400"
                            disabled={exportingKey === `${msg.id}-docx` || exportingKey === `${msg.id}-pdf`}
                            onClick={() => handleExport(msg, "pdf")}
                            title="Download formatted PDF document"
                          >
                            {exportingKey === `${msg.id}-pdf` ? (
                              <Loader2 className="h-3.5 w-3.5 animate-spin text-red-600" />
                            ) : (
                              <FileText className="h-3.5 w-3.5 text-red-600" />
                            )}
                            <span>PDF</span>
                          </Button>
                        </div>
                      </div>

                      {exportError && (
                        <div className="mt-2 rounded-md border border-destructive/30 bg-destructive/10 p-2 text-xs text-destructive">
                          {exportError}
                        </div>
                      )}
                    </>
                  )}
                </div>

                {/* User avatar */}
                {msg.role === "user" && (
                  <span className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground shadow-xs">
                    <User className="h-4 w-4" />
                  </span>
                )}
              </div>
            ))}

            {/* Typing / Loading state */}
            {loading && (
              <div className="flex justify-start gap-3">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-tricolor-saffron to-tricolor-green text-white shadow-xs">
                  <Bot className="h-4 w-4" />
                </span>
                <div className="flex items-center gap-2 rounded-2xl border bg-card p-4 text-xs text-muted-foreground shadow-xs">
                  <div className="flex gap-1">
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-tricolor-saffron [animation-delay:-0.3s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-tricolor-navy [animation-delay:-0.15s]" />
                    <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-tricolor-green" />
                  </div>
                  <span>Retrieving Indian Standards and verifying citations…</span>
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>
        )}
      </div>

      {/* Input container */}
      <div className="border-t bg-muted/20 p-3 sm:p-4">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="relative flex items-end gap-2"
        >
          <div className="relative flex-1">
            <Textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a technical question about Indian Standards (e.g. 'What are the permissible limits in IS 10500?')..."
              rows={2}
              disabled={loading}
              className="min-h-[56px] resize-none pr-12 text-xs sm:text-sm"
            />
          </div>

          <Button
            type="submit"
            size="icon"
            disabled={!input.trim() || loading}
            className="h-10 w-10 shrink-0 bg-tricolor-saffron text-white shadow-xs hover:bg-tricolor-saffron/90"
            title="Send message (Enter)"
          >
            <ArrowUp className="h-5 w-5" />
          </Button>
        </form>

        <p className="mt-1.5 text-center text-[10px] text-muted-foreground">
          Press <kbd className="rounded border bg-muted px-1 py-0.5 font-mono text-[9px]">Enter</kbd> to send, <kbd className="rounded border bg-muted px-1 py-0.5 font-mono text-[9px]">Shift+Enter</kbd> for newline. Answers are grounded in the BIS corpus.
        </p>
      </div>
    </div>
  );
}
