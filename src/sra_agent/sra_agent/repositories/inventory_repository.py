from typing import Any


class InventoryRepository:
    """PostgreSQL access for inventory-related skills.

    Inventory is derived from physical products stored in occupied ROS2-managed
    storage slots. Legacy aggregate inventory tables are intentionally ignored.
    """

    def __init__(self, connection):
        self._connection = connection

    def get_total_available(self) -> int:
        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM available_stored_parts
                """
            )
            value = cursor.fetchone()[0]
        self._connection.rollback()
        return int(value)

    def get_available_by_config(self, config_code: str) -> dict[str, Any] | None:
        try:
            bottom_cover, top_cover, fuse_configuration = config_code.split("-", 2)
        except ValueError:
            return None

        if bottom_cover not in {"blue", "red", "black"}:
            return None
        if top_cover not in {"blue", "red"}:
            return None
        if fuse_configuration not in {"none", "upper", "lower", "both"}:
            return None

        with self._connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM available_stored_parts
                WHERE bottom_cover = %s
                  AND top_cover = %s
                  AND fuse_configuration = %s
                """,
                (bottom_cover, top_cover, fuse_configuration),
            )
            available = int(cursor.fetchone()[0])
        self._connection.rollback()

        return {
            "config_code": config_code,
            "bottom_cover": bottom_cover,
            "top_cover": top_cover,
            "fuse_configuration": fuse_configuration,
            "available": available,
        }
