# ADR-004: Deterministic safety boundary

Status: Accepted. `SafetyEngine` requires physical-document provenance for physical limits and denies missing limits. Virtual fixture limits are separate. Emergency load-off is requested before persistence; stop state has requested, acknowledged, verified-off, and failed phases. AI/search/planning cannot override this boundary. The physical stop protocol remains blocked until verified.
