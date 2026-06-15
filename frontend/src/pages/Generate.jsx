import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import Layout from "@/components/Layout";
import { API, api } from "@/lib/api";
import { UploadSimple, Code, Cube, Lightning, Warning, GlobeHemisphereWest, ArrowsClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";

const REGIONS = [
  "ap-southeast-2", "ap-southeast-1", "ap-south-1", "ap-northeast-1", "ap-northeast-2",
  "us-east-1", "us-east-2", "us-west-1", "us-west-2",
  "ca-central-1",
  "eu-west-1", "eu-west-2", "eu-west-3", "eu-central-1", "eu-north-1",
  "sa-east-1", "me-south-1", "af-south-1",
];

export default function Generate() {
  const navigate = useNavigate();
  const [mode, setMode] = useState("upload"); // "upload" | "paste"
  const [xml, setXml] = useState("");
  const [title, setTitle] = useState("");
  const [fileName, setFileName] = useState("");
  const [region, setRegion] = useState("ap-southeast-2");
  const [generating, setGenerating] = useState(false);
  const [refreshingPrices, setRefreshingPrices] = useState(false);
  const [streamLog, setStreamLog] = useState([]);
  const [progress, setProgress] = useState(0); // chars received
  const fileInputRef = useRef(null);
  const logRef = useRef(null);

  const refreshPrices = async () => {
    setRefreshingPrices(true);
    try {
      const { data } = await api.post(`/pricing/refresh?region=${region}`);
      const ok = Object.values(data.results).filter((r) => r.ok).length;
      const tot = Object.keys(data.results).length;
      toast.success(`AWS prices refreshed (${ok}/${tot} services live)`);
    } catch {
      toast.error("Price refresh failed");
    } finally {
      setRefreshingPrices(false);
    }
  };

  const handleFile = async (file) => {
    if (!file) return;
    const text = await file.text();
    setXml(text);
    setFileName(file.name);
    if (!title) setTitle(file.name.replace(/\.(drawio|xml)$/i, "").replace(/[-_]/g, " "));
  };

  const onDrop = (e) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  };

  const appendLog = (line) => {
    setStreamLog((cur) => [...cur.slice(-200), line]);
    setTimeout(() => {
      if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
    }, 0);
  };

  const start = async () => {
    if (!xml.trim()) {
      toast.error("Provide a draw.io XML first");
      return;
    }
    if (!title.trim()) {
      toast.error("Give your design a title");
      return;
    }
    setGenerating(true);
    setStreamLog([]);
    setProgress(0);
    appendLog("$ architecht generate --model claude-sonnet-4.5");
    appendLog("» parsing drawio xml...");

    try {
      const token = localStorage.getItem("architecht_token");
      const res = await fetch(`${API}/lld/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ title, xml, region }),
      });

      if (!res.ok) {
        const errText = await res.text().catch(() => "");
        throw new Error(`HTTP ${res.status}: ${errText.slice(0, 200)}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let charCount = 0;
      let lldId = null;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const events = buf.split("\n\n");
        buf = events.pop();
        for (const evt of events) {
          const line = evt.trim();
          if (!line.startsWith("data: ")) continue;
          let payload;
          try { payload = JSON.parse(line.slice(6)); } catch { continue; }

          if (payload.type === "meta") {
            appendLog(`✓ parsed ${payload.pages.length} page(s), ${Object.keys(payload.service_counts).length} unique services`);
            appendLog(`» approx baseline cost: $${payload.estimated_monthly_cost_usd}/mo`);
            appendLog("» streaming LLD from claude-sonnet-4.5...");
          } else if (payload.type === "delta") {
            charCount += payload.content.length;
            setProgress(charCount);
            // log last meaningful line of streamed text
            const lastLine = payload.content.split("\n").pop().trim();
            if (lastLine) appendLog(lastLine.slice(0, 120));
          } else if (payload.type === "error") {
            throw new Error(payload.message);
          } else if (payload.type === "done") {
            lldId = payload.lld_id;
            appendLog(`✓ done. saved as ${lldId}`);
          }
        }
      }

      if (lldId) {
        toast.success("LLD generated");
        navigate(`/lld/${lldId}`);
      } else {
        // Stream cut before 'done' — try to recover by title (backend persists in finally)
        appendLog("» stream ended without 'done'. attempting recovery...");
        // Give backend a moment to flush its insert
        await new Promise((r) => setTimeout(r, 1500));
        try {
          const { data } = await (await import("@/lib/api")).api.get(
            `/lld/find-by-title?title=${encodeURIComponent(title)}`
          );
          if (data?.id) {
            appendLog(`✓ recovered as ${data.id}`);
            toast.success("LLD recovered");
            navigate(`/lld/${data.id}`);
            return;
          }
        } catch {
          // fall through
        }
        throw new Error("Generation did not complete");
      }
    } catch (err) {
      appendLog(`✗ ERROR: ${err.message}`);
      toast.error(err.message || "Generation failed");
    } finally {
      setGenerating(false);
    }
  };

  return (
    <Layout>
      <div className="max-w-[1600px] mx-auto px-6 py-10">
        <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500 mb-2">
          New design / step 01
        </p>
        <h1 className="font-chivo text-4xl sm:text-5xl font-black tracking-tighter mb-2">
          Feed the architect.
        </h1>
        <p className="text-zinc-400 max-w-2xl mb-10">
          Drop a draw.io / XML export. We&apos;ll parse every tab, detect AWS services, and stream a
          full LLD with networking, IAM, OSI layers, CI/CD and cost estimation.
        </p>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-0 border-l border-t border-zinc-800">
          {/* Input pane */}
          <div className="bg-zinc-950 border-r border-b border-zinc-800 p-6">
            <div className="flex items-center gap-1 mb-6">
              <button
                data-testid="mode-upload"
                onClick={() => setMode("upload")}
                className={`px-3 py-2 text-[11px] font-mono uppercase tracking-wider transition-colors ${
                  mode === "upload" ? "bg-white text-black" : "text-zinc-400 hover:text-white"
                }`}
              >
                <UploadSimple size={12} className="inline mr-1.5" /> Upload
              </button>
              <button
                data-testid="mode-paste"
                onClick={() => setMode("paste")}
                className={`px-3 py-2 text-[11px] font-mono uppercase tracking-wider transition-colors ${
                  mode === "paste" ? "bg-white text-black" : "text-zinc-400 hover:text-white"
                }`}
              >
                <Code size={12} className="inline mr-1.5" /> Paste XML
              </button>
            </div>

            <div className="mb-5">
              <label className="block text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-2">
                Design title
              </label>
              <input
                data-testid="lld-title"
                type="text"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Acme Checkout — Multi-AZ Prod"
                className="w-full bg-black border border-zinc-800 px-3 py-2.5 text-sm focus:border-white focus:outline-none font-mono"
                disabled={generating}
              />
            </div>

            <div className="mb-5 grid grid-cols-3 gap-3">
              <div className="col-span-2">
                <label className="block text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-2">
                  <GlobeHemisphereWest size={11} className="inline mr-1" /> AWS Region
                </label>
                <select
                  data-testid="region-select"
                  value={region}
                  onChange={(e) => setRegion(e.target.value)}
                  disabled={generating}
                  className="w-full bg-black border border-zinc-800 px-3 py-2.5 text-sm focus:border-white focus:outline-none font-mono"
                >
                  {REGIONS.map((r) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-2">
                  Prices
                </label>
                <button
                  type="button"
                  data-testid="refresh-prices"
                  onClick={refreshPrices}
                  disabled={generating || refreshingPrices}
                  title="Pull live prices for supported services from AWS Bulk Pricing JSON"
                  className="w-full border border-zinc-800 hover:border-zinc-500 px-2 py-2.5 text-[10px] font-mono uppercase tracking-wider text-zinc-300 hover:text-white transition-colors disabled:opacity-40 flex items-center justify-center gap-1.5"
                >
                  <ArrowsClockwise size={12} weight={refreshingPrices ? "fill" : "regular"} className={refreshingPrices ? "animate-spin" : ""} />
                  {refreshingPrices ? "..." : "Refresh"}
                </button>
              </div>
            </div>

            {mode === "upload" ? (
              <div
                onDrop={onDrop}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => fileInputRef.current?.click()}
                data-testid="drop-zone"
                className="border-2 border-dashed border-zinc-700 hover:border-zinc-400 transition-colors p-12 text-center cursor-pointer"
              >
                <input
                  ref={fileInputRef}
                  data-testid="file-input"
                  type="file"
                  accept=".drawio,.xml,application/xml,text/xml"
                  onChange={(e) => handleFile(e.target.files?.[0])}
                  className="hidden"
                />
                <UploadSimple size={32} weight="duotone" className="mx-auto text-zinc-500 mb-3" />
                <p className="font-chivo font-bold text-lg mb-1">
                  {fileName || "Drop .drawio / .xml here"}
                </p>
                <p className="text-xs text-zinc-500 font-mono">
                  {fileName ? `${(xml.length / 1024).toFixed(1)} KB loaded` : "or click to browse"}
                </p>
              </div>
            ) : (
              <textarea
                data-testid="xml-paste"
                value={xml}
                onChange={(e) => setXml(e.target.value)}
                placeholder="<mxfile> ... </mxfile>"
                rows={14}
                disabled={generating}
                className="w-full bg-black border border-zinc-800 px-3 py-3 text-xs font-mono focus:border-white focus:outline-none resize-y"
              />
            )}

            <button
              data-testid="generate-btn"
              onClick={start}
              disabled={generating || !xml.trim() || !title.trim()}
              className="mt-6 w-full bg-white text-black font-mono uppercase tracking-wider text-xs py-3.5 hover:bg-zinc-200 disabled:opacity-30 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2 rounded-sm"
            >
              {generating ? (
                <>
                  <Lightning size={14} weight="fill" className="animate-pulse" />
                  Generating...
                </>
              ) : (
                <>
                  <Cube size={14} weight="bold" />
                  Generate LLD →
                </>
              )}
            </button>
            <p className="text-[10px] font-mono text-zinc-600 mt-3 flex items-center gap-1.5">
              <Warning size={12} /> Generation takes 30-90 seconds. Don&apos;t close the tab.
            </p>
          </div>

          {/* Stream pane */}
          <div className="bg-black border-r border-b border-zinc-800 p-0 flex flex-col">
            <div className="border-b border-zinc-800 px-5 py-3 flex items-center justify-between">
              <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500">
                ╴ generation stream
              </span>
              <span className="text-[10px] font-mono text-amber-500">
                {progress > 0 ? `${(progress / 1024).toFixed(1)} KB` : "idle"}
              </span>
            </div>
            <div
              ref={logRef}
              data-testid="stream-log"
              className="flex-1 overflow-y-auto p-5 font-mono text-xs space-y-1 min-h-[400px] max-h-[600px]"
            >
              {streamLog.length === 0 ? (
                <p className="text-zinc-700">$ awaiting input...</p>
              ) : (
                streamLog.map((line, i) => (
                  <p
                    key={i}
                    className={
                      i === streamLog.length - 1
                        ? "text-white cursor-blink"
                        : line.startsWith("✓")
                          ? "text-green-400"
                          : line.startsWith("✗")
                            ? "text-red-400"
                            : line.startsWith("»")
                              ? "text-amber-400"
                              : "text-zinc-500"
                    }
                  >
                    {line}
                  </p>
                ))
              )}
            </div>
          </div>
        </div>
      </div>
    </Layout>
  );
}
