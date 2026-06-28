import { useRef, useState } from "react";

// Floating Claude analysis chat. Streams the backend SSE response token-by-token.
// `stockId` (when on a stock detail page) is sent so the backend can attach that
// stock's rows as focused context.

interface Msg {
  role: "user" | "assistant";
  content: string;
}

export default function ChatWidget({ stockId }: { stockId?: number }) {
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  const scrollDown = () =>
    requestAnimationFrame(() => {
      scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
    });

  async function send() {
    const q = input.trim();
    if (!q || busy) return;
    setInput("");
    const history = msgs.map((m) => ({ role: m.role, content: m.content }));
    setMsgs((m) => [...m, { role: "user", content: q }, { role: "assistant", content: "" }]);
    setBusy(true);
    scrollDown();

    try {
      const resp = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ message: q, stock_id: stockId, history }),
      });
      const reader = resp.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const events = buf.split("\n\n");
        buf = events.pop() ?? "";
        for (const ev of events) {
          const dataLine = ev.split("\n").find((l) => l.startsWith("data:"));
          if (!dataLine) continue;
          const payload = dataLine.slice(5).trim();
          if (payload === "{}") continue;
          try {
            const { text } = JSON.parse(payload);
            if (text)
              setMsgs((m) => {
                const copy = [...m];
                copy[copy.length - 1] = {
                  role: "assistant",
                  content: copy[copy.length - 1].content + text,
                };
                return copy;
              });
            scrollDown();
          } catch {
            /* ignore partial frames */
          }
        }
      }
    } catch (e) {
      setMsgs((m) => {
        const copy = [...m];
        copy[copy.length - 1] = { role: "assistant", content: `⚠️ ${e}` };
        return copy;
      });
    } finally {
      setBusy(false);
      scrollDown();
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-50 bg-indigo-600 hover:bg-indigo-500 text-white rounded-full shadow-lg px-5 py-3 text-sm font-semibold"
      >
        Ask Claude
      </button>
    );
  }

  return (
    <div className="fixed bottom-5 right-5 z-50 w-[min(92vw,420px)] h-[min(80vh,560px)] card flex flex-col shadow-2xl">
      <div className="flex items-center justify-between px-4 py-3 border-b border-edge">
        <div className="font-semibold text-slate-100">Claude analysis</div>
        <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-slate-200">
          ✕
        </button>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3">
        {msgs.length === 0 && (
          <div className="text-sm text-slate-400">
            Ask about signals, a stock, or the macro picture. Answers are grounded in your
            database{stockId ? " (this stock is in focus)" : ""}.
          </div>
        )}
        {msgs.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={`inline-block max-w-[90%] whitespace-pre-wrap rounded-lg px-3 py-2 text-sm ${
                m.role === "user" ? "bg-indigo-600 text-white" : "bg-edge/70 text-slate-200"
              }`}
            >
              {m.content || (busy && i === msgs.length - 1 ? "…" : "")}
            </div>
          </div>
        ))}
      </div>
      <div className="p-3 border-t border-edge flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about the data…"
          className="flex-1 bg-ink border border-edge rounded-md px-3 py-2 text-sm outline-none focus:border-indigo-500"
        />
        <button
          onClick={send}
          disabled={busy}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white rounded-md px-4 text-sm font-semibold"
        >
          Send
        </button>
      </div>
    </div>
  );
}
