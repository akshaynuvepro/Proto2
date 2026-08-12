export default function DocIndex() {
  const groups = props.groups || [];

  return (
    <div className="w-full space-y-3">
      {groups.map((g) => (
        <div key={g.title}>
          <div className="mb-1.5 text-sm font-semibold">{g.title}</div>
          <div className="flex flex-col gap-1">
            {g.docs.map((d) => (
              <button
                key={d}
                className="w-fit text-left rounded-md border border-border bg-background px-2.5 py-1 text-xs text-primary hover:bg-muted cursor-pointer"
                title="Read this document in the side panel"
                onClick={() => callAction({ name: "read_doc", payload: { doc: d } })}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
