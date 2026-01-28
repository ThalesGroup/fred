interface App {
  name: string;
  description: string;
  url: string;
}

const apps: App[] = [
  {
    name: "Google",
    description: "Your favorite search engine in PRISM !",
    url: "https://google.com",
  },
  {
    name: "Wikipedia",
    description: "Your favorite wiki in PRISM !",
    url: "https://google.com",
  },
];

export function TeamAppsPage() {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))", gap: "16px" }}>
      {apps.map((app) => (
        <div
          key={app.name}
        >
          <a href={app.url} target="_blank" rel="noreferrer" style={{ fontSize: 14, color: "#1976d2" }}>
            Open {app.url}
          </a>
        </div>
      ))}
    </div>
  );
}
