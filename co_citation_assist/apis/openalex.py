import logging
from typing import List
import time

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
        Fetch DOIs of works referenced by the given identifier (DOI).
        
        Uses pyalex to fetch the outgoing citations (works that this paper references).
        
        Args:
            identifier: A DOI string
            
        Returns:
            A list of DOIs referenced by the given identifier
        """
        # Clean DOI if it's a URL
        if identifier.startswith("https://doi.org/"):
            identifier = identifier[len("https://doi.org/"):]
            
        try:
            # Try to get the work directly
            logger.debug(f"Fetching work metadata for DOI: {identifier}")
            work = Works()[f"doi:{identifier}"]
            
            if not work or "referenced_works" not in work or not work["referenced_works"]:
                logger.warning(f"No referenced works found for DOI: {identifier}")
                return []
                
            # Get referenced works IDs
            ref_ids = work["referenced_works"]
            logger.info(f"Found {len(ref_ids)} referenced works for DOI: {identifier}")
            
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
                        time.sleep(0.2)
                        
                except Exception as e:
                    logger.warning(f"Error fetching batch of references: {e}")
                    continue
                    
            logger.info(f"Successfully extracted {len(referenced_dois)} DOIs from referenced works for DOI: {identifier}")
            return referenced_dois
            
        except Exception as e:
            logger.error(f"Error fetching references for DOI {identifier}: {e}")
            return []

    def get_citations(self, identifier: str) -> List[str]:
        """
        Fetch DOIs of works citing the given identifier (DOI).
        
        Uses pyalex to fetch the incoming citations (works that cite this paper).
        
        Args:
            identifier: A DOI string
            
        Returns:
            A list of DOIs citing the given identifier
        """
        # Clean DOI if it's a URL
        if identifier.startswith("https://doi.org/"):
            identifier = identifier[len("https://doi.org/"):]
            
        try:
            # First, get the OpenAlex ID for the given DOI
            logger.debug(f"Fetching OpenAlex ID for DOI: {identifier}")
            target_work = Works()[f"doi:{identifier}"]

            if not target_work or "id" not in target_work:
                logger.warning(f"Could not find OpenAlex ID for DOI: {identifier}")
                return []

            openalex_id = target_work["id"]
            if not openalex_id:
                logger.warning(f"Found empty OpenAlex ID for DOI: {identifier}")
                return []
                
            logger.debug(f"Found OpenAlex ID {openalex_id} for DOI: {identifier}")

            # Use Works().filter(cites=openalex_id) to find works citing this work
            logger.debug(f"Fetching citations for OpenAlex ID: {openalex_id}")

            # Create filter query using the OpenAlex ID
            citing_works_query = Works().filter(cites=openalex_id)

            # Get citation count to log progress
            citation_count = citing_works_query.count()
            logger.info(f"Found {citation_count} citing works for DOI: {identifier} (OpenAlex ID: {openalex_id})")

            if citation_count == 0:
                return []

            # Collect all citing DOIs with pagination to handle large result sets
            citing_dois = []

            # Use pagination to fetch all results
            # pyalex handles this elegantly with an iterator
            for page in citing_works_query.paginate(per_page=100):
                for work in page:
                    if "doi" in work and work["doi"]:
                        doi = work["doi"]
                        # Clean DOI if it's a URL
                        if doi.startswith("https://doi.org/"):
                            doi = doi[len("https://doi.org/"):]
                        if doi.startswith('10.'):  # Basic validation
                            citing_dois.append(doi.lower())

            logger.info(f"Successfully extracted {len(citing_dois)} DOIs from citing works for DOI: {identifier}")
            return citing_dois

        except Exception as e:
            # More specific error for the initial ID lookup vs. fetching citations
            if 'openalex_id' not in locals():
                 logger.error(f"Error fetching OpenAlex ID for DOI {identifier}: {e}")
            else:
                logger.error(f"Error fetching citations for DOI {identifier} (OpenAlex ID: {openalex_id}): {e}")
            return [] 