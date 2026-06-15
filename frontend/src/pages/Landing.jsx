import { Link, Navigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Cube, Lightning, ShieldCheck, GitBranch, CurrencyDollar, Stack } from "@phosphor-icons/react";

export default function Landing() {
  const { user } = useAuth();
  if (user) return <Navigate to="/dashboard" replace />;

  return (
    <div className="min-h-screen bg-[#09090B] text-zinc-100">
      <header className="border-b border-zinc-800">
        <div className="max-w-[1400px] mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Cube size={22} weight="duotone" />
            <span className="font-chivo font-black text-lg tracking-tighter">ARCHITECHT</span>
          </div>
          <div className="flex items-center gap-2">
            <Link
              to="/login"
              data-testid="landing-login"
              className="text-xs font-mono uppercase tracking-wider text-zinc-400 hover:text-white px-3 py-2"
            >
              Sign in
            </Link>
            <Link
              to="/register"
              data-testid="landing-register"
              className="text-xs font-mono uppercase tracking-wider bg-white text-black hover:bg-zinc-200 px-4 py-2 rounded-sm"
            >
              Get started →
            </Link>
          </div>
        </div>
      </header>

      <section className="relative overflow-hidden">
        <div className="absolute inset-0 dot-grid opacity-40" />
        <div className="relative max-w-[1400px] mx-auto px-6 py-24 sm:py-32">
          <p className="text-[10px] font-mono uppercase tracking-[0.3em] text-amber-500 mb-5">
            // claude sonnet 4.5 · draw.io · aws
          </p>
          <h1 className="font-chivo text-5xl sm:text-7xl lg:text-8xl font-black tracking-tighter max-w-5xl leading-[0.95]">
            Diagrams in.
            <br />
            <span className="text-zinc-500">Production-grade LLDs out.</span>
          </h1>
          <p className="text-zinc-400 text-lg max-w-2xl mt-8 leading-relaxed">
            Drop your AWS architecture from draw.io. Architecht parses every tab, maps it across
            all 7 OSI layers, generates IAM policies, ingress/egress controls, CI/CD pipelines and
            a monthly cost estimate — in 60 seconds.
          </p>

          <div className="flex flex-wrap items-center gap-3 mt-10">
            <Link
              to="/register"
              data-testid="hero-cta"
              className="bg-white text-black px-6 py-3.5 text-sm font-mono uppercase tracking-wider hover:bg-zinc-200 transition-colors rounded-sm"
            >
              Generate your first LLD →
            </Link>
            <Link
              to="/login"
              className="border border-zinc-700 hover:border-zinc-400 px-6 py-3.5 text-sm font-mono uppercase tracking-wider text-zinc-300 hover:text-white transition-colors rounded-sm"
            >
              I have an account
            </Link>
          </div>
        </div>
      </section>

      <section className="border-t border-zinc-800">
        <div className="max-w-[1400px] mx-auto grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-0 border-l border-zinc-800">
          {[
            { icon: Stack, title: "Multi-page parsing", body: "Every drawio tab — zoom-ins, regions, sub-systems — captured and reconciled into one LLD." },
            { icon: Lightning, title: "All 7 OSI layers", body: "L1 physical to L7 application. Every protocol, every port, every encryption boundary." },
            { icon: ShieldCheck, title: "IAM & Security depth", body: "Least-privilege policy snippets, SGs/NACLs as tables, ingress/egress per service." },
            { icon: GitBranch, title: "CI/CD playbook", body: "Pipeline stages, IaC patterns, blue/green & canary strategy — opinionated and concrete." },
            { icon: CurrencyDollar, title: "Cost estimation", body: "Rule-of-thumb monthly cost from detected services + Claude-led optimization advice." },
            { icon: Cube, title: "Clickable & exportable", body: "Click any diagram node → jump to its LLD section. Export to Markdown, Word, or PDF." },
          ].map((f, i) => (
            <div key={i} className="border-r border-b border-zinc-800 p-8 hover:bg-zinc-950 transition-colors">
              <f.icon size={26} weight="duotone" className="text-amber-500 mb-4" />
              <h3 className="font-chivo font-bold text-xl mb-2">{f.title}</h3>
              <p className="text-zinc-500 text-sm leading-relaxed">{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      <footer className="border-t border-zinc-800 py-8 text-center text-xs font-mono text-zinc-600">
        ARCHITECHT · Powered by Claude Sonnet 4.5
      </footer>
    </div>
  );
}
