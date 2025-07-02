import logging
from typing import List
import time
import random

import pyalex
from pyalex import Works

from .base import CitationAPI
from ..utils import get_openalex_email

# Configure logging
logger = logging.getLogger(__name__)

class OpenAlexAPI(CitationAPI):
    """Implementation of CitationAPI using the OpenAlex service via pyalex library."""

    def __init__(self):
        """Initialize the OpenAlex API client."""
        # Set the email for the polite pool
        email = get_openalex_email()
        pyalex.config.email = email
        logger.info(f"Initialized OpenAlex API client with email: {email}")

    def get_references(self, identifier: str) -> List[str]:
        """
        Fetch DOIs of works referenced by the given identifier (DOI or MAG ID).
        
        Uses pyalex to fetch the outgoing citations (works that this paper references).
        
        Args:
            identifier: A DOI string or MAG ID string
            
        Returns:
            A list of DOIs referenced by the given identifier
        """
        # Clean DOI if it's a URL
        if identifier.startswith("https://doi.org/"):
            identifier = identifier[len("https://doi.org/"):]
            
        try:
            # Determine if this is a DOI or MAG ID and construct appropriate query
            if identifier.isdigit():
                # This is a MAG ID
                query_identifier = f"mag:{identifier}"
                logger.debug(f"Fetching work metadata for MAG ID: {identifier}")
            else:
                # This is a DOI
                query_identifier = f"doi:{identifier}"
                logger.debug(f"Fetching work metadata for DOI: {identifier}")
            
            work = Works()[query_identifier]
            
            if not work or "referenced_works" not in work or not work["referenced_works"]:
                id_type = "MAG ID" if identifier.isdigit() else "DOI"
                logger.warning(f"[OpenAlex] No referenced works found for {id_type}: {identifier}")
                return []
                
            # Get referenced works IDs
            ref_ids = work["referenced_works"]
            id_type = "MAG ID" if identifier.isdigit() else "DOI"
            logger.info(f"[OpenAlex] Found {len(ref_ids)} referenced works for {id_type}: {identifier}")
            
            # Fetch the referenced works in batches to avoid overloading the API
            # and extract DOIs
            referenced_dois = []
            batch_size = 25
            
            # Process in batches
            for i in range(0, len(ref_ids), batch_size):
                batch = ref_ids[i:i+batch_size]
                
                # Use pyalex to get details of referenced works
                try:
                    refs_batch = Works()[batch]
                    
                    # Extract DOIs from each work
                    for ref in refs_batch:
                        if ref and "doi" in ref and ref["doi"]:
                            doi = ref["doi"]
                            # Clean DOI if it's a URL
                            if doi.startswith("https://doi.org/"):
                                doi = doi[len("https://doi.org/"):]
                            if doi.startswith('10.'):  # Basic validation
                                referenced_dois.append(doi.lower())
                    
                    # Add a small delay between batches
                    if i + batch_size < len(ref_ids):
                        time.sleep(0.5)
                        
                except Exception as e:
                    logger.warning(f"Error fetching batch of references: {e}")
                    continue
                    
            id_type = "MAG ID" if identifier.isdigit() else "DOI"
            logger.info(f"[OpenAlex] Successfully extracted {len(referenced_dois)} DOIs from referenced works for {id_type}: {identifier}")
            return referenced_dois
            
        except Exception as e:
            id_type = "MAG ID" if identifier.isdigit() else "DOI"
            logger.error(f"Error fetching references for {id_type} {identifier}: {e}")
            return []

    def get_citations(self, identifier: str) -> List[str]:
        """
        Fetch DOIs of works citing the given identifier (DOI or MAG ID).
        
        Uses pyalex to fetch the incoming citations (works that cite this paper).
        
        Args:
            identifier: A DOI string or MAG ID string
            
        Returns:
            A list of DOIs citing the given identifier
        """
        # Clean DOI if it's a URL
        if identifier.startswith("https://doi.org/"):
            identifier = identifier[len("https://doi.org/"):]
            
        try:
            # Determine if this is a DOI or MAG ID and construct appropriate query
            if identifier.isdigit():
                # This is a MAG ID
                query_identifier = f"mag:{identifier}"
                id_type = "MAG ID"
                logger.debug(f"Fetching OpenAlex ID for MAG ID: {identifier}")
            else:
                # This is a DOI
                query_identifier = f"doi:{identifier}"
                id_type = "DOI"
                logger.debug(f"Fetching OpenAlex ID for DOI: {identifier}")
            
            target_work = Works()[query_identifier]

            if not target_work or "id" not in target_work:
                logger.warning(f"[OpenAlex] Could not find OpenAlex ID for {id_type}: {identifier}")
                return []

            openalex_id = target_work["id"]
            if not openalex_id:
                logger.warning(f"[OpenAlex] Found empty OpenAlex ID for {id_type}: {identifier}")
                return []
                
            logger.debug(f"Found OpenAlex ID {openalex_id} for {id_type}: {identifier}")

            # Use Works().filter(cites=openalex_id) to find works citing this work
            logger.debug(f"Fetching citations for OpenAlex ID: {openalex_id}")

            # Create filter query using the OpenAlex ID
            citing_works_query = Works().filter(cites=openalex_id)

            # Get citation count to log progress
            citation_count = citing_works_query.count()
            logger.info(f"[OpenAlex] Found {citation_count} citing works for {id_type}: {identifier} (OpenAlex ID: {openalex_id})")

            if citation_count == 0:
                return []

            # Collect all citing DOIs with pagination to handle large result sets
            citing_dois = []

            # Use pagination to fetch all results
            # pyalex handles this elegantly with an iterator
            page_count = 0
            for page in citing_works_query.paginate(per_page=100):
                page_count += 1
                for work in page:
                    if "doi" in work and work["doi"]:
                        doi = work["doi"]
                        # Clean DOI if it's a URL
                        if doi.startswith("https://doi.org/"):
                            doi = doi[len("https://doi.org/"):]
                        if doi.startswith('10.'):  # Basic validation
                            citing_dois.append(doi.lower())
                
                # Add delay between pages to avoid rate limiting
                time.sleep(0.5)

            logger.info(f"[OpenAlex] Successfully extracted {len(citing_dois)} DOIs from citing works for {id_type}: {identifier}")
            return citing_dois

        except Exception as e:
            # Check if this is a rate limiting error that we should retry
            if "429" in str(e) or "too many" in str(e).lower():
                id_type = "MAG ID" if identifier.isdigit() else "DOI"
                logger.warning(f"[OpenAlex] Rate limited for {id_type} {identifier}, retrying with exponential backoff...")
                
                # Retry with exponential backoff
                for attempt in range(3):
                    delay = (2 ** attempt) + random.uniform(0, 1)  # 1-2s, 2-3s, 4-5s
                    logger.info(f"[OpenAlex] Waiting {delay:.1f}s before retry attempt {attempt + 1}/3")
                    time.sleep(delay)
                    
                    try:
                        # Retry the entire citations fetch
                        query_identifier = f"mag:{identifier}" if identifier.isdigit() else f"doi:{identifier}"
                        target_work = Works()[query_identifier]
                        if not target_work or "id" not in target_work:
                            continue
                        
                        openalex_id = target_work["id"]
                        citing_works_query = Works().filter(cites=openalex_id)
                        citation_count = citing_works_query.count()
                        
                        if citation_count == 0:
                            return []
                        
                        citing_dois = []
                        for page in citing_works_query.paginate(per_page=100):
                            for work in page:
                                if "doi" in work and work["doi"]:
                                    doi = work["doi"]
                                    if doi.startswith("https://doi.org/"):
                                        doi = doi[len("https://doi.org/"):]
                                    if doi.startswith('10.'):
                                        citing_dois.append(doi.lower())
                            # Longer delay during retry
                            time.sleep(1.0)
                        
                        id_type = "MAG ID" if identifier.isdigit() else "DOI"
                        logger.info(f"[OpenAlex] Successfully extracted {len(citing_dois)} DOIs from citing works for {id_type}: {identifier} (retry successful)")
                        return citing_dois
                        
                    except Exception as retry_e:
                        id_type = "MAG ID" if identifier.isdigit() else "DOI"
                        if attempt == 2:  # Last attempt
                            logger.error(f"[OpenAlex] All retry attempts failed for {id_type} {identifier}: {retry_e}")
                        else:
                            logger.warning(f"[OpenAlex] Retry attempt {attempt + 1} failed for {id_type} {identifier}: {retry_e}")
                        continue
                
                return []  # All retries failed
            
            # More specific error for the initial ID lookup vs. fetching citations
            id_type = "MAG ID" if identifier.isdigit() else "DOI"
            if 'openalex_id' not in locals():
                 logger.error(f"[OpenAlex] Error fetching OpenAlex ID for {id_type} {identifier}: {e}")
            else:
                logger.error(f"[OpenAlex] Error fetching citations for {id_type} {identifier} (OpenAlex ID: {openalex_id}): {e}")
            return [] 