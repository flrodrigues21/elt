from abc import ABC, abstractmethod
import pandas as pd


class BaseExtractor(ABC):
    @abstractmethod
    def extract(self, row: dict) -> pd.DataFrame:
        pass
