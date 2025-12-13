package fredlab.dev.samples.a2a.model;

import com.fasterxml.jackson.annotation.JsonInclude;

import java.util.List;
import java.util.Map;

@JsonInclude(JsonInclude.Include.NON_NULL)
public final class A2aTypes {

  // ---- Agent Card ----
  public record AgentCard(
      String protocolVersion,
      String name,
      String description,
      String url,
      String preferredTransport,
      Capabilities capabilities,
      List<String> defaultInputModes,
      List<String> defaultOutputModes,
      List<Skill> skills,
      Boolean supportsAuthenticatedExtendedCard
  ) {}

  public record Capabilities(Boolean streaming, Boolean pushNotifications, Boolean stateTransitionHistory) {}

  public record Skill(
      String id,
      String name,
      String description,
      List<String> tags,
      List<String> examples,
      List<String> inputModes,
      List<String> outputModes
  ) {}

  // ---- Message / Task ----
  public record Message(String role, List<Part> parts, String messageId, String taskId, String contextId) {}

  public sealed interface Part permits TextPart {}
  public record TextPart(String kind, String text) implements Part {}

  public record MessageSendParams(Message message, Map<String, Object> metadata) {}

  public record Task(
      String id,
      String contextId,
      TaskStatus status,
      List<Artifact> artifacts,
      List<Message> history,
      String kind,
      Map<String, Object> metadata
  ) {}

  public record TaskStatus(String state) {}

  public record Artifact(String artifactId, String name, List<Part> parts) {}
}
