export default function RunsTable() {
  const runs = props.runs || [];

  const cell = "px-3 py-2 whitespace-nowrap";
  const num = (v) => (v === null || v === undefined ? "—" : v);

  return (
    <div className="w-full overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-muted/60 text-left text-muted-foreground">
            <th className={cell}>Run</th>
            <th className={cell}>Skill</th>
            <th className={cell}>Progress</th>
            <th className={cell}>Baseline</th>
            <th className={cell}>Improved</th>
            <th className={cell}>Δ</th>
            <th className={cell}>Status</th>
            <th className={cell}></th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.run_id} className="border-t border-border hover:bg-muted/30">
              <td className={cell}>
                <button
                  className="font-mono text-primary hover:underline cursor-pointer"
                  title="Open this run (all stages & documents)"
                  onClick={() => sendUserMessage(`open ${r.run_id}`)}
                >
                  {r.run_id}
                </button>
              </td>
              <td className={cell}>{r.skill}</td>
              <td className={cell}>{r.progress}</td>
              <td className={cell + " font-semibold"}>{num(r.baseline)}</td>
              <td className={cell + " font-semibold"}>{num(r.improved)}</td>
              <td className={cell + " font-semibold"}>{num(r.delta)}</td>
              <td className={cell}>{r.status}</td>
              <td className={cell}>
                {r.resumable ? (
                  <button
                    className="rounded border border-border px-2 py-0.5 text-xs hover:bg-muted"
                    title="Continue optimizing this run's improved skill"
                    onClick={() => sendUserMessage(`resume ${r.run_id}`)}
                  >
                    ⟳ Resume
                  </button>
                ) : null}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
