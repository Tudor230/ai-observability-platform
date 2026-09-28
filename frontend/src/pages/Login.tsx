import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { Alert, Button, Field, TextInput } from "../components/core";
import { IconSparkle } from "../components/core/icons";
import { useAuth } from "../state/AuthContext";

export default function Login() {
  const { profile, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const from = (location.state as { from?: string } | null)?.from ?? "/";
  if (!loading && profile) return <Navigate to={from} replace />;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
      navigate(from, { replace: true });
    } catch {
      setError("Invalid email or password.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="login">
      <form className="login__card" onSubmit={submit}>
        <div className="login__brand">
          <span className="side-nav__brand-mark">
            <IconSparkle size={22} />
          </span>
          <span>AI Observability</span>
        </div>
        <p className="login__hint">Sign in with your platform account.</p>
        {error ? <Alert variant="danger" message={error} /> : null}
        <Field label="Email">
          <TextInput
            type="email"
            autoComplete="username"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
        </Field>
        <Field label="Password">
          <TextInput
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
        </Field>
        <Button variant="primary" size="M" type="submit" disabled={busy}>
          {busy ? "Signing in…" : "Sign in"}
        </Button>
        <p className="login__hint">
          Accounts are provisioned by an administrator. Ask your manager or an
          admin for access.
        </p>
      </form>
    </div>
  );
}
