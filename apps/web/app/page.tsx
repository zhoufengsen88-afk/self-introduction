"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { parseSseFrames, type StreamEvent } from "../lib/sse";

type Citation = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  heading_path: string[];
  score: number | null;
  excerpt: string | null;
};

type ChatRole = "user" | "assistant";

type AssistantStatus = "streaming" | "done" | "error" | "stopped";

type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  citations: Citation[];
  status?: AssistantStatus;
  refused?: boolean;
  refusalReason?: string | null;
  createdAt: string;
};

type ApiHistoryMessage = {
  role: ChatRole;
  content: string;
};

type UiStatus = "idle" | "streaming" | "done" | "error" | "stopped";
type IntroState = "checking" | "visible" | "hidden";
type IntroPage = {
  eyebrow: string;
  title: string;
  description: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const storageKey = "self-introduction-chat-v1";
const introStorageKey = "self-introduction-intro-seen-v1";
const textareaMinHeight = 96;
const textareaMaxHeight = textareaMinHeight * 2;

const recommendedQuestions = [
  "请介绍一下你的代表项目 Skillvar。",
  "你在 Skillvar 中具体负责什么？",
  "Skillvar 最大的技术难点是什么？",
  "这个平台怎么把能力交给自动化工具或命令行使用？",
  "如果 ChromaDB 不可用，检索链路会怎么处理？",
  "候选人是不是也负责产品规划？",
];

const introPages: IntroPage[] = [
  {
    eyebrow: "Personal Knowledge Assistant",
    title: "个人经历 AI 助手",
    description:
      "这是一个基于公开个人经历知识库构建的 AI 问答助手，用来帮助你快速了解我的项目经历、技术能力和职责边界。",
  },
  {
    eyebrow: "Ask About Experience",
    title: "你可以这样了解我",
    description:
      "你可以询问我的代表项目、实习经历、技术栈、个人贡献、技术难点、项目成果，以及我在团队中的职责边界。",
  },
  {
    eyebrow: "Evidence-based Answers",
    title: "回答基于公开证据",
    description:
      "系统会先从公开知识库中检索相关资料，再交给大模型生成回答；如果证据不足，会明确说明无法确认，而不是编造答案。",
  },
];

export default function Home() {
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<UiStatus>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [introState, setIntroState] = useState<IntroState>("checking");
  const [introPageIndex, setIntroPageIndex] = useState(0);
  const abortRef = useRef<AbortController | null>(null);
  const hasLoadedStorageRef = useRef(false);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const bootstrapTimer = window.setTimeout(() => {
      try {
        if (window.sessionStorage.getItem(introStorageKey) === "seen") {
          setIntroState("hidden");
          return;
        }
      } catch {
        // If browser storage is unavailable, still show the lightweight intro once for this render.
      }

      setIntroState("visible");
    }, 0);

    return () => {
      window.clearTimeout(bootstrapTimer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    queueMicrotask(() => {
      try {
        const saved = window.sessionStorage.getItem(storageKey);
        if (saved) {
          const parsed: unknown = JSON.parse(saved);
          if (!cancelled && isStoredMessages(parsed)) {
            setMessages(parsed);
            if (parsed.length > 0) {
              setStatus("done");
            }
          }
        }
      } catch {
        window.sessionStorage.removeItem(storageKey);
      } finally {
        hasLoadedStorageRef.current = true;
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!hasLoadedStorageRef.current) return;
    window.sessionStorage.setItem(storageKey, JSON.stringify(messages));
  }, [messages]);

  useLayoutEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = "auto";
    const nextHeight = Math.min(
      Math.max(textarea.scrollHeight, textareaMinHeight),
      textareaMaxHeight,
    );
    textarea.style.height = `${nextHeight}px`;
    textarea.style.overflowY = textarea.scrollHeight > textareaMaxHeight ? "auto" : "hidden";
  }, [draft]);

  useEffect(() => {
    if (introState !== "hidden") return;

    const frameId = window.requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({
        block: "end",
        behavior: status === "streaming" ? "auto" : "smooth",
      });
    });

    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [introState, messages, status]);

  const canSubmit = useMemo(
    () => draft.trim().length > 0 && status !== "streaming",
    [draft, status],
  );

  async function ask(questionInput = draft) {
    const question = questionInput.trim();
    if (!question || status === "streaming") return;

    const controller = new AbortController();
    abortRef.current = controller;
    setStatus("streaming");
    setErrorMessage("");
    setDraft("");

    const history = toApiHistory(messages).slice(-8);
    const userMessage = createMessage("user", question);
    const assistantId = createId();
    const assistantMessage: ChatMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      citations: [],
      status: "streaming",
      createdAt: new Date().toISOString(),
    };

    setMessages((current) => [...current, userMessage, assistantMessage]);

    try {
      const response = await fetch(`${apiBaseUrl}/api/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: question, history }),
        signal: controller.signal,
      });
      if (!response.ok || !response.body) {
        throw new Error(`request failed: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parsed = parseSseFrames(buffer);
        buffer = parsed.rest;
        for (const event of parsed.events) {
          handleStreamEvent(event, assistantId);
        }
      }
    } catch (error) {
      if (controller.signal.aborted) {
        markAssistantStopped(assistantId);
        setStatus("stopped");
        return;
      }
      const message = error instanceof Error ? error.message : "unknown error";
      setErrorMessage(`请求失败：${message}`);
      markAssistantError(assistantId);
      setStatus("error");
    } finally {
      abortRef.current = null;
    }
  }

  function handleStreamEvent(event: StreamEvent, assistantId: string) {
    const data = event.data;
    if (event.event === "delta" && hasContent(data)) {
      appendAssistantContent(assistantId, data.content);
      return;
    }

    if (event.event === "done" && hasDoneData(data)) {
      setMessages((current) =>
        current.map((message) =>
          message.id === assistantId
            ? {
                ...message,
                citations: data.citations,
                refused: data.refused,
                refusalReason: data.refusal_reason,
                status: "done",
              }
            : message,
        ),
      );
      setStatus("done");
      return;
    }

    if (event.event === "error") {
      setErrorMessage(`请求失败：${hasErrorData(data) ? data.message : "流式响应失败"}`);
      markAssistantError(assistantId);
      setStatus("error");
    }
  }

  function appendAssistantContent(assistantId: string, content: string) {
    setMessages((current) =>
      current.map((message) =>
        message.id === assistantId ? { ...message, content: message.content + content } : message,
      ),
    );
  }

  function markAssistantStopped(assistantId: string) {
    setMessages((current) =>
      current.map((message) =>
        message.id === assistantId
          ? {
              ...message,
              content: message.content || "已停止生成。你可以换一种问法继续追问。",
              status: "stopped",
            }
          : message,
      ),
    );
  }

  function markAssistantError(assistantId: string) {
    setMessages((current) =>
      current.map((message) =>
        message.id === assistantId
          ? {
              ...message,
              content: "这次请求没有成功。请确认本地 API 已启动后重试。",
              status: "error",
            }
          : message,
      ),
    );
  }

  function stopStreaming() {
    abortRef.current?.abort();
  }

  function clearChat() {
    abortRef.current?.abort();
    setMessages([]);
    setStatus("idle");
    setErrorMessage("");
    setDraft("");
  }

  function completeIntro() {
    try {
      window.sessionStorage.setItem(introStorageKey, "seen");
    } catch {
      // Ignore storage errors; the intro is purely presentational.
    }
    setIntroState("hidden");
  }

  function goToNextIntroPage() {
    if (introPageIndex < introPages.length - 1) {
      setIntroPageIndex((current) => current + 1);
      return;
    }
    completeIntro();
  }

  return (
    <main className="h-dvh overflow-hidden bg-[radial-gradient(circle_at_top_left,#dbeafe_0,#f8fafc_28rem),linear-gradient(180deg,#f8fafc,#eef2ff)] text-slate-950">
      <div className="mx-auto flex h-full min-h-0 max-w-5xl flex-col gap-4 px-5 py-5 sm:px-8">
        <header className="shrink-0">
          <h1 className="text-2xl font-semibold tracking-tight text-slate-950 sm:text-3xl">
            个人经历 AI 助手
          </h1>
        </header>

        <div className="min-h-0 flex-1">
          <section className="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] overflow-hidden rounded-[1.75rem] border border-white/70 bg-white/85 shadow-sm shadow-slate-200/80 backdrop-blur">
            <div className="grid min-h-0 content-start gap-4 overflow-y-auto overscroll-contain p-4 sm:p-6">
              {messages.length === 0 ? <EmptyState /> : null}
              {messages.map((message) => (
                <MessageBubble key={message.id} message={message} />
              ))}
              <div ref={messagesEndRef} aria-hidden="true" />
            </div>

            <div className="border-t border-slate-200 bg-white/95 p-4 sm:p-5">
              {errorMessage ? (
                <div className="mb-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {errorMessage}
                </div>
              ) : null}
              <div className="grid gap-3">
                <div className="flex gap-2 overflow-x-auto pb-1">
                  {recommendedQuestions.map((question) => (
                    <button
                      key={question}
                      className="shrink-0 rounded-full border border-slate-200 bg-white px-3 py-1.5 text-xs text-slate-600 transition hover:border-slate-400 hover:bg-slate-50 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
                      type="button"
                      disabled={status === "streaming"}
                      onClick={() => void ask(question)}
                    >
                      {question}
                    </button>
                  ))}
                </div>
                <label className="sr-only" htmlFor="question">
                  输入问题
                </label>
                <textarea
                  ref={textareaRef}
                  id="question"
                  className="max-h-48 min-h-24 resize-none rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm leading-6 text-slate-900 outline-none transition-[height,border-color,background-color] placeholder:text-slate-400 focus:border-slate-400 focus:bg-white"
                  placeholder="例如：你在 Skillvar 里具体负责什么？"
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.nativeEvent.isComposing) {
                      return;
                    }
                    if (event.key === "Enter" && !event.shiftKey) {
                      event.preventDefault();
                      void ask();
                    }
                  }}
                />
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <p className="text-xs text-slate-500">按 Enter 发送，Shift + Enter 换行</p>
                  <div className="flex items-center gap-2">
                    <button
                      className="rounded-full px-4 py-2 text-sm font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
                      type="button"
                      onClick={clearChat}
                    >
                      清空对话
                    </button>
                    {status === "streaming" ? (
                      <button
                        className="rounded-full bg-white px-5 py-2 text-sm font-semibold text-slate-900 ring-1 ring-slate-300 transition hover:bg-slate-50"
                        type="button"
                        onClick={stopStreaming}
                      >
                        停止生成
                      </button>
                    ) : null}
                    <button
                      className="rounded-full bg-slate-950 px-5 py-2 text-sm font-semibold text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:bg-slate-300"
                      disabled={!canSubmit}
                      type="button"
                      onClick={() => void ask()}
                    >
                      {status === "streaming" ? "生成中..." : "发送"}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </div>
      </div>
      {introState === "visible" ? (
        <IntroOverlay
          currentPage={introPages[introPageIndex]}
          pageIndex={introPageIndex}
          pageCount={introPages.length}
          onNext={goToNextIntroPage}
          onSkip={completeIntro}
        />
      ) : null}
    </main>
  );
}

function IntroOverlay({
  currentPage,
  pageIndex,
  pageCount,
  onNext,
  onSkip,
}: {
  currentPage: IntroPage;
  pageIndex: number;
  pageCount: number;
  onNext: () => void;
  onSkip: () => void;
}) {
  const isLastPage = pageIndex === pageCount - 1;

  return (
    <div
      aria-label="个人经历 AI 助手介绍"
      aria-modal="true"
      className="fixed inset-0 z-50 grid place-items-center bg-slate-950 px-6 text-white"
      role="dialog"
    >
      <button
        className="absolute right-5 top-5 rounded-full px-4 py-2 text-sm text-slate-300 transition hover:bg-white/10 hover:text-white"
        type="button"
        onClick={onSkip}
      >
        跳过介绍
      </button>

      <section
        key={pageIndex}
        className="intro-content-in grid max-w-2xl place-items-center gap-7 text-center"
      >
        <div className="intro-mark-in grid size-14 place-items-center rounded-2xl bg-white text-lg font-semibold text-slate-950 shadow-2xl shadow-blue-500/20">
          AI
        </div>
        <div className="grid gap-3">
          <p className="text-sm uppercase tracking-[0.28em] text-slate-400">
            {currentPage.eyebrow}
          </p>
          <h2 className="text-4xl font-semibold tracking-tight sm:text-6xl">
            {currentPage.title}
          </h2>
          <p className="mx-auto max-w-xl text-base leading-8 text-slate-300 sm:text-lg">
            {currentPage.description}
          </p>
        </div>

        <div className="grid gap-5">
          <div className="flex items-center justify-center gap-2" aria-label={`第 ${pageIndex + 1} 页，共 ${pageCount} 页`}>
            {Array.from({ length: pageCount }, (_, index) => (
              <span
                key={index}
                className={`h-1.5 rounded-full transition-all ${
                  index === pageIndex ? "w-8 bg-white" : "w-1.5 bg-white/30"
                }`}
              />
            ))}
          </div>
          <button
            className="rounded-full bg-white px-6 py-3 text-sm font-semibold text-slate-950 shadow-2xl shadow-blue-500/20 transition hover:bg-slate-100"
            type="button"
            onClick={onNext}
          >
            {isLastPage ? "进入 AI 问答" : "下一页"}
          </button>
        </div>
      </section>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="grid min-h-80 place-items-center rounded-3xl border border-dashed border-slate-200 bg-slate-50/80 p-8 text-center">
      <div className="grid max-w-md gap-3">
        <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-slate-950 text-lg font-semibold text-white">
          AI
        </div>
        <h2 className="text-xl font-semibold text-slate-950">从一个具体问题开始</h2>
        <p className="text-sm leading-6 text-slate-500">
          比如“你在 Skillvar 中具体负责什么？”或者“最大技术难点是什么？”。系统会边生成边返回答案，并在结束后展示引用证据。
        </p>
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <article className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`grid max-w-[min(44rem,100%)] gap-3 rounded-3xl px-4 py-3 text-sm leading-7 shadow-sm ${
          isUser
            ? "rounded-br-md bg-slate-950 text-white"
            : "rounded-bl-md border border-slate-200 bg-white text-slate-700"
        }`}
      >
        <div className="whitespace-pre-wrap">{message.content || "正在组织公开证据..."}</div>

        {!isUser && message.refused ? (
          <div className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
            已拒答：{refusalReasonText(message.refusalReason)}
          </div>
        ) : null}

        {!isUser && message.citations.length > 0 ? <CitationList citations={message.citations} /> : null}
      </div>
    </article>
  );
}

function CitationList({ citations }: { citations: Citation[] }) {
  const [isOpen, setIsOpen] = useState(false);
  const visibleCitations = citations.slice(0, 6);
  const hiddenCount = citations.length - visibleCitations.length;

  return (
    <section className="grid gap-2 border-t border-slate-100 pt-3">
      <button
        aria-expanded={isOpen}
        className="flex w-full items-center justify-between gap-3 rounded-2xl px-2 py-1.5 text-left transition hover:bg-slate-50"
        type="button"
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">引用证据</span>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{citations.length} chunks</span>
        </span>
        <span className="text-xs font-medium text-slate-500">{isOpen ? "收起" : "展开"}</span>
      </button>

      {isOpen ? (
        <div className="grid gap-2">
          {visibleCitations.map((citation) => (
            <article key={citation.chunk_id} className="rounded-2xl bg-slate-50 px-3 py-3 text-xs leading-5 text-slate-600">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="font-semibold text-slate-800">{citation.document_title}</span>
                {citation.score !== null ? <span className="text-slate-400">score {citation.score.toFixed(2)}</span> : null}
              </div>
              {citation.heading_path.length > 0 ? (
                <div className="mt-1 text-slate-500">{citation.heading_path.join(" / ")}</div>
              ) : null}
              {citation.excerpt ? <p className="mt-2 text-slate-500">{citation.excerpt}</p> : null}
            </article>
          ))}
          {hiddenCount > 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-200 px-3 py-2 text-xs text-slate-400">
              还有 {hiddenCount} 条引用证据未展示，当前仅显示最相关的前 {visibleCitations.length} 条。
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function createMessage(role: ChatRole, content: string): ChatMessage {
  return {
    id: createId(),
    role,
    content,
    citations: [],
    createdAt: new Date().toISOString(),
  };
}

function createId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function toApiHistory(messages: ChatMessage[]): ApiHistoryMessage[] {
  return messages
    .filter((message) => {
      if (!message.content.trim()) return false;
      if (message.role === "assistant") {
        return message.status === "done";
      }
      return true;
    })
    .map((message) => ({ role: message.role, content: message.content }));
}

function hasContent(value: unknown): value is { content: string } {
  return typeof value === "object" && value !== null && "content" in value && typeof value.content === "string";
}

function hasDoneData(value: unknown): value is {
  finish_reason: string;
  refused: boolean;
  refusal_reason: string | null;
  citations: Citation[];
} {
  return (
    typeof value === "object" &&
    value !== null &&
    "citations" in value &&
    Array.isArray(value.citations) &&
    "refused" in value &&
    typeof value.refused === "boolean"
  );
}

function hasErrorData(value: unknown): value is { message: string; code?: string } {
  return typeof value === "object" && value !== null && "message" in value && typeof value.message === "string";
}

function isStoredMessages(value: unknown): value is ChatMessage[] {
  return (
    Array.isArray(value) &&
    value.every(
      (item) =>
        typeof item === "object" &&
        item !== null &&
        "id" in item &&
        "role" in item &&
        "content" in item &&
        "citations" in item &&
        "createdAt" in item &&
        (item.role === "user" || item.role === "assistant") &&
        typeof item.content === "string" &&
        Array.isArray(item.citations),
    )
  );
}

function refusalReasonText(reason: string | null | undefined): string {
  if (reason === "restricted_content") return "涉及隐藏资料、系统规则或非公开内容";
  if (reason === "insufficient_evidence") return "公开知识库证据不足";
  return "当前问题不适合基于公开知识库回答";
}
