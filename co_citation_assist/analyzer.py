import logging
from collections import Counter, defaultdict
from typing import List, Set, Dict, Tuple, Optional
from pathlib import Path
import datetime
import time

from .apis.base import CitationAPI
from .ris_parser import extract_dois_from_ris

logger = logging.getLogger(__name__)

# Type alias for clarity
Doi = str
# Define structure for summary data
SummaryRecord = Dict[str, any] # E.g., {'doi': ..., 'references_found': ..., 'citations_found': ..., 'api': ..., 'timestamp': ...}
# Define structure for detailed results (list of relationships)
ResultRecord = Dict[str, Doi] # E.g., {'novel_doi': ..., 'initial_doi': ...}
# Define structure for raw fetched data per initial DOI
RawDataRecord = Dict[str, Optional[List[Doi]]] # E.g. {'references': [...], 'citations': [...]}

class CocitationAnalyzer:
    def __init__(self, api_client: CitationAPI, initial_dois: Set[Doi]):
        """
        Initializes the analyzer with an API client and the initial set of DOIs.

        Args:
            api_client: An instance of a class implementing CitationAPI.
            initial_dois: A set of DOIs extracted from the input RIS file.
        """
        if not isinstance(initial_dois, set):
            raise TypeError("initial_dois must be a set")
        self.api_client = api_client
        self.initial_dois = initial_dois
        logger.info(f"Analyzer initialized with {len(initial_dois)} initial DOIs.")

    def _fetch_data_for_doi(self, doi: Doi, fetch_references: bool, fetch_citations: bool) -> Tuple[Optional[List[Doi]], Optional[List[Doi]]]:
        """Fetches references and/or citations for a single DOI using the API client."""
        references = None
        citations = None
        # Use a generic API name for now, could be enhanced later if multiple APIs are used
        api_name = type(self.api_client).__name__ 
        try:
            if fetch_references:
                logger.debug(f"Fetching references for {doi} using {api_name}")
                references = self.api_client.get_references(doi)
                # Add a small delay *after* potential successful calls
                if references is not None:
                    time.sleep(0.1) 
            if fetch_citations:
                logger.debug(f"Fetching citations for {doi} using {api_name}")
                citations = self.api_client.get_citations(doi)
                # Add a small delay *after* potential successful calls
                if citations is not None:
                    time.sleep(0.1) 
        except Exception as e:
            logger.error(f"Error fetching data for DOI {doi} using {api_name}: {e}")
        # Return the actual lists (or None if error/not fetched)
        return references, citations

    def run_analysis(self, min_references_n: int, min_citations_m: int) -> Tuple[List[SummaryRecord], List[ResultRecord], List[ResultRecord], Dict[Doi, RawDataRecord]]:
        """
        Performs backward and forward co-citation analysis in a single pass.

        Args:
            min_references_n: The minimum number (N) of initial articles that must reference a DOI for backward analysis.
            min_citations_m: The minimum number (M) of initial articles that must be cited by a DOI for forward analysis.

        Returns:
            A tuple containing:
            - summary_data: List of dictionaries, one for each initial DOI processed.
            - backward_results: List of dictionaries detailing novel backward papers and the initial DOIs referencing them.
            - forward_results: List of dictionaries detailing novel forward papers and the initial DOIs they cite.
            - raw_data: Dictionary mapping each initial DOI to its fetched references and citations.
        """
        do_backward = min_references_n > 0
        do_forward = min_citations_m > 0

        if not do_backward and not do_forward:
            logger.warning("Both N and M are non-positive. No analysis performed.")
            return [], [], [], {}

        summary_data: List[SummaryRecord] = []
        all_references: Dict[Doi, List[Doi]] = defaultdict(list)
        all_citations: Dict[Doi, List[Doi]] = defaultdict(list)
        raw_data: Dict[Doi, RawDataRecord] = {}
        
        processed_count = 0
        total_initial = len(self.initial_dois)
        api_name = type(self.api_client).__name__

        logger.info(f"Starting analysis pass (N={min_references_n}, M={min_citations_m})...")

        for initial_doi in self.initial_dois:
            processed_count += 1
            logger.info(f"Processing ({processed_count}/{total_initial}): {initial_doi}")
            
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            fetched_references, fetched_citations = self._fetch_data_for_doi(
                initial_doi, 
                fetch_references=do_backward, 
                fetch_citations=do_forward
            )

            # Store the raw fetched data (even if None)
            raw_data[initial_doi] = {
                'references': fetched_references,
                'citations': fetched_citations
            }

            ref_count = len(fetched_references) if fetched_references is not None else 0
            cite_count = len(fetched_citations) if fetched_citations is not None else 0

            # Add to summary
            summary_data.append({
                'doi': initial_doi,
                'references_found': ref_count,
                'citations_found': cite_count,
                'api': api_name,
                'retrieval_timestamp': timestamp
            })

            # Populate backward analysis data structures (using the fetched data)
            if do_backward and fetched_references is not None:
                unique_references = set(fetched_references)
                for ref_doi in unique_references:
                    if ref_doi not in self.initial_dois:
                        all_references[ref_doi].append(initial_doi)

            # Populate forward analysis data structures (using the fetched data)
            if do_forward and fetched_citations is not None:
                unique_citations = set(fetched_citations)
                for cite_doi in unique_citations:
                    if cite_doi not in self.initial_dois:
                         all_citations[cite_doi].append(initial_doi)

        # --- Post-processing ---

        # Backward Analysis Results Calculation
        backward_results: List[ResultRecord] = []
        if do_backward:
            logger.info(f"Calculating backward results (N={min_references_n})...")
            for referenced_doi, citing_initial_dois in all_references.items():
                if len(citing_initial_dois) >= min_references_n:
                    logger.debug(f"Backward novel paper: {referenced_doi} (referenced by {len(citing_initial_dois)} initial DOIs)")
                    for initial_doi in citing_initial_dois:
                        backward_results.append({
                            'novel_doi': referenced_doi,
                            'initial_citing_doi': initial_doi
                        })
            logger.info(f"Backward analysis complete. Found {len(set(r['novel_doi'] for r in backward_results))} unique novel papers meeting threshold N={min_references_n}.")


        # Forward Analysis Results Calculation
        forward_results: List[ResultRecord] = []
        if do_forward:
            logger.info(f"Calculating forward results (M={min_citations_m})...")
            for citing_doi, cited_initial_dois in all_citations.items():
                 if len(cited_initial_dois) >= min_citations_m:
                    logger.debug(f"Forward novel paper: {citing_doi} (cites {len(cited_initial_dois)} initial DOIs)")
                    for initial_doi in cited_initial_dois:
                        forward_results.append({
                            'novel_doi': citing_doi,
                            'initial_cited_doi': initial_doi
                        })
            logger.info(f"Forward analysis complete. Found {len(set(r['novel_doi'] for r in forward_results))} unique novel papers meeting threshold M={min_citations_m}.")

        logger.info("Analysis pass complete.")
        # Return all collected data
        return summary_data, backward_results, forward_results, raw_data 