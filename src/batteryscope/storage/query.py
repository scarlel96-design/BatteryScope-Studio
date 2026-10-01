"""DuckDB readback belongs to a worker, never the QML thread."""

from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

import duckdb


class DuckDBWorker:
    def __init__(self) -> None:
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="batteryscope-duckdb")

    def summarize(self, raw_glob: Path) -> Future[dict[str, float | int]]:
        def query() -> dict[str, float | int]:
            start = perf_counter()
            connection = duckdb.connect(":memory:")
            try:
                row = connection.execute(
                    "SELECT count(*), avg(voltage_v), min(voltage_v), max(voltage_v), "
                    "avg(current_a), min(current_a), max(current_a), sum(power_w) FROM read_parquet(?)",
                    [str(raw_glob)],
                ).fetchone()
            finally:
                connection.close()
            return {"rows": row[0], "avg_voltage_v": row[1], "min_voltage_v": row[2],
                    "max_voltage_v": row[3], "avg_current_a": row[4], "min_current_a": row[5],
                    "max_current_a": row[6], "sum_power_w": row[7],
                    "duckdb_query_ms": (perf_counter() - start) * 1000}
        return self._pool.submit(query)

    def close(self) -> None:
        self._pool.shutdown(wait=True)
