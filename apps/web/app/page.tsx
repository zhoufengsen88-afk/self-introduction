"use client";

import {
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent,
  type TouchEvent,
  type WheelEvent,
} from "react";
import { parseSseFrames, type StreamEvent } from "../lib/sse";

type Citation = {
  chunk_id: string;
  document_id: string;
  document_title: string;
  heading_path: string[];
  score: number | null;
  excerpt: string | null;
};

type DebugInfo = {
  trace_id: string | null;
  route: string;
  intent: string | null;
  project_id: string | null;
  generation_strategy: string;
  retrieved_chunk_ids: string[];
  citation_count: number;
  first_token_ms: number | null;
  total_latency_ms: number | null;
  model_name: string | null;
  refused: boolean;
  refusal_reason: string | null;
};

type ChatRole = "user" | "assistant";

type AssistantStatus = "streaming" | "done" | "error" | "stopped";

type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  citations: Citation[];
  debug?: DebugInfo | null;
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
type IntroState = "checking" | "visible" | "leaving" | "hidden";
type IntroPage = {
  eyebrow: string;
  title: string;
  description: string;
};
type SuggestedQuestion = {
  id: string;
  category: "profile" | "projects" | "responsibility" | "engineering";
  label: string;
  text: string;
};
type FeatureHighlight = {
  title: string;
  description: string;
};

const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
const storageKey = "self-introduction-chat-v1";
const introStorageKey = "self-introduction-intro-seen-v1";
const textareaMinHeight = 96;
const textareaMaxHeight = textareaMinHeight * 2;
const introExitDurationMs = 650;
const scrollFollowThresholdPx = 80;

const featureHighlights: FeatureHighlight[] = [
  {
    title: "知识治理",
    description: "公开 Markdown 资料经过 Front Matter 校验、Chunk 切分和可见性过滤。",
  },
  {
    title: "证据驱动",
    description: "回答必须绑定公开证据；资料不足时明确拒答，而不是补编个人事实。",
  },
  {
    title: "工程链路",
    description: "覆盖 Router、检索、RAG Prompt、SSE 流式输出、评测和 LiteLLMOps 观测。",
  },
];

const questionPool: SuggestedQuestion[] = [
  { id: "profile-name", category: "profile", label: "候选人姓名？", text: "候选人叫什么名字？" },
  { id: "profile-school", category: "profile", label: "毕业院校？", text: "候选人毕业于哪所大学？" },
  { id: "profile-stack", category: "profile", label: "主要技术栈？", text: "候选人的主要技术栈是什么？" },
  { id: "profile-fit", category: "profile", label: "适合岗位？", text: "候选人适合什么方向的岗位？" },
  {
    id: "project-skillvar",
    category: "projects",
    label: "介绍 Skillvar",
    text: "请介绍一下代表项目 Skillvar。",
  },
  {
    id: "project-ontocore",
    category: "projects",
    label: "介绍 OntoCore",
    text: "介绍一下 OntoCore 的背景和核心链路。",
  },
  {
    id: "project-self-rag",
    category: "projects",
    label: "介绍 AI 助手",
    text: "介绍一下这个 Agentic RAG 个人经历助手。",
  },
  {
    id: "project-skillvar-features",
    category: "projects",
    label: "Skillvar 功能？",
    text: "Skillvar 有哪些主要功能模块？",
  },
  {
    id: "role-skillvar",
    category: "responsibility",
    label: "Skillvar 职责？",
    text: "候选人在 Skillvar 中具体负责什么？",
  },
  {
    id: "role-ontocore",
    category: "responsibility",
    label: "OntoCore 职责？",
    text: "候选人在 OntoCore 中明确负责哪些链路？",
  },
  {
    id: "role-ontocore-negative",
    category: "responsibility",
    label: "OntoCore 边界？",
    text: "OntoCore 中哪些部分不是候选人负责的？",
  },
  {
    id: "role-product",
    category: "responsibility",
    label: "负责产品吗？",
    text: "候选人是不是也负责产品规划？",
  },
  {
    id: "eng-skillvar-challenge",
    category: "engineering",
    label: "Skillvar 难点？",
    text: "Skillvar 最大的技术难点是什么？",
  },
  {
    id: "eng-ontocore-graph",
    category: "engineering",
    label: "图谱难点？",
    text: "OntoCore 的 Neo4j 知识图谱难点是什么？",
  },
  {
    id: "eng-self-rag-flow",
    category: "engineering",
    label: "AI 助手数据流？",
    text: "这个个人经历 AI 助手的数据流是怎样的？",
  },
  {
    id: "eng-chroma-fallback",
    category: "engineering",
    label: "检索降级？",
    text: "如果 ChromaDB 不可用，检索链路会怎么处理？",
  },
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
    eyebrow: "AI-Assisted Development",
    title: "基于 AI 编程的工程实践",
    description:
      "该项目以 AI 编程为主要开发方式完成，展示候选人借助 AI 工具完成需求拆解、代码实现、调试测试和工程化落地的能力。项目仅用于介绍公开个人经历，不提供商业服务。",
  },
];

export default function Home() {
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<UiStatus>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [introState, setIntroState] = useState<IntroState>("checking");
  const [introPageIndex, setIntroPageIndex] = useState(0);
  const [suggestedQuestions, setSuggestedQuestions] = useState<SuggestedQuestion[]>(
    questionPool.slice(0, 3),
  );
  const [isNearBottom, setIsNearBottom] = useState(true);
  const abortRef = useRef<AbortController | null>(null);
  const introExitTimerRef = useRef<number | null>(null);
  const hasLoadedStorageRef = useRef(false);
  const shouldAutoScrollRef = useRef(true);
  const userPausedAutoScrollRef = useRef(false);
  const lastTouchYRef = useRef<number | null>(null);
  const messageScrollerRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const bootstrapTimer = window.setTimeout(() => {
      setSuggestedQuestions(pickSuggestedQuestions());
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
    return () => {
      if (introExitTimerRef.current !== null) {
        window.clearTimeout(introExitTimerRef.current);
      }
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
    if (!shouldAutoScrollRef.current) return;

    const frameId = window.requestAnimationFrame(() => {
      if (!shouldAutoScrollRef.current) return;
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
    shouldAutoScrollRef.current = true;
    userPausedAutoScrollRef.current = false;
    setIsNearBottom(true);
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
                debug: data.debug ?? null,
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
    shouldAutoScrollRef.current = true;
    userPausedAutoScrollRef.current = false;
    lastTouchYRef.current = null;
    setIsNearBottom(true);
    setMessages([]);
    setStatus("idle");
    setErrorMessage("");
    setDraft("");
    setSuggestedQuestions(pickSuggestedQuestions());
  }

  function refreshSuggestedQuestions() {
    if (status === "streaming") return;
    setSuggestedQuestions((current) => pickSuggestedQuestions(current.map((question) => question.id)));
  }

  function handleMessagesScroll() {
    const scroller = messageScrollerRef.current;
    if (!scroller) return;

    if (userPausedAutoScrollRef.current) {
      const isAtBottom = isScrollContainerAtBottom(scroller);
      if (isAtBottom) {
        userPausedAutoScrollRef.current = false;
        shouldAutoScrollRef.current = true;
        setIsNearBottom(true);
        return;
      }
      shouldAutoScrollRef.current = false;
      setIsNearBottom(false);
      return;
    }

    const nextIsNearBottom = isScrollContainerNearBottom(scroller);
    shouldAutoScrollRef.current = nextIsNearBottom;
    setIsNearBottom((current) =>
      current === nextIsNearBottom ? current : nextIsNearBottom,
    );
  }

  function pauseAutoScroll() {
    const scroller = messageScrollerRef.current;
    if (scroller && !isScrollContainerScrollable(scroller)) return;
    userPausedAutoScrollRef.current = true;
    shouldAutoScrollRef.current = false;
    setIsNearBottom(false);
  }

  function handleMessagesWheel(event: WheelEvent<HTMLDivElement>) {
    if (event.deltaY < 0) {
      pauseAutoScroll();
    }
  }

  function handleMessagesTouchStart(event: TouchEvent<HTMLDivElement>) {
    lastTouchYRef.current = event.touches[0]?.clientY ?? null;
  }

  function handleMessagesTouchMove(event: TouchEvent<HTMLDivElement>) {
    const nextTouchY = event.touches[0]?.clientY ?? null;
    if (lastTouchYRef.current !== null && nextTouchY !== null && nextTouchY > lastTouchYRef.current) {
      pauseAutoScroll();
    }
    lastTouchYRef.current = nextTouchY;
  }

  function handleMessagesPointerDown(event: PointerEvent<HTMLDivElement>) {
    const bounds = event.currentTarget.getBoundingClientRect();
    const isLikelyScrollbarDrag = event.clientX >= bounds.right - 24;
    if (isLikelyScrollbarDrag) {
      pauseAutoScroll();
    }
  }

  function scrollToBottom(behavior: ScrollBehavior = "smooth") {
    userPausedAutoScrollRef.current = false;
    shouldAutoScrollRef.current = true;
    lastTouchYRef.current = null;
    setIsNearBottom(true);
    window.requestAnimationFrame(() => {
      messagesEndRef.current?.scrollIntoView({
        block: "end",
        behavior,
      });
    });
  }

  function completeIntro() {
    if (introState === "leaving" || introState === "hidden") return;
    try {
      window.sessionStorage.setItem(introStorageKey, "seen");
    } catch {
      // Ignore storage errors; the intro is purely presentational.
    }
    setIntroState("leaving");
    if (introExitTimerRef.current !== null) {
      window.clearTimeout(introExitTimerRef.current);
    }
    introExitTimerRef.current = window.setTimeout(() => {
      setIntroState("hidden");
      introExitTimerRef.current = null;
    }, introExitDurationMs);
  }

  function goToNextIntroPage() {
    if (introPageIndex < introPages.length - 1) {
      setIntroPageIndex((current) => current + 1);
      return;
    }
    completeIntro();
  }

  return (
    <main className="relative h-dvh overflow-hidden bg-[radial-gradient(circle_at_top_left,#dbeafe_0,#f8fafc_28rem),linear-gradient(180deg,#f8fafc,#eef2ff)] text-slate-950">
      <header className="pointer-events-none absolute left-5 top-4 z-10 sm:left-8 sm:top-5">
        <h1 className="text-base font-semibold tracking-tight text-slate-950 sm:text-lg">
          个人经历 AI 助手
        </h1>
      </header>

      <div className="mx-auto flex h-full min-h-0 max-w-5xl flex-col px-5 py-5 sm:px-8 sm:py-6">
        <div className="min-h-0 flex-1">
          <section className="grid h-full min-h-0 grid-rows-[minmax(0,1fr)_auto] overflow-hidden rounded-[1.75rem] border border-slate-950 bg-white/90 shadow-lg shadow-slate-300/50 backdrop-blur">
            <div className="relative h-full min-h-0">
              <div
                ref={messageScrollerRef}
                className="grid h-full min-h-0 content-start gap-4 overflow-y-auto overscroll-contain p-4 sm:p-6"
                onPointerDown={handleMessagesPointerDown}
                onScroll={handleMessagesScroll}
                onTouchMove={handleMessagesTouchMove}
                onTouchStart={handleMessagesTouchStart}
                onWheel={handleMessagesWheel}
              >
                {messages.length === 0 ? <EmptyState /> : null}
                {messages.map((message) => (
                  <MessageBubble key={message.id} message={message} />
                ))}
                <div ref={messagesEndRef} aria-hidden="true" />
              </div>
              {messages.length > 0 && !isNearBottom ? (
                <button
                  aria-label="回到底部"
                  className="absolute bottom-4 right-4 z-10 grid size-11 place-items-center rounded-full border border-white/10 bg-slate-950/90 text-white shadow-xl shadow-slate-900/25 ring-1 ring-slate-700/40 transition hover:bg-slate-900"
                  type="button"
                  onClick={() => scrollToBottom()}
                >
                  <svg
                    aria-hidden="true"
                    className="size-6"
                    fill="none"
                    viewBox="0 0 24 24"
                  >
                    <path
                      d="M12 4v15m0 0 7-7m-7 7-7-7"
                      stroke="currentColor"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth="2"
                    />
                  </svg>
                </button>
              ) : null}
            </div>

            <div className="border-t border-slate-200 bg-white/95 p-4 sm:p-5">
              {errorMessage ? (
                <div className="mb-3 rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {errorMessage}
                </div>
              ) : null}
              <div className="grid gap-3">
                <div className="no-scrollbar flex items-center gap-2 overflow-x-auto">
                  <span className="shrink-0 text-xs font-medium text-slate-400">你可以试试</span>
                  {suggestedQuestions.map((question) => (
                    <button
                      key={question.id}
                      className="shrink-0 rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-600 transition hover:border-slate-400 hover:bg-white hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
                      type="button"
                      disabled={status === "streaming"}
                      title={question.text}
                      onClick={() => void ask(question.text)}
                    >
                      {question.label}
                    </button>
                  ))}
                  <button
                    className="shrink-0 rounded-full px-3 py-1.5 text-xs font-medium text-slate-500 transition hover:bg-slate-100 hover:text-slate-950 disabled:cursor-not-allowed disabled:opacity-60"
                    type="button"
                    disabled={status === "streaming"}
                    onClick={refreshSuggestedQuestions}
                  >
                    换一批
                  </button>
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
      {introState === "visible" || introState === "leaving" ? (
        <IntroOverlay
          currentPage={introPages[introPageIndex]}
          isLeaving={introState === "leaving"}
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
  isLeaving,
  pageIndex,
  pageCount,
  onNext,
  onSkip,
}: {
  currentPage: IntroPage;
  isLeaving: boolean;
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
      className={`fixed inset-0 z-50 grid place-items-center px-6 text-white transition-colors duration-700 ease-out ${
        isLeaving ? "pointer-events-none bg-transparent" : "bg-slate-950"
      }`}
      role="dialog"
    >
      <button
        className={`absolute right-5 top-5 rounded-full px-4 py-2 text-sm text-slate-300 transition-all duration-300 hover:bg-white/10 hover:text-white ${
          isLeaving ? "translate-y-1 opacity-0" : "translate-y-0 opacity-100"
        }`}
        type="button"
        onClick={onSkip}
      >
        跳过介绍
      </button>

      <section
        key={pageIndex}
        className={`grid max-w-2xl place-items-center gap-7 text-center transition-all duration-300 ease-out ${
          isLeaving
            ? "translate-y-2 scale-[0.98] opacity-0"
            : "intro-content-in translate-y-0 scale-100 opacity-100"
        }`}
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
    <div className="grid gap-5 rounded-3xl border border-dashed border-slate-200 bg-slate-50/80 p-5 sm:p-7">
      <div className="grid gap-3 text-center sm:text-left">
        <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-slate-950 text-lg font-semibold text-white sm:mx-0">
          AI
        </div>
        <div className="grid gap-2">
          <h2 className="text-2xl font-semibold tracking-tight text-slate-950">
            从一个可验证的问题开始
          </h2>
          <p className="max-w-3xl text-sm leading-6 text-slate-500">
            这不是通用聊天页，而是一个面试展示型 RAG 应用：系统会从公开知识库检索证据，
            再生成回答，并在答案底部展示引用、路由、意图和 Trace 摘要。
          </p>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        {featureHighlights.map((feature) => (
          <article key={feature.title} className="rounded-2xl border border-white bg-white px-4 py-4 shadow-sm">
            <h3 className="text-sm font-semibold text-slate-950">{feature.title}</h3>
            <p className="mt-2 text-xs leading-5 text-slate-500">{feature.description}</p>
          </article>
        ))}
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
          <RefusalNotice reason={message.refusalReason} />
        ) : null}

        {!isUser && message.citations.length > 0 ? <CitationList citations={message.citations} /> : null}
        {!isUser && message.debug ? <DebugPanel debug={message.debug} /> : null}
      </div>
    </article>
  );
}

function RefusalNotice({ reason }: { reason: string | null | undefined }) {
  return (
    <div className="rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-800">
      <div className="font-semibold">已触发知识库边界</div>
      <p className="mt-1">
        {refusalReasonText(reason)}
        你可以换成询问项目职责、技术难点、技术栈、公开经历或职责边界。
      </p>
    </div>
  );
}

function CitationList({ citations }: { citations: Citation[] }) {
  const [isOpen, setIsOpen] = useState(false);
  const visibleCitations = isOpen ? citations.slice(0, 6) : [];
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
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">公开证据</span>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">{citations.length} 条</span>
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
            还有 {hiddenCount} 条公开证据未展示，当前显示最相关的前 {visibleCitations.length} 条。
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function DebugPanel({ debug }: { debug: DebugInfo }) {
  const [isOpen, setIsOpen] = useState(false);
  const latency = debug.total_latency_ms !== null ? `${debug.total_latency_ms.toFixed(0)} ms` : "未知";
  const firstToken = debug.first_token_ms !== null ? `${debug.first_token_ms.toFixed(0)} ms` : "未记录";

  return (
    <section className="grid gap-2 border-t border-slate-100 pt-3">
      <button
        aria-expanded={isOpen}
        className="flex w-full items-center justify-between gap-3 rounded-2xl px-2 py-1.5 text-left transition hover:bg-slate-50"
        type="button"
        onClick={() => setIsOpen((current) => !current)}
      >
        <span className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">调试链路</span>
          <span className="rounded-full bg-blue-50 px-2 py-0.5 text-xs text-blue-700">
            {routeText(debug.route)}
          </span>
          <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-500">
            {debug.generation_strategy}
          </span>
        </span>
        <span className="text-xs font-medium text-slate-500">{isOpen ? "收起" : "查看"}</span>
      </button>

      {isOpen ? (
        <div className="grid gap-2 rounded-2xl bg-slate-50 px-3 py-3 text-xs leading-5 text-slate-600">
          <DebugRow label="Trace ID" value={debug.trace_id ?? "未记录"} mono />
          <DebugRow label="Route" value={debug.route} />
          <DebugRow label="Intent" value={debug.intent ?? "无"} />
          <DebugRow label="Project" value={debug.project_id ?? "个人资料/未限定项目"} />
          <DebugRow label="生成策略" value={debug.generation_strategy} />
          <DebugRow label="首 Token" value={firstToken} />
          <DebugRow label="总耗时" value={latency} />
          {debug.model_name ? <DebugRow label="模型" value={debug.model_name} /> : null}
          <DebugRow label="命中 Chunk" value={`${debug.retrieved_chunk_ids.length} 个`} />
          {debug.retrieved_chunk_ids.length > 0 ? (
            <div className="mt-1 flex flex-wrap gap-1.5">
              {debug.retrieved_chunk_ids.slice(0, 8).map((chunkId) => (
                <span key={chunkId} className="rounded-full bg-white px-2 py-0.5 font-mono text-[11px] text-slate-500">
                  {chunkId}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function DebugRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="grid grid-cols-[5rem_1fr] gap-3">
      <span className="text-slate-400">{label}</span>
      <span className={mono ? "break-all font-mono text-slate-700" : "break-words text-slate-700"}>{value}</span>
    </div>
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

function isScrollContainerNearBottom(element: HTMLDivElement): boolean {
  const distanceToBottom = distanceToScrollContainerBottom(element);
  return distanceToBottom < scrollFollowThresholdPx;
}

function isScrollContainerAtBottom(element: HTMLDivElement): boolean {
  return distanceToScrollContainerBottom(element) < 8;
}

function isScrollContainerScrollable(element: HTMLDivElement): boolean {
  return element.scrollHeight > element.clientHeight + 1;
}

function distanceToScrollContainerBottom(element: HTMLDivElement): number {
  return element.scrollHeight - element.scrollTop - element.clientHeight;
}

function pickSuggestedQuestions(previousIds: string[] = [], count = 3): SuggestedQuestion[] {
  const previous = new Set(previousIds);
  const categories = shuffleUnique(questionPool.map((question) => question.category));
  const selected: SuggestedQuestion[] = [];

  for (const category of categories) {
    const candidates = shuffle(
      questionPool.filter(
        (question) =>
          question.category === category &&
          !previous.has(question.id) &&
          !selected.some((selectedQuestion) => selectedQuestion.id === question.id),
      ),
    );
    const candidate = candidates[0];
    if (candidate) {
      selected.push(candidate);
    }
    if (selected.length >= count) break;
  }

  const fallback = shuffle(
    questionPool.filter((question) => !selected.some((selectedQuestion) => selectedQuestion.id === question.id)),
  );
  for (const question of fallback) {
    if (selected.length >= count) break;
    selected.push(question);
  }

  return selected;
}

function shuffleUnique<T extends string>(items: T[]): T[] {
  return shuffle(Array.from(new Set(items)));
}

function shuffle<T>(items: T[]): T[] {
  return [...items].sort(() => Math.random() - 0.5);
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
  debug?: DebugInfo | null;
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
  if (reason === "restricted_content") return "这个问题涉及隐藏资料、系统规则或非公开内容，系统不能回答。";
  if (reason === "insufficient_evidence") return "公开知识库中没有足够证据确认这一点，系统不会凭空补充。";
  if (reason === "llm_provider_error") return "大模型调用暂时失败，可以稍后重试或先切换到确定性回答器验证检索链路。";
  return "当前问题不适合基于公开知识库回答。";
}

function routeText(route: string): string {
  if (route === "knowledge_rag") return "知识库 RAG";
  if (route === "normal_chat") return "普通引导";
  if (route === "out_of_scope") return "范围外";
  if (route === "restricted") return "安全拒答";
  return route;
}
