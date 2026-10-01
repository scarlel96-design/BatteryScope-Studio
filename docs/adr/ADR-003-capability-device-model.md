# ADR-003: Capability-based device model

Status: Accepted. Plugins declare capability names and verified limits. Application logic checks capabilities instead of driver model names. The registry checks manifest/driver agreement and emergency-stop structure. A feature declaration with unknown limits may be registered for manual discovery, but deterministic auto load authorization still fails.
