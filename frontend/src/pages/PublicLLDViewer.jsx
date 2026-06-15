import { useEffect, useMemo, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { API } from "@/lib/api";
import DiagramPreview from "@/components/DiagramPreview";
import { Cube, CurrencyDollar, Stack, GlobeHemisphereWest } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function PublicLLDViewer() {
  const { token } = useParams();
  const [lld, setLld] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeService, setActiveService] = useState(null);
  const docRef = useRef(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch(`${API}/public/lld/${token}`);
        if (!res.ok) throw new Error(res.status === 404 ? "This shared link is invalid or has been revoked." : `HTTP ${res.status}`);
        const data = await res.json();
        if (alive) setLld(data);
      } catch (e) {
        if (alive) setError(e.message);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => { alive = false; };
  }, [token]);

  const onNodeClick = (service) => {
    setActiveService(service);
    const anchor = `svc-${service.toLowerCase().replace(/[^a-z0-9]/g, "")}`;
    const target = document.getElementById(anchor);
    if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    else {
      docRef.current?.querySelectorAll("h3").forEach((h) => {
        if (h.textContent.toLowerCase().includes(service.toLowerCase())) {
          h.scrollIntoView({ behavior: "smooth", block: "start" });
        }
      });
    }
  };

  const toc = useMemo(() => {
    if (!lld?.markdown) return [];
    const items = [];
    for (const ln of lld.markdown.split("\n")) {
      const m = /^##\s+(.+)$/.exec(ln);
      if (m) {
        const text = m[1].replace(/<[^>]+>/g, "").trim();
        items.push({ text, slug: text.toLowerCase().replace(/[^a-z0-9]+/g, "-") });
      }
    }
    return items;
  }, [lld?.markdown]);

  if (loading) {
    return (
      <div className="min-h-screen bg-[#09090B] text-zinc-100 flex items-center justify-center font-mono text-xs text-zinc-500">
        Loading shared LLD…
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-[#09090B] text-zinc-100 flex items-center justify-center p-6">
        <div className="border border-zinc-800 p-8 text-center max-w-md">
          <Cube size={32} weight="duotone" className="mx-auto text-zinc-700 mb-3" />
          <h2 className="font-chivo text-2xl font-black mb-2">Link unavailable</h2>
          <p className="text-zinc-400 text-sm">{error}</p>
        </div>
      </div>
    );
  }

  const pages = lld.layout?.pages || [];

  return (
    <div className="min-h-screen bg-[#09090B] text-zinc-100">
      <header className="sticky top-0 z-50 bg-black/70 backdrop-blur-xl border-b border-zinc-800">
        <div className="max-w-[1600px] mx-auto px-6 h-14 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2.5">
            <Cube size={22} weight="duotone" />
            <span className="font-chivo font-black text-lg tracking-tighter">ARCHITECHT</span>
            <span className="font-mono text-[10px] text-zinc-500 tracking-[0.2em] uppercase ml-2">
              · public read-only
            </span>
          </Link>
          <Link to="/register" data-testid="public-register" className="text-[11px] font-mono uppercase tracking-wider bg-white text-black px-3 py-1.5 hover:bg-zinc-200 rounded-sm">
            Build yours →
          </Link>
        </div>
      </header>

      <div className="max-w-[1600px] mx-auto px-6 py-6">
        <h1 data-testid="public-title" className="font-chivo text-3xl sm:text-4xl font-black tracking-tighter">
          {lld.title}
        </h1>
        <div className="flex items-center gap-3 mt-2 text-[11px] font-mono text-zinc-500 uppercase tracking-wider">
          <span>{new Date(lld.created_at).toLocaleDateString()}</span>
          <span className="text-zinc-700">•</span>
          <span>{lld.services?.length || 0} services</span>
          <span className="text-zinc-700">•</span>
          <span className="inline-flex items-center gap-1"><GlobeHemisphereWest size={12} /> {lld.region}</span>
          <span className="text-zinc-700">•</span>
          <span className="text-amber-500 inline-flex items-center gap-1">
            <CurrencyDollar size={12} weight="bold" />
            {lld.estimated_monthly_cost_usd?.toFixed(0)}/mo est.
          </span>
        </div>

        {lld.services?.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-6">
            {lld.services.map((s) => (
              <button
                key={s.name}
                data-testid={`public-pill-${s.name.replace(/\s+/g, "-").toLowerCase()}`}
                onClick={() => onNodeClick(s.name)}
                className={`font-mono text-[10px] uppercase tracking-wider border px-2 py-1 transition-colors ${
                  activeService === s.name ? "bg-amber-500 text-black border-amber-500" :
                  "border-zinc-700 bg-zinc-900/50 text-zinc-300 hover:border-zinc-500 hover:text-white"
                }`}
                title={s.assumption || ""}
              >
                {s.name} <span className="text-zinc-500 ml-1">×{s.count}</span>
              </button>
            ))}
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-0 border-t border-l border-zinc-800 mt-6">
          <div className="lg:col-span-5 bg-zinc-950 border-r border-b border-zinc-800">
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

          <div className="lg:col-span-7 bg-black border-r border-b border-zinc-800">
            <div className="grid grid-cols-12 gap-0">
              <aside className="hidden xl:block col-span-3 border-r border-zinc-800">
                <div className="sticky top-14 p-4 max-h-[calc(100vh-56px)] overflow-y-auto">
                  <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-3">Contents</p>
                  <nav className="space-y-1">
                    {toc.map((t) => (
                      <a key={t.slug} href={`#${t.slug}`} className="block text-xs text-zinc-400 hover:text-white py-1 leading-tight">
                        {t.text}
                      </a>
                    ))}
                  </nav>
                </div>
              </aside>

              <div className="col-span-12 xl:col-span-9 p-6 sm:p-8" ref={docRef}>
                <div className="lld-prose">
                  <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
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
    </div>
  );
}
