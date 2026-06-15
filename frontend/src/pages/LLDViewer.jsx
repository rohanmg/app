import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api, API } from "@/lib/api";
import Layout from "@/components/Layout";
import DiagramPreview from "@/components/DiagramPreview";
import { DownloadSimple, FileText, FileDoc, CurrencyDollar, ArrowLeft, Stack, ShareNetwork, GlobeHemisphereWest } from "@phosphor-icons/react";
import { toast } from "sonner";
import ShareDialog from "@/components/ShareDialog";

export default function LLDViewer() {
  const { id } = useParams();
  const [lld, setLld] = useState(null);
  const [loading, setLoading] = useState(true);
  const [activeService, setActiveService] = useState(null);
  const [shareOpen, setShareOpen] = useState(false);
  const docRef = useRef(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const { data } = await api.get(`/lld/${id}`);
        if (alive) setLld(data);
      } catch {
        toast.error("Failed to load LLD");
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [id]);

  const onNodeClick = (service) => {
    setActiveService(service);
    const anchor = `svc-${service.toLowerCase().replace(/[^a-z0-9]/g, "")}`;
    const target = document.getElementById(anchor);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    } else {
      // fallback: find first ### heading containing service name
      const headings = docRef.current?.querySelectorAll("h3");
      headings?.forEach((h) => {
        if (h.textContent.toLowerCase().includes(service.toLowerCase())) {
          h.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    }
  };

  const downloadFile = async (format) => {
    try {
      const token = localStorage.getItem("architecht_token");
      const res = await fetch(`${API}/lld/${id}/export/${format}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("export failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${lld.title.replace(/[^a-z0-9]/gi, "_")}.${format === "markdown" ? "md" : "docx"}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Download failed");
    }
  };

  const printPdf = () => window.print();

  // Build TOC from markdown ## headings
  const toc = useMemo(() => {
    if (!lld?.markdown) return [];
    const lines = lld.markdown.split("\n");
    const items = [];
    for (const ln of lines) {
      const m = /^##\s+(.+)$/.exec(ln);
      if (m) {
        const text = m[1].replace(/<[^>]+>/g, "").trim();
        const slug = text.toLowerCase().replace(/[^a-z0-9]+/g, "-");
        items.push({ text, slug });
      }
    }
    return items;
  }, [lld?.markdown]);

  if (loading) {
    return (
      <Layout>
        <div className="max-w-[1600px] mx-auto px-6 py-10 font-mono text-xs text-zinc-500">Loading LLD…</div>
      </Layout>
    );
  }

  if (!lld) {
    return (
      <Layout>
        <div className="max-w-[1600px] mx-auto px-6 py-10">
          <p className="text-zinc-500 mb-4">LLD not found.</p>
          <Link to="/dashboard" className="text-white underline">Back to vault</Link>
        </div>
      </Layout>
    );
  }

  const pages = lld.layout?.pages || [];

  return (
    <Layout>
      <div className="max-w-[1600px] mx-auto px-6 py-6 print:p-0 print:max-w-none">
        {/* Header */}
        <div className="flex items-start justify-between flex-wrap gap-4 mb-6 print:hidden">
          <div>
            <Link to="/dashboard" data-testid="back-vault" className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 hover:text-white inline-flex items-center gap-1.5 mb-2">
              <ArrowLeft size={12} /> Back to vault
            </Link>
            <h1 className="font-chivo text-3xl sm:text-4xl font-black tracking-tighter">{lld.title}</h1>
            <div className="flex items-center gap-3 mt-2 text-[11px] font-mono text-zinc-500 uppercase tracking-wider">
              <span>{new Date(lld.created_at).toLocaleDateString()}</span>
              <span className="text-zinc-700">•</span>
              <span>{lld.services.length} services</span>
              <span className="text-zinc-700">•</span>
              <span className="inline-flex items-center gap-1"><GlobeHemisphereWest size={12} /> {lld.region || "us-east-1"}</span>
              <span className="text-zinc-700">•</span>
              <span className="text-amber-500 inline-flex items-center gap-1">
                <CurrencyDollar size={12} weight="bold" />
                {lld.estimated_monthly_cost_usd.toFixed(0)}/mo est.
              </span>
              {lld.is_public && (
                <>
                  <span className="text-zinc-700">•</span>
                  <span className="text-green-400 inline-flex items-center gap-1">
                    <ShareNetwork size={12} weight="fill" /> public
                  </span>
                </>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              data-testid="share-btn"
              onClick={() => setShareOpen(true)}
              className={`flex items-center gap-1.5 border px-3 py-2 text-[11px] font-mono uppercase tracking-wider transition-colors rounded-sm ${
                lld.is_public
                  ? "border-green-700/50 text-green-400 hover:bg-green-950/30"
                  : "border-zinc-800 hover:border-zinc-500 text-zinc-300 hover:text-white"
              }`}
            >
              <ShareNetwork size={13} weight={lld.is_public ? "fill" : "regular"} />
              {lld.is_public ? "Public" : "Share"}
            </button>
            <button
              data-testid="export-md"
              onClick={() => downloadFile("markdown")}
              className="flex items-center gap-1.5 border border-zinc-800 hover:border-zinc-500 px-3 py-2 text-[11px] font-mono uppercase tracking-wider text-zinc-300 hover:text-white transition-colors rounded-sm"
            >
              <FileText size={13} /> .md
            </button>
            <button
              data-testid="export-docx"
              onClick={() => downloadFile("docx")}
              className="flex items-center gap-1.5 border border-zinc-800 hover:border-zinc-500 px-3 py-2 text-[11px] font-mono uppercase tracking-wider text-zinc-300 hover:text-white transition-colors rounded-sm"
            >
              <FileDoc size={13} /> .docx
            </button>
            <button
              data-testid="export-pdf"
              onClick={printPdf}
              className="flex items-center gap-1.5 bg-white text-black px-3 py-2 text-[11px] font-mono uppercase tracking-wider hover:bg-zinc-200 transition-colors rounded-sm"
            >
              <DownloadSimple size={13} weight="bold" /> Print / PDF
            </button>
          </div>
        </div>

        {/* Service pills */}
        {lld.services.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-6 print:hidden">
            {lld.services.map((s) => (
              <button
                key={s.name}
                data-testid={`pill-${s.name.replace(/\s+/g, "-").toLowerCase()}`}
                onClick={() => onNodeClick(s.name)}
                title={s.assumption ? `${s.assumption} — $${s.monthly_cost_usd}/mo (${s.source})` : undefined}
                className={`font-mono text-[10px] uppercase tracking-wider border px-2 py-1 transition-colors ${
                  activeService === s.name
                    ? "bg-amber-500 text-black border-amber-500"
                    : "border-zinc-700 bg-zinc-900/50 text-zinc-300 hover:border-zinc-500 hover:text-white"
                }`}
              >
                {s.name} <span className="text-zinc-500 ml-1">×{s.count}</span>
              </button>
            ))}
          </div>
        )}

        {/* Split pane: diagram (left) + LLD (right) */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-0 border-t border-l border-zinc-800 print:block print:border-0">
          {/* Diagram (left) */}
          <div className="lg:col-span-5 bg-zinc-950 border-r border-b border-zinc-800 print:hidden">
            <div className="sticky top-14">
              <div className="px-4 py-3 border-b border-zinc-800 flex items-center gap-2">
                <Stack size={14} weight="duotone" className="text-amber-500" />
                <span className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-400">
                  Diagram · {pages.length} page(s)
                </span>
              </div>
              <div style={{ height: "calc(100vh - 200px)" }}>
                <DiagramPreview pages={pages} activeService={activeService} onNodeClick={onNodeClick} />
              </div>
            </div>
          </div>

          {/* LLD document (right) */}
          <div className="lg:col-span-7 bg-black border-r border-b border-zinc-800 print:bg-white print:text-black">
            <div className="grid grid-cols-12 gap-0">
              {/* TOC */}
              <aside className="hidden xl:block col-span-3 border-r border-zinc-800 print:hidden">
                <div className="sticky top-14 p-4 max-h-[calc(100vh-56px)] overflow-y-auto">
                  <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-3">Contents</p>
                  <nav className="space-y-1">
                    {toc.map((t) => (
                      <a
                        key={t.slug}
                        href={`#${t.slug}`}
                        data-testid={`toc-${t.slug}`}
                        className="block text-xs text-zinc-400 hover:text-white py-1 leading-tight"
                      >
                        {t.text}
                      </a>
                    ))}
                  </nav>
                </div>
              </aside>

              {/* Markdown */}
              <div className="col-span-12 xl:col-span-9 p-6 sm:p-8" ref={docRef}>
                <div className="lld-prose">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[]}
                    components={{
                      h2: ({ children, ...props }) => {
                        const text = String(children).replace(/<[^>]+>/g, "");
                        const slug = text.toLowerCase().replace(/[^a-z0-9]+/g, "-");
                        return <h2 id={slug} {...props}>{children}</h2>;
                      },
                      h3: ({ children, ...props }) => {
                        const text = String(children).replace(/<[^>]+>/g, "");
                        const slug = `svc-${text.toLowerCase().replace(/[^a-z0-9]/g, "")}`;
                        return <h3 id={slug} {...props}>{children}</h3>;
                      },
                    }}
                  >
                    {lld.markdown}
                  </ReactMarkdown>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <ShareDialog
        lldId={id}
        open={shareOpen}
        onClose={() => {
          setShareOpen(false);
          // refresh to reflect new public state in header
          api.get(`/lld/${id}`).then(({ data }) => setLld(data)).catch(() => {});
        }}
        initialPublic={lld.is_public}
        initialToken={lld.share_token}
      />
    </Layout>
  );
}
