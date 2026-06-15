import { useNavigate, Navigate, Link } from "react-router-dom";
import { useState } from "react";
import { useAuth } from "@/contexts/AuthContext";
import { Cube } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function Register() {
  const { user, register } = useAuth();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  if (user) return <Navigate to="/dashboard" replace />;

  const submit = async (e) => {
    e.preventDefault();
    setSubmitting(true);
    try {
      await register(name, email, password);
      toast.success("Welcome aboard.");
      navigate("/dashboard");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Registration failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#09090B] flex items-center justify-center p-6 dot-grid">
      <div className="w-full max-w-md bg-zinc-950 border border-zinc-800 p-8">
        <Link to="/" className="flex items-center gap-2 mb-8">
          <Cube size={22} weight="duotone" className="text-white" />
          <span className="font-chivo font-black text-lg tracking-tighter">ARCHITECHT</span>
        </Link>

        <h1 className="font-chivo text-3xl font-black tracking-tighter mb-1">Create account</h1>
        <p className="text-xs font-mono text-zinc-500 tracking-wider uppercase mb-8">
          Start designing in seconds
        </p>

        <form onSubmit={submit} className="space-y-4">
          <div>
            <label className="block text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-2">
              Name
            </label>
            <input
              data-testid="register-name"
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-black border border-zinc-800 px-3 py-2.5 text-sm focus:border-white focus:outline-none font-mono"
              placeholder="Jane Architect"
            />
          </div>
          <div>
            <label className="block text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-2">
              Email
            </label>
            <input
              data-testid="register-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-black border border-zinc-800 px-3 py-2.5 text-sm focus:border-white focus:outline-none font-mono"
              placeholder="you@company.com"
            />
          </div>
          <div>
            <label className="block text-[10px] font-mono uppercase tracking-[0.2em] text-zinc-500 mb-2">
              Password
            </label>
            <input
              data-testid="register-password"
              type="password"
              required
              minLength={6}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-black border border-zinc-800 px-3 py-2.5 text-sm focus:border-white focus:outline-none font-mono"
              placeholder="At least 6 characters"
            />
          </div>

          <button
            data-testid="register-submit"
            type="submit"
            disabled={submitting}
            className="w-full bg-white text-black font-mono tracking-wider uppercase text-xs py-3 hover:bg-zinc-200 transition-colors disabled:opacity-50 rounded-sm"
          >
            {submitting ? "Creating..." : "Create account →"}
          </button>
        </form>

        <p className="text-xs font-mono text-zinc-500 mt-6 text-center">
          Have an account?{" "}
          <Link to="/login" data-testid="goto-login" className="text-white hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
