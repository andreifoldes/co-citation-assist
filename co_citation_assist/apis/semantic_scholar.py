import logging
import requests
import time
from typing import List, Optional, Dict, Any
from urllib.parse import quote

from .base import CitationAPI
from ..utils import get_semantic_scholar_api_key

logger = logging.getLogger(__name__)

class SemanticScholarAPI(CitationAPI):
    """Implementation of CitationAPI using the Semantic Scholar Academic Graph API."""
    
    BASE_URL = "https://api.semanticscholar.org/graph/v1"
    
    def __init__(self):
        """Initialize the Semantic Scholar API client."""
        self.api_key = get_semantic_scholar_api_key()
        self.session = requests.Session()
        
        # Set up headers
        self.session.headers.update({
            'User-Agent': 'co-citation-assist/0.1.0 (https://github.com/andreifoldes/co-citation-assist)'
        })
        
        # Comment out API key usage temporarily due to 403 errors
        # The API works without the key but with rate limits
        # if self.api_key:
        #     self.session.headers.update({
        #         'x-api-key': self.api_key
        #     })
        #     logger.info("Initialized Semantic Scholar API client with API key")
        # else:
        logger.info("Initialized Semantic Scholar API client without API key (rate limited)")
    
    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """Make a request to the Semantic Scholar API with error handling and rate limiting."""
        url = f"{self.BASE_URL}/{endpoint}"
        
        try:
            response = self.session.get(url, params=params, timeout=30)
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                logger.warning(f"Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                # Retry once
                response = self.session.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                logger.debug(f"[SemanticScholar] Paper not found: {endpoint}")
                return None
            else:
                logger.warning(f"[SemanticScholar] API request failed with status {response.status_code}: {response.text}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {endpoint}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error for {endpoint}: {e}")
            return None
    
    def _extract_doi_from_paper(self, paper: Dict[str, Any]) -> Optional[str]:
        """Extract and validate DOI from a Semantic Scholar paper object."""
        doi = paper.get('doi')
        if doi and isinstance(doi, str) and doi.startswith('10.') and '/' in doi:
            return doi.lower()
        return None
    
    def get_references(self, identifier: str) -> List[str]:
        """
        Fetch DOIs of works referenced by the given identifier (DOI or MAG ID).
        
        Args:
            identifier: A DOI string or MAG ID string
            
        Returns:
            A list of DOIs referenced by the given identifier
        """
        # Clean DOI if it's a URL
        if identifier.startswith("https://doi.org/"):
            identifier = identifier[len("https://doi.org/"):]
        
        # Determine if this is a DOI or MAG ID and construct appropriate endpoint
        if identifier.isdigit():
            # This is a MAG ID
            endpoint = f"paper/MAG:{identifier}/references"
            id_type = "MAG ID"
        else:
            # This is a DOI
            endpoint = f"paper/{identifier}/references"
            id_type = "DOI"
        
        params = {
            'fields': 'title,authors,year,externalIds',
            'limit': 1000  # Maximum allowed by API
        }
        
        try:
            logger.debug(f"Fetching references for {id_type}: {identifier}")
            data = self._make_request(endpoint, params)
            
            if not data or 'data' not in data:
                logger.warning(f"[SemanticScholar] No references data found for {id_type}: {identifier}. Details on the endpoints we should use are at https://api.semanticscholar.org/api-docs/#tag/Paper-Data/operation/get_graph_get_paper_citations and https://api.semanticscholar.org/api-docs/#tag/Paper-Data/operation/get_graph_get_paper_references")
                return []
            
            # Check if data is null (publisher blocking)
            if data['data'] is None:
                # Check for citing paper info which might contain publisher blocking message
                if 'citingPaperInfo' in data:
                    citing_info = data['citingPaperInfo']
                    if 'openAccessPdf' in citing_info and citing_info['openAccessPdf'].get('disclaimer'):
                        logger.warning(f"[SemanticScholar] References blocked by publisher for {id_type}: {identifier}. Publisher restricts reference data access via API.")
                    else:
                        logger.warning(f"[SemanticScholar] References data is null for {id_type}: {identifier}. This may indicate publisher restrictions on reference data.")
                else:
                    logger.warning(f"[SemanticScholar] References data is null for {id_type}: {identifier}. This may indicate publisher restrictions on reference data.")
                return []
            
            references = data['data']
            if not references:
                logger.info(f"[SemanticScholar] No references found for {id_type}: {identifier}")
                return []
                
            logger.info(f"[SemanticScholar] Found {len(references)} references for {id_type}: {identifier}")
            
            # Extract DOIs from references
            referenced_dois = []
            for ref in references:
                if 'citedPaper' in ref and ref['citedPaper']:
                    # Extract DOI from externalIds
                    cited_paper = ref['citedPaper']
                    if 'externalIds' in cited_paper and cited_paper['externalIds'] and 'DOI' in cited_paper['externalIds']:
                        doi = cited_paper['externalIds']['DOI']
                        if doi and isinstance(doi, str) and doi.startswith('10.') and '/' in doi:
                            referenced_dois.append(doi.lower())
            
            # Add delay to be respectful to the API
            time.sleep(0.1)
            
            logger.info(f"[SemanticScholar] Successfully extracted {len(referenced_dois)} DOIs from references for {id_type}: {identifier}")
            return referenced_dois
            
        except Exception as e:
            logger.error(f"Error fetching references for {id_type} {identifier}: {e}")
            return []
    
    def get_citations(self, identifier: str) -> List[str]:
        """
        Fetch DOIs of works citing the given identifier (DOI or MAG ID).
        
        Args:
            identifier: A DOI string or MAG ID string
            
        Returns:
            A list of DOIs citing the given identifier
        """
        # Clean DOI if it's a URL
        if identifier.startswith("https://doi.org/"):
            identifier = identifier[len("https://doi.org/"):]
        
        # Determine if this is a DOI or MAG ID and construct appropriate endpoint
        if identifier.isdigit():
            # This is a MAG ID
            endpoint = f"paper/MAG:{identifier}/citations"
            id_type = "MAG ID"
        else:
            # This is a DOI
            endpoint = f"paper/{identifier}/citations"
            id_type = "DOI"
        
        citing_dois = []
        offset = 0
        limit = 1000  # Maximum allowed by API per request
        
        try:
            logger.debug(f"Fetching citations for {id_type}: {identifier}")
            
            while True:
                params = {
                    'fields': 'title,authors,year,externalIds',
                    'limit': limit,
                    'offset': offset
                }
                
                data = self._make_request(endpoint, params)
                
                if not data or 'data' not in data:
                    break
                
                citations = data['data']
                if not citations:
                    break
                
                # Extract DOIs from citations
                batch_dois = []
                for citation in citations:
                    if 'citingPaper' in citation and citation['citingPaper']:
                        # Extract DOI from externalIds
                        citing_paper = citation['citingPaper']
                        if 'externalIds' in citing_paper and citing_paper['externalIds'] and 'DOI' in citing_paper['externalIds']:
                            doi = citing_paper['externalIds']['DOI']
                            if doi and isinstance(doi, str) and doi.startswith('10.') and '/' in doi:
                                batch_dois.append(doi.lower())
                
                citing_dois.extend(batch_dois)
                logger.debug(f"Processed batch: {len(batch_dois)} DOIs (offset: {offset})")
                
                # Check if we have more results
                if len(citations) < limit:
                    break
                
                offset += limit
                
                # Add delay between paginated requests
                time.sleep(0.1)
            
            logger.info(f"[SemanticScholar] Successfully extracted {len(citing_dois)} DOIs from citations for {id_type}: {identifier}")
            return citing_dois
            
        except Exception as e:
            logger.error(f"Error fetching citations for {id_type} {identifier}: {e}")
            return []