#!/usr/bin/env python3
"""Standalone network generation CLI for co-citation-assist."""

import typer
import json
import logging
from pathlib import Path
from typing_extensions import Annotated
from typing import Optional

from .network_generator import NetworkGenerator, LinkingMode

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main(
    citations_file: Annotated[Path,
        typer.Argument(
            help="Path to the detailed_references_citations.json file.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        )
    ],
    output_file: Annotated[Optional[Path],
        typer.Option(
            "-o", "--output",
            help="Output path for the network JSON file (default: network.json in same directory as input).",
        )
    ] = None,
    mode: Annotated[LinkingMode,
        typer.Option(
            "--mode",
            help="Linking mode for network generation.",
        )
    ] = LinkingMode.BIBLIOGRAPHIC_COUPLING,
    min_strength: Annotated[int,
        typer.Option(
            "--min-strength",
            help="Minimum link strength to include in network (default: 1).",
            min=1,
        )
    ] = 1,
    max_nodes: Annotated[Optional[int],
        typer.Option(
            "--max-nodes",
            help="Maximum number of nodes to include in network (default: no limit).",
            min=1,
        )
    ] = None,
    detailed_metadata: Annotated[bool,
        typer.Option(
            "--detailed-metadata",
            help="Fetch detailed metadata (abstracts, keywords, etc.) from OpenAlex API. Basic metadata (title, authors, year) is always fetched.",
        )
    ] = False,
    include_cociting_nodes: Annotated[bool,
        typer.Option(
            "--include-cociting-nodes",
            help="Include co-citing papers as nodes in co-citation networks (papers that cite the core papers together).",
        )
    ] = False,
    amsler_lambda: Annotated[float,
        typer.Option(
            "--amsler-lambda",
            help="Lambda weight for Amsler similarity (bibliographic coupling component). Range: 0.0-1.0. Only used with --mode amsler.",
            min=0.0,
            max=1.0,
        )
    ] = 0.5,
):
    """
    Generate a network structure from detailed citations JSON file.
    
    Creates a VOSGraph-compatible network JSON file showing relationships between papers
    based on the specified linking mode and strength parameters.
    
    Example usage:
    
    # Basic bibliographic coupling network
    python -m co_citation_assist.network_cli output/detailed_references_citations.json
    
    # Co-citation network with minimum strength of 3
    python -m co_citation_assist.network_cli output/detailed_references_citations.json --mode co_citation --min-strength 3
    
    # Amsler similarity network with custom lambda weighting
    python -m co_citation_assist.network_cli output/detailed_references_citations.json --mode amsler --amsler-lambda 0.7
    
    # Limit to 100 nodes with detailed metadata
    python -m co_citation_assist.network_cli output/detailed_references_citations.json --max-nodes 100 --detailed-metadata
    """
    # Set default output file if not provided
    if output_file is None:
        mode_name = mode.value.replace(" ", "_")
        output_file = citations_file.parent / f"network_{mode_name}.json"
    
    # Ensure output directory exists
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Generating network from: {citations_file}")
    print(f"Mode: {mode.value}")
    print(f"Minimum link strength: {min_strength}")
    if max_nodes:
        print(f"Maximum nodes: {max_nodes}")
    print("Fetching metadata from OpenAlex API (this may take some time)...")
    
    try:
        # Initialize network generator
        generator = NetworkGenerator()
        
        # Load citations data
        with citations_file.open('r', encoding='utf-8') as f:
            citations_data = json.load(f)
        
        print(f"Loaded data with {len(citations_data)} papers")
        
        # Note: Always fetch basic metadata; detailed_metadata flag for future use
        if detailed_metadata:
            print("Note: Detailed metadata fetching is planned for future implementation.")
        
        # Generate network
        network_data = generator.generate_network(
            citations_data=citations_data,
            mode=mode,
            min_strength=min_strength,
            max_nodes=max_nodes,
            include_cociting_nodes=include_cociting_nodes,
            amsler_lambda=amsler_lambda
        )
        
        # Write network file
        with output_file.open('w', encoding='utf-8') as f:
            json.dump(network_data, f, indent=2, ensure_ascii=False)
        
        # Print summary
        num_nodes = len(network_data.get("network", {}).get("items", []))
        num_links = len(network_data.get("network", {}).get("links", []))
        print(f"\nNetwork generated successfully:")
        print(f"  Nodes: {num_nodes}")
        print(f"  Links: {num_links}")
        print(f"  Output: {output_file}")
        
        if num_links == 0:
            print("\nNote: No links were generated. This could mean:")
            print("- The minimum strength threshold is too high")
            print("- There are insufficient overlaps in the data")
            print("- Try reducing --min-strength or increasing --max-nodes")
        
    except Exception as e:
        logger.error(f"Failed to generate network: {e}", exc_info=True)
        print(f"Error: Failed to generate network. {e}")
        raise typer.Exit(code=1)

if __name__ == "__main__":
    typer.run(main)