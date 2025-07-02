import logging
from typing import List, Set, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

from .base import CitationAPI
from .openalex import OpenAlexAPI  
from .semantic_scholar import SemanticScholarAPI

logger = logging.getLogger(__name__)

class CompositeAPI(CitationAPI):
    """
    Composite API that combines results from multiple citation APIs.
    
    Fetches data from both OpenAlex and Semantic Scholar APIs and merges
    the results to provide the most comprehensive citation data possible.
    """
    
    def __init__(self):
        """Initialize the composite API with both underlying APIs."""
        self.openalex = OpenAlexAPI()
        self.semantic_scholar = SemanticScholarAPI()
        logger.info("Initialized Composite API with OpenAlex and Semantic Scholar")
    
    def _fetch_from_api(self, api: CitationAPI, api_name: str, identifier: str, method: str) -> Tuple[str, List[str]]:
        """
        Fetch data from a specific API with error handling.
        
        Args:
            api: The API instance to use
            api_name: Name of the API for logging
            identifier: DOI to fetch data for
            method: 'references' or 'citations'
            
        Returns:
            Tuple of (api_name, list_of_dois)
        """
        try:
            start_time = time.time()
            if method == 'references':
                results = api.get_references(identifier)
            else:  # citations
                results = api.get_citations(identifier)
            
            elapsed = time.time() - start_time
            logger.debug(f"{api_name} returned {len(results)} {method} for {identifier} in {elapsed:.2f}s")
            return api_name, results
            
        except Exception as e:
            logger.error(f"[{api_name}] Error fetching {method} for {identifier}: {e}")
            return api_name, []
    
    def _merge_results(self, openalex_results: List[str], semantic_scholar_results: List[str], 
                      identifier: str, data_type: str) -> List[str]:
        """
        Merge results from multiple APIs, removing duplicates and logging statistics.
        
        Args:
            openalex_results: DOIs from OpenAlex
            semantic_scholar_results: DOIs from Semantic Scholar  
            identifier: Original DOI being processed
            data_type: 'references' or 'citations' for logging
            
        Returns:
            Combined list of unique DOIs
        """
        # Convert to sets for deduplication
        openalex_set = set(openalex_results) if openalex_results else set()
        semantic_scholar_set = set(semantic_scholar_results) if semantic_scholar_results else set()
        
        # Calculate overlaps and unique contributions
        overlap = openalex_set & semantic_scholar_set
        openalex_unique = openalex_set - semantic_scholar_set
        semantic_scholar_unique = semantic_scholar_set - openalex_set
        
        # Merge all results
        merged = openalex_set | semantic_scholar_set
        
        # Log detailed statistics
        logger.info(
            f"Merged {data_type} for {identifier}: "
            f"OpenAlex={len(openalex_set)}, "
            f"SemanticScholar={len(semantic_scholar_set)}, "
            f"Overlap={len(overlap)}, "
            f"OpenAlex_unique={len(openalex_unique)}, "
            f"SemanticScholar_unique={len(semantic_scholar_unique)}, "
            f"Total_unique={len(merged)}"
        )
        
        return list(merged)
    
    def get_references(self, identifier: str) -> List[str]:
        """
        Fetch references from both APIs and merge results.
        
        Args:
            identifier: A DOI string
            
        Returns:
            A merged list of unique DOIs referenced by the given identifier
        """
        logger.debug(f"Fetching references from both APIs for DOI: {identifier}")
        
        # Fetch from both APIs concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(self._fetch_from_api, self.openalex, "OpenAlex", identifier, "references"),
                executor.submit(self._fetch_from_api, self.semantic_scholar, "SemanticScholar", identifier, "references")
            }
            
            results = {}
            for future in as_completed(futures):
                api_name, dois = future.result()
                results[api_name] = dois
        
        # Merge results
        openalex_results = results.get("OpenAlex", [])
        semantic_scholar_results = results.get("SemanticScholar", [])
        
        return self._merge_results(openalex_results, semantic_scholar_results, identifier, "references")
    
    def get_citations(self, identifier: str) -> List[str]:
        """
        Fetch citations from both APIs and merge results.
        
        Args:
            identifier: A DOI string
            
        Returns:
            A merged list of unique DOIs citing the given identifier
        """
        logger.debug(f"Fetching citations from both APIs for DOI: {identifier}")
        
        # Fetch from both APIs concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(self._fetch_from_api, self.openalex, "OpenAlex", identifier, "citations"),
                executor.submit(self._fetch_from_api, self.semantic_scholar, "SemanticScholar", identifier, "citations")
            }
            
            results = {}
            for future in as_completed(futures):
                api_name, dois = future.result()
                results[api_name] = dois
        
        # Merge results
        openalex_results = results.get("OpenAlex", [])
        semantic_scholar_results = results.get("SemanticScholar", [])
        
        return self._merge_results(openalex_results, semantic_scholar_results, identifier, "citations")
    
    def get_references_with_stats(self, identifier: str) -> Tuple[List[str], Dict[str, int]]:
        """
        Fetch references from both APIs and return results with detailed statistics.
        
        Args:
            identifier: A DOI string
            
        Returns:
            Tuple of (merged_dois, statistics_dict)
        """
        logger.debug(f"Fetching references with stats from both APIs for DOI: {identifier}")
        
        # Fetch from both APIs concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(self._fetch_from_api, self.openalex, "OpenAlex", identifier, "references"),
                executor.submit(self._fetch_from_api, self.semantic_scholar, "SemanticScholar", identifier, "references")
            }
            
            results = {}
            for future in as_completed(futures):
                api_name, dois = future.result()
                results[api_name] = dois
        
        # Get individual results
        openalex_results = results.get("OpenAlex", [])
        semantic_scholar_results = results.get("SemanticScholar", [])
        
        # Convert to sets for statistics calculation
        openalex_set = set(openalex_results) if openalex_results else set()
        semantic_scholar_set = set(semantic_scholar_results) if semantic_scholar_results else set()
        
        # Calculate statistics
        overlap = openalex_set & semantic_scholar_set
        openalex_unique = openalex_set - semantic_scholar_set
        semantic_scholar_unique = semantic_scholar_set - openalex_set
        merged = openalex_set | semantic_scholar_set
        
        stats = {
            'OpenAlex': len(openalex_set),
            'SemanticScholar': len(semantic_scholar_set),
            'Overlap': len(overlap),
            'OpenAlex_unique': len(openalex_unique),
            'SemanticScholar_unique': len(semantic_scholar_unique),
            'Total_unique': len(merged)
        }
        
        # Log detailed statistics
        logger.info(
            f"References stats for {identifier}: "
            f"OpenAlex={stats['OpenAlex']}, "
            f"SemanticScholar={stats['SemanticScholar']}, "
            f"Overlap={stats['Overlap']}, "
            f"OpenAlex_unique={stats['OpenAlex_unique']}, "
            f"SemanticScholar_unique={stats['SemanticScholar_unique']}, "
            f"Total_unique={stats['Total_unique']}"
        )
        
        return list(merged), stats
    
    def get_citations_with_stats(self, identifier: str) -> Tuple[List[str], Dict[str, int]]:
        """
        Fetch citations from both APIs and return results with detailed statistics.
        
        Args:
            identifier: A DOI string
            
        Returns:
            Tuple of (merged_dois, statistics_dict)
        """
        logger.debug(f"Fetching citations with stats from both APIs for DOI: {identifier}")
        
        # Fetch from both APIs concurrently
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = {
                executor.submit(self._fetch_from_api, self.openalex, "OpenAlex", identifier, "citations"),
                executor.submit(self._fetch_from_api, self.semantic_scholar, "SemanticScholar", identifier, "citations")
            }
            
            results = {}
            for future in as_completed(futures):
                api_name, dois = future.result()
                results[api_name] = dois
        
        # Get individual results
        openalex_results = results.get("OpenAlex", [])
        semantic_scholar_results = results.get("SemanticScholar", [])
        
        # Convert to sets for statistics calculation
        openalex_set = set(openalex_results) if openalex_results else set()
        semantic_scholar_set = set(semantic_scholar_results) if semantic_scholar_results else set()
        
        # Calculate statistics
        overlap = openalex_set & semantic_scholar_set
        openalex_unique = openalex_set - semantic_scholar_set
        semantic_scholar_unique = semantic_scholar_set - openalex_set
        merged = openalex_set | semantic_scholar_set
        
        stats = {
            'OpenAlex': len(openalex_set),
            'SemanticScholar': len(semantic_scholar_set),
            'Overlap': len(overlap),
            'OpenAlex_unique': len(openalex_unique),
            'SemanticScholar_unique': len(semantic_scholar_unique),
            'Total_unique': len(merged)
        }
        
        # Log detailed statistics
        logger.info(
            f"Citations stats for {identifier}: "
            f"OpenAlex={stats['OpenAlex']}, "
            f"SemanticScholar={stats['SemanticScholar']}, "
            f"Overlap={stats['Overlap']}, "
            f"OpenAlex_unique={stats['OpenAlex_unique']}, "
            f"SemanticScholar_unique={stats['SemanticScholar_unique']}, "
            f"Total_unique={stats['Total_unique']}"
        )
        
        return list(merged), stats