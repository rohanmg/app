import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import Layout from "@/components/Layout";
import { FileText, Plus, Trash, CurrencyDollar, Cube, ArrowRight } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Dashboard() {
  const [llds, setLlds] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  const load = async () => {
    try {
      const { data } = await api.get("/lld");
      setLlds(data);
    } catch {
      toast.error("Failed to load LLDs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const remove = async (id, e) => {
    e.stopPropagation();
    e.preventDefault();
    if (!window.confirm("Delete this LLD permanently?")) return;
    try {
      await api.delete(`/lld/${id}`);
      setLlds((cur) => cur.filter((l) => l.id !== id));
      toast.success("Deleted");
    } catch {
      toast.error("Delete failed");
    }
  };

  return (
    <Layout>
      <div className="max-w-[1600px] mx-auto px-6 py-10">
        <div className="flex items-end justify-between mb-10">
          <div>
            <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-zinc-500 mb-2">
              The Vault
            </p>
            <h1 className="font-chivo text-4xl sm:text-5xl font-black tracking-tighter">
              Your low-level designs
            </h1>
          </div>
          <Link
            to="/generate"
            data-testid="dashboard-new-cta"
            className="hidden sm:flex items-center gap-2 bg-white text-black px-5 py-3 text-xs font-mono uppercase tracking-wider hover:bg-zinc-200 transition-colors rounded-sm"
          >
            <Plus size={14} weight="bold" /> New generation
          </Link>
        </div>

        {loading ? (
          <div className="font-mono text-xs text-zinc-500 tracking-wider uppercase">Loading vault…</div>
        ) : llds.length === 0 ? (
          <div className="border border-dashed border-zinc-800 p-16 text-center">
            <Cube size={42} weight="duotone" className="mx-auto text-zinc-700 mb-4" />
            <h3 className="font-chivo text-xl font-bold mb-2">Vault is empty</h3>
            <p className="text-sm text-zinc-500 mb-6 max-w-md mx-auto">
              Upload an AWS architecture from draw.io and let Claude Sonnet 4.5 generate a deep
              LLD covering networking, IAM, CI/CD, OSI layers and estimated cost.
            </p>
            <Link
              to="/generate"
              data-testid="empty-state-cta"
              className="inline-flex items-center gap-2 bg-white text-black px-5 py-3 text-xs font-mono uppercase tracking-wider hover:bg-zinc-200 transition-colors rounded-sm"
            >
              <Plus size={14} weight="bold" /> Generate your first LLD
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-0 border-l border-t border-zinc-800">
            {llds.map((l) => (
              <button
                key={l.id}
                data-testid={`lld-card-${l.id}`}
                onClick={() => navigate(`/lld/${l.id}`)}
                className="group text-left bg-zinc-950 hover:bg-zinc-900 border-r border-b border-zinc-800 p-6 transition-colors"
              >
                <div className="flex items-start justify-between mb-4">
                  <FileText size={20} weight="duotone" className="text-zinc-500 group-hover:text-white transition-colors" />
                  <span
                    onClick={(e) => remove(l.id, e)}
                    data-testid={`lld-delete-${l.id}`}
                    className="opacity-0 group-hover:opacity-100 text-zinc-600 hover:text-red-400 transition-all cursor-pointer"
                  >
                    <Trash size={14} />
                  </span>
                </div>
                <h3 className="font-chivo font-bold text-lg leading-tight mb-3 line-clamp-2 group-hover:text-white">
                  {l.title}
                </h3>
                <div className="flex items-center gap-3 text-[10px] font-mono uppercase tracking-wider text-zinc-500 mb-3">
                  <span>{new Date(l.created_at).toLocaleDateString()}</span>
                  <span className="text-zinc-700">•</span>
                  <span>{l.service_count} services</span>
                </div>
                <div className="flex items-center justify-between pt-3 border-t border-zinc-800">
                  <div className="flex items-center gap-1 text-amber-500 font-mono text-sm">
                    <CurrencyDollar size={13} weight="bold" />
                    {l.estimated_monthly_cost_usd.toFixed(0)}
                    <span className="text-zinc-600 text-[10px] ml-1">/mo est.</span>
                  </div>
                  <ArrowRight size={14} className="text-zinc-600 group-hover:text-white group-hover:translate-x-0.5 transition-all" />
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
