import json
import logging
import time
import random
from typing import Dict, List, Set, Optional, Any, Tuple
from enum import Enum
from collections import defaultdict, Counter
import re
from dataclasses import dataclass
from tqdm import tqdm

from .apis.openalex import OpenAlexAPI

logger = logging.getLogger(__name__)

class LinkingMode(str, Enum):
    """Enum for different network linking modes."""
    BIBLIOGRAPHIC_COUPLING = "bibliographic_coupling"
    CO_CITATION = "co_citation"
    AMSLER = "amsler"

@dataclass
class NodeMetadata:
    """Metadata for a network node."""
    id: int
    label: str
    description: str
    url: str
    year: Optional[int] = None
    authors: Optional[List[str]] = None
    title: Optional[str] = None
    source: Optional[str] = None
    citations: Optional[int] = None

@dataclass
class NetworkLink:
    """A link between two nodes in the network."""
    source_id: int
    target_id: int
    strength: float

class NetworkGenerator:
    """Generates network structures from detailed citations data."""
    
    def __init__(self):
        self.openalex_api = OpenAlexAPI()
        self.node_counter = 0
        self.identifier_to_node_id: Dict[str, int] = {}
        self.node_metadata: Dict[int, NodeMetadata] = {}
    
    def generate_network(
        self,
        citations_data: Dict[str, Dict[str, List[str]]],
        mode: LinkingMode,
        min_strength: int = 1,
        max_nodes: Optional[int] = None,
        include_cociting_nodes: bool = False,
        amsler_lambda: float = 0.5
    ) -> Dict[str, Any]:
        """
        Generate a network structure from citations data.
        
        Args:
            citations_data: Dictionary with structure from detailed_references_citations.json
            mode: Type of linking to perform
            min_strength: Minimum link strength to include
            max_nodes: Maximum number of nodes to include (None for no limit)
            include_cociting_nodes: Include co-citing papers as nodes (only for co-citation mode)
            amsler_lambda: Lambda weight for Amsler similarity (only for amsler mode)
            
        Returns:
            Dictionary in VOSGraph format
        """
        logger.info(f"Generating network with mode: {mode.value}")
        
        # Extract all unique identifiers from the data
        all_identifiers = self._extract_all_identifiers(citations_data, include_cociting_nodes)
        logger.info(f"Found {len(all_identifiers)} unique identifiers")
        
        # Limit nodes if specified
        if max_nodes and len(all_identifiers) > max_nodes:
            # Prioritize the initial DOIs (keys in citations_data)
            initial_dois = set(citations_data.keys())
            other_identifiers = all_identifiers - initial_dois
            
            # Keep all initial DOIs and fill up to max_nodes with others
            remaining_slots = max_nodes - len(initial_dois)
            if remaining_slots > 0:
                other_identifiers = list(other_identifiers)[:remaining_slots]
                all_identifiers = initial_dois | set(other_identifiers)
            else:
                all_identifiers = set(list(initial_dois)[:max_nodes])
            
            logger.info(f"Limited to {len(all_identifiers)} nodes")
        
        # Create initial node mappings for all identifiers
        self._create_node_mappings(all_identifiers)
        
        # Generate links based on mode (this determines which nodes we actually need)
        if mode == LinkingMode.BIBLIOGRAPHIC_COUPLING:
            links = self._generate_bibliographic_coupling_links(citations_data, min_strength)
        elif mode == LinkingMode.CO_CITATION:
            links = self._generate_co_citation_links(citations_data, min_strength, include_cociting_nodes)
        elif mode == LinkingMode.AMSLER:
            links = self._generate_amsler_links(citations_data, min_strength, amsler_lambda)
        else:
            raise ValueError(f"Unsupported linking mode: {mode}")
        
        # Determine which nodes actually have links (only fetch metadata for these)
        linked_node_ids = set()
        for link in links:
            linked_node_ids.add(link.source_id)
            linked_node_ids.add(link.target_id)
        
        # Get identifiers for linked nodes only
        id_to_identifier = {v: k for k, v in self.identifier_to_node_id.items()}
        linked_identifiers = {id_to_identifier[node_id] for node_id in linked_node_ids}
        
        logger.info(f"Found {len(links)} links between {len(linked_identifiers)} nodes")
        
        # Only fetch metadata for nodes that will appear in the final network
        self._fetch_node_metadata(linked_identifiers)
        
        # Build the network structure
        network_data = self._build_network_structure(links)
        
        logger.info(f"Generated network with {len(network_data['network']['items'])} nodes and {len(network_data['network']['links'])} links")
        
        return network_data
    
    def _extract_all_identifiers(self, citations_data: Dict[str, Dict[str, List[str]]], include_cociting_nodes: bool = False) -> Set[str]:
        """Extract all unique identifiers from citations data."""
        all_identifiers = set()
        
        # Add initial DOIs/identifiers (keys)
        all_identifiers.update(citations_data.keys())
        
        # Add all referenced identifiers (always include these)
        for doi_data in citations_data.values():
            if 'references' in doi_data:
                all_identifiers.update(doi_data['references'])
            
            # Only add citing identifiers if include_cociting_nodes is True or mode is not co-citation
            if 'citations' in doi_data and include_cociting_nodes:
                all_identifiers.update(doi_data['citations'])
        
        return all_identifiers
    
    def _create_node_mappings(self, identifiers: Set[str]):
        """Create mappings from identifiers to integer node IDs."""
        self.node_counter = 0
        self.identifier_to_node_id = {}
        
        for identifier in sorted(identifiers):  # Sort for consistency
            self.identifier_to_node_id[identifier] = self.node_counter
            self.node_counter += 1
    
    def _create_placeholder_metadata(self, identifiers: Set[str]):
        """Create placeholder metadata for all nodes (for testing without API calls)."""
        logger.info("Creating placeholder metadata for nodes...")
        
        for identifier in identifiers:
            node_id = self.identifier_to_node_id[identifier]
            
            # Create simple placeholder metadata
            self.node_metadata[node_id] = NodeMetadata(
                id=node_id,
                label=f"paper {node_id} (unknown)",
                description=f"<table><tr><td>ID:</td><td>{identifier}</td></tr></table>",
                url=f"https://doi.org/{identifier}" if self._is_doi(identifier) else "",
                year=2020,  # placeholder
                authors=["unknown"],
                title="Unknown Title",
                source="Unknown Source",
                citations=0
            )

    def _fetch_node_metadata(self, identifiers: Set[str]):
        """Fetch metadata for all nodes using OpenAlex API (once per node)."""
        logger.info("Fetching metadata for nodes...")
        
        # Separate DOIs from other identifiers
        dois = [id for id in identifiers if self._is_doi(id)]
        mag_ids = [id for id in identifiers if self._is_mag_id(id)]
        
        # Fetch metadata for all identifiers with a single progress bar
        all_identifiers = dois + mag_ids
        metadata_map = {}
        
        if all_identifiers:
            logger.info(f"Fetching metadata for {len(all_identifiers)} nodes from OpenAlex API")
            
            with tqdm(total=len(all_identifiers), desc="Fetching node metadata") as pbar:
                # Process DOIs
                for identifier in dois:
                    try:
                        query_id = f"doi:{identifier}" if not identifier.startswith('doi:') else identifier
                        
                        # Use pyalex Works API to fetch individual work
                        from pyalex import Works
                        work = Works()[query_id]
                        
                        if work:
                            metadata_map[identifier] = work
                            logger.debug(f"Fetched metadata for DOI: {identifier}")
                        else:
                            logger.debug(f"No metadata found for DOI: {identifier}")
                            metadata_map[identifier] = {}
                        
                        # Add small delay to be respectful to API
                        time.sleep(0.1)
                                
                    except Exception as e:
                        logger.warning(f"Failed to fetch metadata for DOI {identifier}: {e}")
                    
                    pbar.update(1)
                
                # Process MAG IDs
                for identifier in mag_ids:
                    try:
                        query_id = f"mag:{identifier}" if not identifier.startswith('mag:') else identifier
                        
                        # Use pyalex Works API to fetch individual work
                        from pyalex import Works
                        work = Works()[query_id]
                        
                        if work:
                            metadata_map[identifier] = work
                            logger.debug(f"Fetched metadata for MAG ID: {identifier}")
                        else:
                            logger.debug(f"No metadata found for MAG ID: {identifier}")
                            metadata_map[identifier] = {}
                        
                        # Add small delay to be respectful to API
                        time.sleep(0.1)
                                
                    except Exception as e:
                        logger.warning(f"Failed to fetch metadata for MAG ID {identifier}: {e}")
                    
                    pbar.update(1)
        
        # Create NodeMetadata objects
        logger.info("Creating node metadata objects...")
        with tqdm(total=len(identifiers), desc="Processing node metadata") as pbar:
            for identifier in identifiers:
                node_id = self.identifier_to_node_id[identifier]
                metadata = metadata_map.get(identifier, {})
                
                self.node_metadata[node_id] = self._create_node_metadata(
                    node_id, identifier, metadata
                )
                pbar.update(1)
    
    
    def _create_node_metadata(self, node_id: int, identifier: str, api_metadata: Dict) -> NodeMetadata:
        """Create NodeMetadata from API response."""
        # Handle None api_metadata
        if api_metadata is None:
            api_metadata = {}
        
        # Extract basic info
        title = api_metadata.get('title', 'Unknown Title')
        year = api_metadata.get('publication_year')
        
        # Extract first author surname for label
        first_author_surname = "Unknown"
        authors = []
        if 'authorships' in api_metadata:
            for authorship in api_metadata['authorships']:
                author = authorship.get('author', {})
                display_name = author.get('display_name', '')
                if display_name:
                    authors.append(display_name)
                    # Get first author surname for label
                    if first_author_surname == "Unknown":
                        name_parts = display_name.split()
                        if name_parts:
                            first_author_surname = name_parts[-1].lower().capitalize()
        
        # Create label in format "firstauthor-surname (pubyear)" with Unicode normalization
        import unicodedata
        # Normalize Unicode characters to ASCII equivalents where possible
        normalized_surname = unicodedata.normalize('NFKD', first_author_surname).encode('ascii', 'ignore').decode('ascii')
        if not normalized_surname:  # If normalization resulted in empty string, keep original
            normalized_surname = first_author_surname
        label = f"{normalized_surname} ({year or 'unknown'})"
        
        # Create description table - use the authors list we already built
        author_names = authors
        
        author_str = '; '.join(author_names[:4])  # Limit to 4 authors in description
        if len(author_names) > 4:
            author_str += f" (and {len(author_names) - 4} others)"
        
        # Try multiple sources for journal/venue name
        source = 'Unknown Source'
        
        # Primary source: host_venue display_name
        host_venue = api_metadata.get('host_venue') or {}
        if host_venue.get('display_name'):
            source = host_venue['display_name']
        
        # Fallback 1: primary_location host_venue display_name
        elif ((api_metadata.get('primary_location') or {}).get('source') or {}).get('display_name'):
            source = api_metadata['primary_location']['source']['display_name']
        
        # Fallback 2: first location with a source
        elif api_metadata.get('locations'):
            for location in api_metadata['locations']:
                if (location.get('source') or {}).get('display_name'):
                    source = location['source']['display_name']
                    break
        
        # Fallback 3: biblio.venue field
        elif (api_metadata.get('biblio') or {}).get('venue'):
            source = api_metadata['biblio']['venue']
        citations = api_metadata.get('cited_by_count', 0)
        
        # Escape HTML entities to properly handle Unicode characters
        import html
        escaped_author = html.escape(author_str or 'Unknown', quote=False)
        escaped_title = html.escape(title or 'Unknown Title', quote=False)
        escaped_source = html.escape(source or 'Unknown Source', quote=False)
        
        description = (
            f"<table>"
            f"<tr><td>Authors:</td><td>{escaped_author}</td></tr>"
            f"<tr><td>Title:</td><td>{escaped_title}</td></tr>"
            f"<tr><td>Source:</td><td>{escaped_source}</td></tr>"
            f"<tr><td>Year:</td><td>{year or 'Unknown'}</td></tr>"
            f"</table>"
        )
        
        # Create URL (use OpenAlex ID if available, otherwise construct)
        url = api_metadata.get('id', f"https://doi.org/{identifier}" if self._is_doi(identifier) else "")
        
        return NodeMetadata(
            id=node_id,
            label=label,
            description=description,
            url=url,
            year=year,
            authors=authors,
            title=title,
            source=source,
            citations=citations
        )
    
    def _generate_bibliographic_coupling_links(
        self, 
        citations_data: Dict[str, Dict[str, List[str]]], 
        min_strength: int
    ) -> List[NetworkLink]:
        """Generate links based on bibliographic coupling (shared references)."""
        logger.info("Generating bibliographic coupling links...")
        
        # Build reference sets for each paper
        paper_references: Dict[str, Set[str]] = {}
        
        for paper_id, data in citations_data.items():
            if 'references' in data:
                # Include all references (not just those in node set)
                references = set(data['references'])
                paper_references[paper_id] = references
        
        # Calculate bibliographic coupling strength between papers
        links = []
        paper_ids = list(paper_references.keys())
        
        total_pairs = len(paper_ids) * (len(paper_ids) - 1) // 2
        with tqdm(total=total_pairs, desc="Computing pairwise bibliographic coupling") as pbar:
            for i in range(len(paper_ids)):
                for j in range(i + 1, len(paper_ids)):
                    pbar.update(1)
                    paper1, paper2 = paper_ids[i], paper_ids[j]
                    
                    # Skip if either paper is not in our node set
                    if paper1 not in self.identifier_to_node_id or paper2 not in self.identifier_to_node_id:
                        continue
                    
                    # Calculate overlap in references
                    refs1 = paper_references.get(paper1, set())
                    refs2 = paper_references.get(paper2, set())
                    
                    overlap = len(refs1.intersection(refs2))
                    
                    if overlap >= min_strength:
                        node1_id = self.identifier_to_node_id[paper1]
                        node2_id = self.identifier_to_node_id[paper2]
                        
                        links.append(NetworkLink(
                            source_id=node1_id,
                            target_id=node2_id,
                            strength=float(overlap)
                        ))
        
        return links
    
    def _generate_co_citation_links(
        self, 
        citations_data: Dict[str, Dict[str, List[str]]], 
        min_strength: int,
        include_cociting_nodes: bool = False
    ) -> List[NetworkLink]:
        """Generate links based on co-citation (being cited together)."""
        logger.info("Generating co-citation links...")
        
        # Build citation sets for each paper
        paper_citations: Dict[str, Set[str]] = {}
        
        for paper_id, data in citations_data.items():
            if 'citations' in data:
                citations = set(data['citations'])
                
                if include_cociting_nodes:
                    # Include all citations as potential nodes (they should already be in node mapping)
                    paper_citations[paper_id] = citations
                else:
                    # Only include citations that are in our node set
                    citations = citations.intersection(self.identifier_to_node_id.keys())
                    paper_citations[paper_id] = citations
        
        # Calculate co-citation strength between papers
        links = []
        paper_ids = list(paper_citations.keys())
        
        total_pairs = len(paper_ids) * (len(paper_ids) - 1) // 2
        with tqdm(total=total_pairs, desc="Computing pairwise co-citation") as pbar:
            for i in range(len(paper_ids)):
                for j in range(i + 1, len(paper_ids)):
                    pbar.update(1)
                    paper1, paper2 = paper_ids[i], paper_ids[j]
                    
                    # Skip if either paper is not in our node set
                    if paper1 not in self.identifier_to_node_id or paper2 not in self.identifier_to_node_id:
                        continue
                    
                    # Calculate overlap in citations
                    cites1 = paper_citations.get(paper1, set())
                    cites2 = paper_citations.get(paper2, set())
                    
                    overlap = len(cites1.intersection(cites2))
                    
                    if overlap >= min_strength:
                        node1_id = self.identifier_to_node_id[paper1]
                        node2_id = self.identifier_to_node_id[paper2]
                        
                        links.append(NetworkLink(
                            source_id=node1_id,
                            target_id=node2_id,
                            strength=float(overlap)
                        ))
        
        return links
    
    def _generate_amsler_links(
        self, 
        citations_data: Dict[str, Dict[str, List[str]]], 
        min_strength: int,
        amsler_lambda: float = 0.5
    ) -> List[NetworkLink]:
        """Generate links based on Amsler similarity (composite of bibliographic coupling and co-citation)."""
        logger.info(f"Generating Amsler similarity links with lambda={amsler_lambda}...")
        
        # Build reference and citation sets for each paper
        paper_references: Dict[str, Set[str]] = {}
        paper_citations: Dict[str, Set[str]] = {}
        
        for paper_id, data in citations_data.items():
            if 'references' in data:
                paper_references[paper_id] = set(data['references'])
            
            if 'citations' in data:
                paper_citations[paper_id] = set(data['citations'])
        
        # Calculate Amsler similarity between papers
        links = []
        paper_ids = list(set(paper_references.keys()) | set(paper_citations.keys()))
        
        total_pairs = len(paper_ids) * (len(paper_ids) - 1) // 2
        with tqdm(total=total_pairs, desc="Computing pairwise Amsler similarity") as pbar:
            for i in range(len(paper_ids)):
                for j in range(i + 1, len(paper_ids)):
                    pbar.update(1)
                    paper1, paper2 = paper_ids[i], paper_ids[j]
                    
                    # Skip if either paper is not in our node set
                    if paper1 not in self.identifier_to_node_id or paper2 not in self.identifier_to_node_id:
                        continue
                    
                    # Calculate bibliographic coupling strength (shared references)
                    refs1 = paper_references.get(paper1, set())
                    refs2 = paper_references.get(paper2, set())
                    bc_strength = len(refs1.intersection(refs2))
                    
                    # Calculate co-citation strength (shared citations)
                    cites1 = paper_citations.get(paper1, set())
                    cites2 = paper_citations.get(paper2, set())
                    cc_strength = len(cites1.intersection(cites2))
                    
                    # Calculate Amsler similarity: λ * BC + (1-λ) * CC
                    amsler_strength = amsler_lambda * bc_strength + (1 - amsler_lambda) * cc_strength
                    
                    if amsler_strength >= min_strength:
                        node1_id = self.identifier_to_node_id[paper1]
                        node2_id = self.identifier_to_node_id[paper2]
                        
                        links.append(NetworkLink(
                            source_id=node1_id,
                            target_id=node2_id,
                            strength=float(amsler_strength)
                        ))
        
        return links
    
    def _build_network_structure(self, links: List[NetworkLink]) -> Dict[str, Any]:
        """Build the final network structure in VOSGraph format."""
        # Get all nodes that have at least one link
        linked_node_ids = set()
        for link in links:
            linked_node_ids.add(link.source_id)
            linked_node_ids.add(link.target_id)
        
        # Track used coordinates to ensure uniqueness
        used_coordinates = set()
        
        def generate_unique_coordinates():
            """Generate unique x, y coordinates."""
            max_attempts = 10000  # Prevent infinite loop
            attempts = 0
            
            while attempts < max_attempts:
                x = round(random.uniform(-2.0, 2.0), 4)
                y = round(random.uniform(-2.0, 2.0), 4)
                coord_tuple = (x, y)
                
                if coord_tuple not in used_coordinates:
                    used_coordinates.add(coord_tuple)
                    return x, y
                
                attempts += 1
            
            # Fallback: if we can't find unique coordinates, use a systematic approach
            # This should rarely happen given the large coordinate space
            for i in range(len(used_coordinates)):
                x = round(-2.0 + (i * 0.0001) % 4.0, 4)
                y = round(-2.0 + ((i // 40000) * 0.0001) % 4.0, 4)
                coord_tuple = (x, y)
                if coord_tuple not in used_coordinates:
                    used_coordinates.add(coord_tuple)
                    return x, y
            
            # Ultimate fallback
            return 0.0, 0.0
        
        # Build items (nodes)
        items = []
        for node_id in tqdm(sorted(linked_node_ids), desc="Building network nodes"):
            if node_id in self.node_metadata:
                metadata = self.node_metadata[node_id]
                
                # Calculate link statistics for this node
                node_links = [link for link in links if link.source_id == node_id or link.target_id == node_id]
                total_link_strength = sum(link.strength for link in node_links)
                
                # Calculate normalized citations (citations per year since publication)
                norm_citations = self._calculate_normalized_citations(metadata.citations, metadata.year)
                
                # Generate unique coordinates
                x, y = generate_unique_coordinates()
                
                item = {
                    "id": metadata.id,
                    "label": metadata.label,
                    "description": metadata.description,
                    "url": metadata.url,
                    "x": x,
                    "y": y,
                    "cluster": 1,  # Placeholder - would need clustering algorithm
                    "weights": {
                        "Links": float(len(node_links)),
                        "Total link strength": total_link_strength,
                        "Citations": float(metadata.citations or 0),
                        "Norm. citations": norm_citations
                    },
                    "scores": {
                        "Pub. year": float(metadata.year or 0),
                        "Citations": float(metadata.citations or 0),
                        "Norm. citations": norm_citations
                    }
                }
                items.append(item)
        
        # Build links
        network_links = []
        for link in links:
            network_links.append({
                "source_id": link.source_id,
                "target_id": link.target_id,
                "strength": link.strength
            })
        
        return {
            "network": {
                "items": items,
                "links": network_links
            }
        }
    
    def _is_doi(self, identifier: str) -> bool:
        """Check if identifier is a DOI."""
        return identifier.startswith('10.') and '/' in identifier
    
    def _is_mag_id(self, identifier: str) -> bool:
        """Check if identifier is a Microsoft Academic Graph ID."""
        # MAG IDs are typically numeric strings
        return identifier.isdigit() and len(identifier) > 5
    
    def _calculate_normalized_citations(self, citations: Optional[int], pub_year: Optional[int]) -> float:
        """
        Calculate normalized citations per year since publication.
        
        Args:
            citations: Number of citations
            pub_year: Publication year
            
        Returns:
            Normalized citations (citations per year), 0.0 if calculation not possible
        """
        if not citations or not pub_year:
            return 0.0
        
        # Get current year
        import datetime
        current_year = datetime.datetime.now().year
        
        # Calculate years since publication
        years_since_publication = current_year - pub_year
        
        # If published this year or in future, use 1 year to avoid division by zero
        if years_since_publication <= 0:
            years_since_publication = 1
        
        # Calculate normalized citations (citations per year)
        normalized = citations / years_since_publication
        
        return round(normalized, 2)