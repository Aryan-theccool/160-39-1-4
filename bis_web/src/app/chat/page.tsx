"use client";

import { Bot, Sparkles } from "lucide-react";
import * as React from "react";

import { ChatPanel } from "@/components/chat-panel";
import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";

export default function ChatPage() {
  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <PageHeader
        icon={Bot}
        title="BIS Standards AI Assistant"
        description="Interact conversationally with the Indian Standards knowledge base. Every answer cites specific IS codes and clauses, verifies citations against retrieved text, and warns against superseded editions."
      >
        <Badge variant="outline" className="gap-1 border-tricolor-saffron/40 bg-accent text-xs">
          <Sparkles className="h-3 w-3 text-tricolor-saffron" />
          RAG Verified
        </Badge>
      </PageHeader>

      <ChatPanel />
    </div>
  );
}
