"""PocketBase DataSource — standalone plugin.

Fetches records from any PocketBase collection.
Uses the shared pb_client for authenticated HTTP calls.
"""

import logging

from app.core.base_datasource import BaseDataSource
from app.db.pb_client import pb_get_full_list, pb_list

logger = logging.getLogger(__name__)


class PocketBaseSource(BaseDataSource):

    @property
    def source_type(self) -> str:
        return "pocketbase"

    def fetch_records(
        self,
        collection: str,
        filter_str: str = "",
        sort: str = "",
        expand: str = "",
        limit: int = 0,
    ) -> list[dict]:
        """Fetch records from a PocketBase collection.

        Args:
            limit: Max records (0 = fetch all pages).
        """
        try:
            if limit > 0:
                data = pb_list(
                    collection,
                    page=1,
                    per_page=limit,
                    filter_str=filter_str,
                    sort=sort,
                    expand=expand,
                )
                return data.get("items", [])
            return pb_get_full_list(
                collection,
                filter_str=filter_str,
                sort=sort,
                expand=expand,
            )
        except Exception as exc:
            logger.error(
                "PocketBase fetch failed for '%s': %s",
                collection,
                exc,
            )
            return []
