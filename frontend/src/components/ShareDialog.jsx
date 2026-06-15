import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Copy, LinkSimple, X, ShareNetwork } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function ShareDialog({ lldId, open, onClose, initialPublic, initialToken }) {
  const [isPublic, setIsPublic] = useState(initialPublic || false);
  const [token, setToken] = useState(initialToken || null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setIsPublic(initialPublic || false);
    setToken(initialToken || null);
  }, [initialPublic, initialToken, open]);

  if (!open) return null;

  const publicUrl = token ? `${window.location.origin}/share/${token}` : "";

  const enableShare = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/lld/${lldId}/share`);
      setToken(data.share_token);
      setIsPublic(true);
      toast.success("Public link created");
    } catch {
      toast.error("Failed to create share link");
    } finally {
      setBusy(false);
    }
  };

  const disableShare = async () => {
    setBusy(true);
    try {
      await api.delete(`/lld/${lldId}/share`);
      setIsPublic(false);
      setToken(null);
      toast.success("Public link revoked");
    } catch {
      toast.error("Failed to revoke link");
    } finally {
      setBusy(false);
    }
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(publicUrl);
      toast.success("Link copied");
    } catch {
      toast.error("Could not copy");
    }
  };

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm" onClick={onClose}>
      <div
        data-testid="share-dialog"
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-lg bg-zinc-950 border border-zinc-800 p-6"
      >
        <div className="flex items-start justify-between mb-5">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <ShareNetwork size={18} weight="duotone" className="text-amber-500" />
              <h3 className="font-chivo font-bold text-xl tracking-tight">Share this LLD</h3>
            </div>
            <p className="text-xs font-mono uppercase tracking-wider text-zinc-500">View-only · no auth required</p>
          </div>
          <button data-testid="share-close" onClick={onClose} className="text-zinc-600 hover:text-white">
            <X size={18} />
          </button>
        </div>

        {!isPublic ? (
          <>
            <p className="text-sm text-zinc-400 mb-5 leading-relaxed">
              Generate a public read-only link. Anyone with the URL can view the markdown LLD, diagram and
              cost breakdown — no sign-in needed. You can revoke it anytime.
            </p>
            <button
              data-testid="share-enable"
              onClick={enableShare}
              disabled={busy}
              className="w-full bg-white text-black font-mono uppercase tracking-wider text-xs py-3 hover:bg-zinc-200 disabled:opacity-50 transition-colors rounded-sm flex items-center justify-center gap-2"
            >
              <LinkSimple size={14} weight="bold" />
              {busy ? "Creating…" : "Create public link"}
            </button>
          </>
        ) : (
          <>
            <p className="text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-2">
              Public URL
            </p>
            <div className="flex items-stretch gap-0 border border-zinc-800 bg-black mb-5">
              <input
                data-testid="share-url"
                readOnly
                value={publicUrl}
                className="flex-1 bg-transparent px-3 py-2.5 text-xs font-mono text-zinc-100 truncate focus:outline-none"
              />
              <button
                data-testid="share-copy"
                onClick={copy}
                className="px-4 border-l border-zinc-800 text-zinc-300 hover:text-white hover:bg-zinc-900 transition-colors flex items-center gap-1.5 text-[11px] font-mono uppercase"
              >
                <Copy size={13} /> Copy
              </button>
            </div>
            <div className="flex items-center gap-2">
              <a
                href={publicUrl}
                target="_blank"
                rel="noreferrer"
                data-testid="share-open"
                className="flex-1 text-center border border-zinc-800 hover:border-zinc-500 px-3 py-2.5 text-[11px] font-mono uppercase tracking-wider text-zinc-300 hover:text-white transition-colors rounded-sm"
              >
                Open in new tab →
              </a>
              <button
                data-testid="share-revoke"
                onClick={disableShare}
                disabled={busy}
                className="px-4 py-2.5 border border-red-900/50 text-red-400 hover:bg-red-950/30 text-[11px] font-mono uppercase tracking-wider transition-colors rounded-sm disabled:opacity-50"
              >
                Revoke
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
