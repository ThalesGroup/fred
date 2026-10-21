## ADDED Requirements

### Requirement: Hosted application binary request bodies

FRED SHALL let an admitted hosted application send binary content to its application service and receive binary content from it through the host's request bridge, with the exact bytes, without the application handling credentials or upstream addresses. The host MUST announce this capability to the frame; the bridge MUST keep protocol `"1"`, its existing admission, authentication, routing, header protection and concurrency limits, and its text behavior for any participant that does not use the capability.

#### Scenario: Application uploads a file

- **WHEN** an admitted application sends a request whose body is a file or other binary object, with its own content type
- **THEN** its application service receives exactly those bytes and that content type, with the user's credentials added by the host

#### Scenario: Application uploads a multipart form

- **WHEN** an admitted application sends a request whose body is a form holding fields and files
- **THEN** its application service receives a multipart request whose fields, file names and file bytes are those of the form

#### Scenario: Application downloads a binary response

- **WHEN** an admitted application requests a resource its service answers with binary content, through an SDK and a host that both support binary bodies
- **THEN** the response the application receives has the service's status, headers and exact bytes, readable as binary, text or JSON

#### Scenario: Text responses are unchanged

- **WHEN** an application service answers with text or JSON through a host and an SDK that both support binary bodies
- **THEN** the application reads the same text or JSON as through the text transport

#### Scenario: Host announces the capability

- **WHEN** a host that supports binary bodies connects an application frame
- **THEN** its context message announces that capability, and a host that does not support it announces nothing

#### Scenario: Newer application, older host

- **WHEN** an application using an SDK that supports binary bodies sends a binary request body to a host that does not announce the capability
- **THEN** the SDK refuses the request immediately with an explicit unsupported-capability error, sends nothing to the host, and still exchanges text requests and responses as before

#### Scenario: Older application, newer host

- **WHEN** an application using an SDK without binary support connects to a host that supports binary bodies
- **THEN** its requests and responses keep the text transport, and the announcement does not disturb its connection

#### Scenario: Malformed binary messages are ignored

- **WHEN** a frame sends a request whose body is neither text, a binary object nor empty, or asks for a response type the host does not know
- **THEN** the host ignores the message and sends no request upstream

#### Scenario: Binary transfer works in a real browser

- **WHEN** an admitted application uploads a known file and downloads a known binary response inside FRED's production application host iframe in a real browser
- **THEN** the service receives the uploaded bytes and the application receives the downloaded bytes unchanged
