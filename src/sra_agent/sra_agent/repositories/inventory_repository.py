from typing import Any


class InventoryRepository:
    """PostgreSQL access for inventory-related skills.

    SQL lives here rather than in the language model or skill-selection layer.
    The current implementation uses the existing aggregate inventory schema and
    can later be replaced by physical-part queries without changing the agent.
    """

    def __init__(self, connection):
        self._connection = connection

    def get_total_available(self) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COALESCE(SUM(i.quantity - COALESCE(r.reserved, 0)), 0)
                FROM inventory i
                LEFT JOIN (
                    SELECT config_id, SUM(quantity) AS reserved
                    FROM inventory_reservations
                    GROUP BY config_id
                ) r ON r.config_id = i.config_id
                """
            )
            value = cursor.fetchone()[0]
        self._connection.rollback()
        return int(value)

    def get_available_by_config(self, config_code: str) -> dict[str, Any] | None:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    c.config_code,
                    i.quantity - COALESCE(r.reserved, 0) AS available
                FROM configurations c
                JOIN inventory i ON i.config_id = c.id
                LEFT JOIN (
                    SELECT config_id, SUM(quantity) AS reserved
                    FROM inventory_reservations
                    GROUP BY config_id
                ) r ON r.config_id = c.id
                WHERE c.config_code = %s
                """,
                (config_code,),
            )
            row = cursor.fetchone()
        self._connection.rollback()
        if row is None:
            return None
        return {"config_code": row[0], "available": int(row[1])}
