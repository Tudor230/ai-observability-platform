export function QueryError({ what, error }: { what: string; error: unknown }) {
  const message =
    error instanceof Error ? error.message : error ? String(error) : "";
  return (
    <p className="error" role="alert">
      Failed to load {what}.{" "}
      {message && <span className="muted">({message})</span>}
    </p>
  );
}
