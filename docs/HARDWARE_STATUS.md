# Physical hardware validation status

No physical hardware was queried in Work Order 01. OS candidate inventory does not identify a specific model. Protocol statuses below are project validation states, not claims about manufacturer software.

| ALIENTEK C2 Pro | Status | Evidence |
| --- | --- | --- |
| Discovery | PARTIAL | Generic USB inventory method; no verified VID/PID |
| Telemetry | UNVERIFIED | No captured frames or parser fixtures |
| PC control | BLOCKED / NOT VERIFIED | Driver write methods raise typed error |
| PD capture | UNVERIFIED | No traffic fixtures |
| PD trigger | BLOCKED / NOT VERIFIED | No verified command |
| Voltage/current/power limits | UNKNOWN | No project-verified source |

| ZKETECH EBD-A20H | Status | Evidence |
| --- | --- | --- |
| Discovery | PARTIAL | Generic COM port listing; no verified protocol identification |
| Telemetry | UNVERIFIED | No captured frames or parser fixtures |
| CC/CP control | BLOCKED / NOT VERIFIED | Driver write methods raise typed error |
| Stop | BLOCKED / NOT VERIFIED | Stop frame and state readback unverified |
| Voltage/current/power limits | UNKNOWN | No project-verified source |

Next validation needs model-specific descriptors, captured read-only traffic, official software behavior, command/response fixtures, and physical limit sources. Observed traffic alone does not elevate a protocol to KNOWN.
