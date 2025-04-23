# Base API definition
from abc import ABC, abstractmethod
from typing import List

class CitationAPI(ABC):
    @abstractmethod
    def get_references(self, identifier: str) -> List[str]:
        """Fetch works referenced by the given identifier (e.g., DOI).
        
        Args:
            identifier: Typically a DOI string
            
        Returns:
            A list of DOIs referenced by the identifier
        """
        pass

    @abstractmethod
    def get_citations(self, identifier: str) -> List[str]:
        """Fetch works citing the given identifier (e.g., DOI).
        
        Args:
            identifier: Typically a DOI string
            
        Returns:
            A list of DOIs citing the identifier
        """
        pass 