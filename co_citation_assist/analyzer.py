import logging
from collections import Counter, defaultdict
from typing import List, Set, Dict, Tuple, Optional
from pathlib import Path
import datetime
import time

from .apis.base import CitationAPI
from .ris_parser import extract_dois_from_ris, extract_identifiers_from_ris

logger = logging.getLogger(__name__)

# Type alias for clarity
Doi = str
Identifier = str  # Can be either DOI or MAG ID
# Define structure for summary data
SummaryRecord = Dict[str, any] # E.g., {'doi': ..., 'references_found': ..., 'citations_found': ..., 'api': ..., 'timestamp': ..., 'api_contributions': ...}
# Define structure for detailed results (list of relationships)
ResultRecord = Dict[str, Doi] # E.g., {'novel_doi': ..., 'initial_doi': ...}
# Define structure for raw fetched data per initial DOI - enhanced for composite API
RawDataRecord = Dict[str, Optional[List[Doi]]] # E.g. {'references': [...], 'citations': [...]}
# Define structure for API contribution data
APIContributions = Dict[str, Dict[str, int]] # E.g., {'references': {'OpenAlex': 33, 'SemanticScholar': 28, 'Overlap': 27, 'OpenAlex_unique': 6, 'SemanticScholar_unique': 1, 'Total_unique': 34}}

class CocitationAnalyzer:
    def __init__(self, api_client: CitationAPI, initial_dois: Set[Doi], initial_mag_ids: Set[Identifier] = None):
        """
        Initializes the analyzer with an API client and the initial set of DOIs and MAG IDs.

        Args:
            api_client: An instance of a class implementing CitationAPI.
            initial_dois: A set of DOIs extracted from the input RIS file.
            initial_mag_ids: A set of MAG IDs extracted from the input RIS file.
        """
        if not isinstance(initial_dois, set):
            raise TypeError("initial_dois must be a set")
        if initial_mag_ids is not None and not isinstance(initial_mag_ids, set):
            raise TypeError("initial_mag_ids must be a set")
        
        self.api_client = api_client
        self.initial_dois = initial_dois
        self.initial_mag_ids = initial_mag_ids or set()
        
        # Create combined set of all identifiers for processing
        self.all_identifiers = initial_dois | self.initial_mag_ids
        
        logger.info(f"Analyzer initialized with {len(initial_dois)} initial DOIs and {len(self.initial_mag_ids)} initial MAG IDs.")

    def _fetch_data_for_identifier(self, identifier: Identifier, fetch_references: bool, fetch_citations: bool) -> Tuple[Optional[List[Doi]], Optional[List[Doi]], Optional[APIContributions]]:
        """Fetches references and/or citations for a single identifier (DOI or MAG ID) using the API client."""
        references = None
        citations = None
        api_contributions = None
        # Use a generic API name for now, could be enhanced later if multiple APIs are used
        api_name = type(self.api_client).__name__ 
        id_type = "MAG ID" if identifier.isdigit() else "DOI"
        try:
            if fetch_references:
                logger.debug(f"Fetching references for {id_type} {identifier} using {api_name}")
                if hasattr(self.api_client, 'get_references_with_stats'):
                    references, ref_stats = self.api_client.get_references_with_stats(identifier)
                    api_contributions = {'references': ref_stats}
                else:
                    references = self.api_client.get_references(identifier)
                # Add a small delay *after* potential successful calls
                if references is not None:
                    time.sleep(0.1) 
            if fetch_citations:
                logger.debug(f"Fetching citations for {id_type} {identifier} using {api_name}")
                if hasattr(self.api_client, 'get_citations_with_stats'):
                    citations, cite_stats = self.api_client.get_citations_with_stats(identifier)
                    if api_contributions is None:
                        api_contributions = {}
                    api_contributions['citations'] = cite_stats
                else:
                    citations = self.api_client.get_citations(identifier)
                # Add a small delay *after* potential successful calls
                if citations is not None:
                    time.sleep(0.1) 
        except Exception as e:
            logger.error(f"Error fetching data for {id_type} {identifier} using {api_name}: {e}")
        # Return the actual lists (or None if error/not fetched) and contribution stats
        return references, citations, api_contributions

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
        raw_data: Dict[Identifier, RawDataRecord] = {}
        
        processed_count = 0
        total_initial = len(self.all_identifiers)
        api_name = type(self.api_client).__name__

        logger.info(f"Starting analysis pass (N={min_references_n}, M={min_citations_m})...")

        for initial_identifier in self.all_identifiers:
            processed_count += 1
            id_type = "MAG ID" if initial_identifier.isdigit() else "DOI"
            logger.info(f"Processing ({processed_count}/{total_initial}) {id_type}: {initial_identifier}")
            
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            fetched_references, fetched_citations, api_contributions = self._fetch_data_for_identifier(
                initial_identifier, 
                fetch_references=do_backward, 
                fetch_citations=do_forward
            )

            # Store the raw fetched data (even if None)
            raw_data[initial_identifier] = {
                'references': fetched_references,
                'citations': fetched_citations
            }

            ref_count = len(fetched_references) if fetched_references is not None else 0
            cite_count = len(fetched_citations) if fetched_citations is not None else 0

            # Add to summary
            summary_record = {
                'doi': initial_identifier,  # Keep 'doi' field name for compatibility, but it may contain MAG ID
                'references_found': ref_count,
                'citations_found': cite_count,
                'api': api_name,
                'retrieval_timestamp': timestamp
            }
            
            # Add API contribution statistics if available
            if api_contributions:
                if 'references' in api_contributions:
                    ref_stats = api_contributions['references']
                    summary_record.update({
                        'references_OpenAlex': ref_stats.get('OpenAlex', 0),
                        'references_SemanticScholar': ref_stats.get('SemanticScholar', 0),
                        'references_Overlap': ref_stats.get('Overlap', 0),
                        'references_OpenAlex_unique': ref_stats.get('OpenAlex_unique', 0),
                        'references_SemanticScholar_unique': ref_stats.get('SemanticScholar_unique', 0),
                        'references_Total_unique': ref_stats.get('Total_unique', 0)
                    })
                if 'citations' in api_contributions:
                    cite_stats = api_contributions['citations']
                    summary_record.update({
                        'citations_OpenAlex': cite_stats.get('OpenAlex', 0),
                        'citations_SemanticScholar': cite_stats.get('SemanticScholar', 0),
                        'citations_Overlap': cite_stats.get('Overlap', 0),
                        'citations_OpenAlex_unique': cite_stats.get('OpenAlex_unique', 0),
                        'citations_SemanticScholar_unique': cite_stats.get('SemanticScholar_unique', 0),
                        'citations_Total_unique': cite_stats.get('Total_unique', 0)
                    })
            
            summary_data.append(summary_record)

            # Populate backward analysis data structures (using the fetched data)
            if do_backward and fetched_references is not None:
                unique_references = set(fetched_references)
                for ref_doi in unique_references:
                    if ref_doi not in self.all_identifiers:
                        all_references[ref_doi].append(initial_identifier)

            # Populate forward analysis data structures (using the fetched data)
            if do_forward and fetched_citations is not None:
                unique_citations = set(fetched_citations)
                for cite_doi in unique_citations:
                    if cite_doi not in self.all_identifiers:
                         all_citations[cite_doi].append(initial_identifier)

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

    def run_base_collection(self) -> Tuple[List[SummaryRecord], Dict[Identifier, RawDataRecord]]:
        """
        Collects references and citations for all initial identifiers without performing co-citation analysis.
        
        Returns:
            A tuple containing:
            - summary_data: List of dictionaries, one for each initial identifier processed.
            - raw_data: Dictionary mapping each initial identifier to its fetched references and citations.
        """
        summary_data: List[SummaryRecord] = []
        raw_data: Dict[Identifier, RawDataRecord] = {}
        
        processed_count = 0
        total_initial = len(self.all_identifiers)
        api_name = type(self.api_client).__name__

        logger.info("Starting base data collection (no co-citation analysis)...")

        for initial_identifier in self.all_identifiers:
            processed_count += 1
            id_type = "MAG ID" if initial_identifier.isdigit() else "DOI"
            logger.info(f"Processing ({processed_count}/{total_initial}): {initial_identifier}")
            
            timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
            
            fetched_references, fetched_citations, api_contributions = self._fetch_data_for_identifier(
                initial_identifier, 
                fetch_references=True, 
                fetch_citations=True
            )

            # Store the raw fetched data (even if None)
            raw_data[initial_identifier] = {
                'references': fetched_references,
                'citations': fetched_citations
            }

            ref_count = len(fetched_references) if fetched_references is not None else 0
            cite_count = len(fetched_citations) if fetched_citations is not None else 0

            # Add to summary
            summary_record = {
                'doi': initial_identifier,  # Keep 'doi' field name for compatibility, but it may contain MAG ID
                'references_found': ref_count,
                'citations_found': cite_count,
                'api': api_name,
                'retrieval_timestamp': timestamp
            }
            
            # Add API contribution statistics if available
            if api_contributions:
                if 'references' in api_contributions:
                    ref_stats = api_contributions['references']
                    summary_record.update({
                        'references_OpenAlex': ref_stats.get('OpenAlex', 0),
                        'references_SemanticScholar': ref_stats.get('SemanticScholar', 0),
                        'references_Overlap': ref_stats.get('Overlap', 0),
                        'references_OpenAlex_unique': ref_stats.get('OpenAlex_unique', 0),
                        'references_SemanticScholar_unique': ref_stats.get('SemanticScholar_unique', 0),
                        'references_Total_unique': ref_stats.get('Total_unique', 0)
                    })
                if 'citations' in api_contributions:
                    cite_stats = api_contributions['citations']
                    summary_record.update({
                        'citations_OpenAlex': cite_stats.get('OpenAlex', 0),
                        'citations_SemanticScholar': cite_stats.get('SemanticScholar', 0),
                        'citations_Overlap': cite_stats.get('Overlap', 0),
                        'citations_OpenAlex_unique': cite_stats.get('OpenAlex_unique', 0),
                        'citations_SemanticScholar_unique': cite_stats.get('SemanticScholar_unique', 0),
                        'citations_Total_unique': cite_stats.get('Total_unique', 0)
                    })
            
            summary_data.append(summary_record)

        logger.info("Base collection complete.")
        return summary_data, raw_data 