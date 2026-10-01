# ADR-001: Qt Quick and QML shell

Status: Accepted. The shell uses PySide6, Qt Quick, QML, and Qt Quick Controls. QML only calls a queued bridge; device and storage work stays in workers. This permits a cross-platform shell while retaining a replaceable backend. A QWidget-only shell was rejected because the planned Lattice UI is scene-graph oriented.
