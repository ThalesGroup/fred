export interface FixtureOrigins {
  readonly applicationOrigin: string;
  readonly applicationPort: number;
  readonly attackerOrigin: string;
  readonly attackerPort: number;
  readonly hostOrigin: string;
  readonly hostPort: number;
}

const ORIGIN_PARAMETERS = ["applicationOrigin", "attackerOrigin"] as const;
const LOOPBACK_ORIGIN = /^http:\/\/127\.0\.0\.1:([1-9]\d{0,4})$/;

function fixturePort(value: string, label: string): number {
  const match = LOOPBACK_ORIGIN.exec(value);
  if (!match)
    throw new Error(
      `${label} must be an absolute loopback HTTP origin with a port`,
    );

  const port = Number(match[1]);
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${label} must be a valid loopback HTTP origin`);
  }
  if (
    !Number.isSafeInteger(port) ||
    port < 1 ||
    port > 65_535 ||
    parsed.protocol !== "http:" ||
    parsed.hostname !== "127.0.0.1" ||
    parsed.port !== String(port) ||
    parsed.username ||
    parsed.password ||
    parsed.pathname !== "/" ||
    parsed.search ||
    parsed.hash ||
    parsed.origin !== value
  ) {
    throw new Error(
      `${label} must be a canonical loopback HTTP origin with a valid port`,
    );
  }
  return port;
}

function loopbackOrigin(port: number): string {
  const origin = new URL("http://127.0.0.1");
  origin.port = String(port);
  return origin.origin;
}

export function readFixtureOrigins(
  hostOrigin: string,
  search: string,
): FixtureOrigins {
  const parameters = new URLSearchParams(search);
  if (
    [...parameters.keys()].some(
      (key) => !(ORIGIN_PARAMETERS as readonly string[]).includes(key),
    ) ||
    ORIGIN_PARAMETERS.some((key) => parameters.getAll(key).length !== 1)
  ) {
    throw new Error(
      "fixture application and attacker origins are required exactly once",
    );
  }

  const hostPort = fixturePort(hostOrigin, "fixture host origin");
  const applicationPort = fixturePort(
    parameters.get("applicationOrigin")!,
    "fixture application origin",
  );
  const attackerPort = fixturePort(
    parameters.get("attackerOrigin")!,
    "fixture attacker origin",
  );
  if (new Set([hostPort, applicationPort, attackerPort]).size !== 3)
    throw new Error(
      "fixture host, application, and attacker origins must be distinct",
    );

  return Object.freeze({
    applicationOrigin: loopbackOrigin(applicationPort),
    applicationPort,
    attackerOrigin: loopbackOrigin(attackerPort),
    attackerPort,
    hostOrigin: loopbackOrigin(hostPort),
    hostPort,
  });
}

function fixtureUrl(port: number, pathname: string): URL {
  const destination = new URL("http://127.0.0.1");
  destination.port = String(port);
  destination.pathname = pathname;
  return destination;
}

export function applicationFixtureUrl(
  origins: FixtureOrigins,
  connectionTimeoutMs?: number,
): URL {
  const destination = fixtureUrl(origins.applicationPort, "/child.html");
  destination.searchParams.set("hostOrigin", origins.hostOrigin);
  if (connectionTimeoutMs !== undefined) {
    if (!Number.isSafeInteger(connectionTimeoutMs) || connectionTimeoutMs <= 0)
      throw new Error("fixture connection timeout must be a positive integer");
    destination.searchParams.set(
      "connectionTimeoutMs",
      String(connectionTimeoutMs),
    );
  }
  return destination;
}

export function attackerFixtureUrl(origins: FixtureOrigins): URL {
  const destination = fixtureUrl(origins.attackerPort, "/attacker.html");
  destination.searchParams.set("targetOrigin", origins.applicationOrigin);
  return destination;
}
