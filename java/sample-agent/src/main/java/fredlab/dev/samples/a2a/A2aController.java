package fredlab.dev.samples.a2a;

import fredlab.dev.samples.a2a.model.A2aTypes;
import fredlab.dev.samples.a2a.model.JsonRpc;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.*;   
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.UUID;

@RestController
public class A2aController {

  /**
   * Public A2A Agent Card (well-known URI).
   * Recommended location in the A2A spec: /.well-known/agent-card.json. :contentReference[oaicite:2]{index=2}
   *
   * We set supportsAuthenticatedExtendedCard=false so your Python client will not attempt
   * to fetch an extended card.
   */
  @GetMapping(path = "/.well-known/agent-card.json", produces = MediaType.APPLICATION_JSON_VALUE)
  public A2aTypes.AgentCard agentCard() {
    return buildAgentCard();
  }

  /**
   * Backward-compat helper: some older clients used /.well-known/agent.json
   * (the SDK moved toward /.well-known/agent-card.json). :contentReference[oaicite:3]{index=3}
   */
  @GetMapping(path = "/.well-known/agent.json", produces = MediaType.APPLICATION_JSON_VALUE)
  public A2aTypes.AgentCard legacyAgentCard() {
    return buildAgentCard();
  }

  /**
   * JSON-RPC endpoint for A2A methods.
   * Your Python A2AClient typically uses the AgentCard.url for the RPC endpoint.
   */
  @PostMapping(path = "/", consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.APPLICATION_JSON_VALUE)
  public Mono<JsonRpc.Response> jsonRpc(@RequestBody JsonRpc.Request req) {
    if (req == null || req.method() == null) {
      return Mono.just(JsonRpc.Response.err(null, -32600, "Invalid Request"));
    }

    return switch (req.method()) {
      case "message/send" -> Mono.just(handleMessageSend(req));
      case "agent/getAuthenticatedExtendedCard" ->
          // We don't support an extended card in this sample.
          Mono.just(JsonRpc.Response.err(req.id(), -32007, "AuthenticatedExtendedCardNotConfiguredError"));
      default -> Mono.just(JsonRpc.Response.err(req.id(), -32601, "Method not found: " + req.method()));
    };
  }

  /**
   * Streaming endpoint for message/stream (SSE).
   * The A2A spec documents a streaming workflow where the server returns text/event-stream. :contentReference[oaicite:4]{index=4}
   */
  @PostMapping(path = "/message/stream", consumes = MediaType.APPLICATION_JSON_VALUE, produces = MediaType.TEXT_EVENT_STREAM_VALUE)
  public Flux<ServerSentEvent<Object>> messageStream(@RequestBody JsonRpc.Request req) {
    if (req == null || !"message/stream".equals(req.method())) {
      return Flux.just(ServerSentEvent.<Object>builder(Map.of("error", "Expected JSON-RPC method message/stream")).event("error").build());
    }

    // Build a task id/context id now to keep events consistent.
    String taskId = UUID.randomUUID().toString();
    String contextId = UUID.randomUUID().toString();

    // 1) working status
    var workingTask = new A2aTypes.Task(
        taskId,
        contextId,
        new A2aTypes.TaskStatus("working"),
        null,
        null,
        "task",
        Map.of()
    );

    // 2) completed with final artifact
    var completedTask = buildCompletedTask(taskId, contextId, extractUserText(req.params()));

    return Flux.concat(
        Flux.just(ServerSentEvent.<Object>builder(workingTask).event("task").build()),
        Flux.just(ServerSentEvent.<Object>builder(completedTask).event("task").build()).delayElements(Duration.ofMillis(400))
    );
  }

  // ------------------ internals ------------------

  private JsonRpc.Response handleMessageSend(JsonRpc.Request req) {
    String taskId = UUID.randomUUID().toString();
    String contextId = UUID.randomUUID().toString();

    var completedTask = buildCompletedTask(taskId, contextId, extractUserText(req.params()));
    return JsonRpc.Response.ok(req.id(), completedTask);
  }

  private A2aTypes.AgentCard buildAgentCard() {
    var skill = new A2aTypes.Skill(
        "fx.convert",
        "FX Convert (demo)",
        "Demo skill: converts a USD amount to INR using a fixed illustrative rate (not live market data).",
        List.of("finance", "demo"),
        List.of("how much is 10 USD in INR?"),
        List.of("text/plain"),
        List.of("text/plain")
    );

    return new A2aTypes.AgentCard(
        "0.3.0",
        "Java A2A Demo Agent",
        "Minimal A2A server in Java (Spring WebFlux). Implements message/send and message/stream.",
        "http://localhost:9999/",         // IMPORTANT: matches where you run it
        "JSONRPC",                        // Keep it simple: JSON-RPC over HTTP POST
        new A2aTypes.Capabilities(true, false, false),
        List.of("text/plain"),
        List.of("text/plain"),
        List.of(skill),
        false
    );
  }

  private A2aTypes.Task buildCompletedTask(String taskId, String contextId, String userText) {
    String answer = answerFor(userText);

    var artifact = new A2aTypes.Artifact(
        UUID.randomUUID().toString(),
        "answer",
        List.of(new A2aTypes.TextPart("text", answer))
    );

    var history = List.of(
        new A2aTypes.Message(
            "user",
            List.of(new A2aTypes.TextPart("text", userText)),
            UUID.randomUUID().toString(),
            taskId,
            contextId
        )
    );

    return new A2aTypes.Task(
        taskId,
        contextId,
        new A2aTypes.TaskStatus("completed"),
        List.of(artifact),
        history,
        "task",
        Map.of()
    );
  }

  @SuppressWarnings("unchecked")
  private String extractUserText(Object paramsObj) {
    // Expected shape (like your Python payload):
    // { "message": { "role":"user", "parts":[{"kind":"text","text":"..."}], "messageId":"..." }, "metadata":{...}}
    if (!(paramsObj instanceof Map<?, ?> params)) return "";
    Object messageObj = params.get("message");
    if (!(messageObj instanceof Map<?, ?> msg)) return "";
    Object partsObj = msg.get("parts");
    if (!(partsObj instanceof List<?> parts) || parts.isEmpty()) return "";
    Object first = parts.get(0);
    if (!(first instanceof Map<?, ?> part)) return "";
    Object text = part.get("text");
    return text == null ? "" : text.toString();
  }

  private String answerFor(String userText) {
    // Intentionally deterministic for testing.
    // You can replace this with a real FX service later.
    if (userText == null) userText = "";
    String normalized = userText.toLowerCase();

    // Very small parser: looks for "<number> usd" and returns INR at a fixed demo rate.
    double rate = 83.0;
    double amount = extractFirstNumber(normalized, 10.0);
    double inr = amount * rate;

    if (normalized.contains("usd") && normalized.contains("inr")) {
      return String.format("Demo conversion (fixed rate %.2f): %.2f USD ≈ %.2f INR", rate, amount, inr);
    }
    return "Hello from Java A2A demo agent. Ask: 'how much is 10 USD in INR?'";
  }

  private double extractFirstNumber(String s, double fallback) {
    try {
      var m = java.util.regex.Pattern.compile("(\\d+(?:\\.\\d+)?)").matcher(s);
      if (m.find()) return Double.parseDouble(m.group(1));
    } catch (Exception ignored) {}
    return fallback;
  }
}
