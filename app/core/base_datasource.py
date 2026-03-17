"""Abstract base class for all data sources.

To add a new datasource:
1. Create a file in app/datasources/ (e.g. mongodb.py)
2. Subclass BaseDataSource and implement all abstract methods
3. Register it in the datasource registry or engine config
"""

from abc import ABC, abstractmethod


class BaseDataSource(ABC):
    """Contract every data source connector must follow."""

    @property
    @abstractmethod
    def source_type(self) -> str:
        """Unique identifier, e.g. 'pocketbase', 'sqlserver'."""

    @abstractmethod
    def fetch_records(
        self,
        collection: str,
        filter_str: str = "",
        sort: str = "",
        limit: int = 0,
    ) -> list[dict]:
        """Fetch records from the data source.

        Args:
            collection: Table/collection name
            filter_str: Filter expression
            sort: Sort expression
            limit: Max records to return (0 = all)

        Returns:
            List of record dicts.
        """
