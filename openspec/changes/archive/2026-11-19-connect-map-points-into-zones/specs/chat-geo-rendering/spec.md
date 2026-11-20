## ADDED Requirements

### Requirement: Optional zone from selected map points

The shared map tool SHALL render selected GPS coordinates as individual point markers by default. When an agent explicitly requests a zone, it SHALL additionally connect at least three distinct supplied coordinates in their given order and close the boundary into one polygon. It SHALL keep the individual markers visible. An invalid zone request SHALL return a correctable tool error without a geographic UI part. The tool's agent-facing guidance SHALL describe when to request a zone and how to order its points.

#### Scenario: Default point map

- **WHEN** an agent submits GPS points without requesting a zone
- **THEN** the result contains the point markers and no zone polygon

#### Scenario: Requested zone

- **WHEN** an agent submits at least three distinct GPS points in boundary order and requests a zone
- **THEN** the result contains each point marker and one closed polygon following that order

#### Scenario: Insufficient zone coordinates

- **WHEN** an agent requests a zone with fewer than three distinct GPS coordinates
- **THEN** the tool returns an error explaining the minimum and emits no geographic UI part
