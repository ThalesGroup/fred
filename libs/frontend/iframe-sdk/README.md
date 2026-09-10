# `@fred/iframe-sdk`

Framework-independent browser client for applications hosted by FRED in an iframe. The package
uses the existing protocol `"1"`; it does not receive FRED credentials or authorization state.
This development archive is not a registry publication or an instruction for FRED or an external
application to adopt a local workspace dependency.

```ts
import { createFredApplicationClient } from "@fred/iframe-sdk";

const fred = createFredApplicationClient({
  hostOrigin: "https://fred.example",
  applicationId: "example",
});
const context = await fred.connect();

const unsubscribe = fred.onRoute(({ subPath }) => renderRoute(subPath));
fred.navigate("reports/42");
fred.openChat();

const response = await fred.request("items", {
  headers: { accept: "application/json" },
});
if (response.ok) console.log(await response.json());

unsubscribe();
fred.dispose();
```

Low-level protocol types, constants, parsers, request limits, protected-header checks, and relative
path validation are available from `@fred/iframe-sdk/protocol`. Undocumented deep imports are not
public API.

## Lifecycle and security boundary

`hostOrigin` must be an absolute HTTP(S) origin and `applicationId` must match the initial FRED
context. The client accepts messages only from that exact origin and `window.parent`. It announces
readiness immediately, retries every 500 ms, and uses a 10-second connection deadline by default.
Every accepted route event is delivered once to each current subscriber, even when its `subPath`
was seen before.

FRED remains responsible for application/team authorization, route and chat destinations,
protected-header enforcement, bearer injection, token refresh, proxying, host concurrency, and
frame/team teardown. Applications never receive bearer tokens, Keycloak state, upstream addresses,
or backend models.

## Requests

Requests support `GET`, `HEAD`, `POST`, `PUT`, `PATCH`, and `DELETE`, at most 32 ordinary string
headers, a string-or-null body, 16 pending requests, and a 30-second local deadline by default.
HTTP errors resolve as inspectable `Response` objects. Host transport failures reject with a generic
SDK error. Caller abort and timeout release local state only; protocol `"1"` has no remote cancel
message. Unknown, duplicate, canceled, timed-out, disposed, and late replies are ignored by request
ID. Mutations are never retried by the SDK.

The transport is buffered text/JSON, not complete Fetch equivalence. Binary or multipart bodies,
streaming responses, SSE, opaque/`null` origins, theme/live-locale extensions, and detailed host
transport errors are unsupported.

## Archive verification

From `libs/frontend`, provisioning is the only network-enabled consumer phase:

```sh
npm run consumer:provision:iframe-sdk
npm run browser:install
```

The following validation commands require the prepared cache, staged consumer, and browser. They
install the actual tarball in npm offline mode, type-check and build outside the FRED checkout, and
then run browser smoke without dependency installation or browser bootstrapping:

```sh
npm run pack:check:iframe-sdk
npm run test:consumer:iframe-sdk
npm run test:browser
```

Missing cached packages or Chromium fail with the relevant provisioning command. The consumer
lockfile pins its tooling; it does not resolve from FRED's installed dependency tree.
