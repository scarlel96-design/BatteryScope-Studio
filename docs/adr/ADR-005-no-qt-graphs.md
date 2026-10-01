# ADR-005: Exclude Qt Graphs from core

Status: Accepted. The core UI imports no Qt Graphs or Qt Charts. The future LatticePlot abstraction will use the Qt Quick scene graph under a separate design task. This keeps optional graph-module licensing and rendering choices outside the WO01 baseline.
