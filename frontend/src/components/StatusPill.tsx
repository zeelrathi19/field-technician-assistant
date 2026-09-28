const CLS: Record<string, string> = {
  Open: "st-open",
  "In Progress": "st-progress",
  "On Hold": "st-hold",
  Completed: "st-done",
};

export function StatusPill({ status }: { status: string }) {
  return <span className={`pill ${CLS[status] ?? ""}`}>{status}</span>;
}
