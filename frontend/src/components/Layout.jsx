import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Cube, SignOut, House, Plus } from "@phosphor-icons/react";

export default function Layout({ children }) {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#09090B] text-zinc-100">
      <header className="sticky top-0 z-50 bg-black/70 backdrop-blur-xl border-b border-zinc-800">
        <div className="max-w-[1600px] mx-auto px-6 h-14 flex items-center justify-between">
          <Link to="/dashboard" data-testid="header-logo" className="flex items-center gap-2.5 group">
            <Cube size={22} weight="duotone" className="text-white" />
            <span className="font-chivo font-black text-lg tracking-tighter">ARCHITECHT</span>
            <span className="font-mono text-[10px] text-zinc-500 tracking-[0.2em] uppercase ml-1 group-hover:text-zinc-300 transition-colors">
              v1.0
            </span>
          </Link>

          <nav className="flex items-center gap-2">
            <Link
              to="/dashboard"
              data-testid="nav-dashboard"
              className={`px-3 py-1.5 text-xs font-mono tracking-wider uppercase transition-colors ${
                location.pathname === "/dashboard" ? "text-white" : "text-zinc-500 hover:text-white"
              }`}
            >
              <House size={14} className="inline mr-1.5" />
              Vault
            </Link>
            <Link
              to="/generate"
              data-testid="nav-new"
              className="px-3 py-1.5 text-xs font-mono tracking-wider uppercase bg-white text-black hover:bg-zinc-200 transition-colors flex items-center gap-1.5 rounded-sm"
            >
              <Plus size={14} weight="bold" />
              New LLD
            </Link>
            {user && (
              <div className="flex items-center gap-3 ml-3 pl-3 border-l border-zinc-800">
                <span data-testid="user-name" className="text-xs font-mono text-zinc-400">
                  {user.name}
                </span>
                <button
                  data-testid="logout-btn"
                  onClick={logout}
                  className="text-zinc-500 hover:text-white transition-colors"
                  title="Logout"
                >
                  <SignOut size={16} />
                </button>
              </div>
            )}
          </nav>
        </div>
      </header>

      <main>{children}</main>
    </div>
  );
}
