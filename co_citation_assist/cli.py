import typer
from pathlib import Path
import logging
from typing_extensions import Annotated
from typing import List, Dict, Optional
import sys
import csv # Import csv module
import json # Import json module
import os # Import os module for directory creation
import datetime # To potentially use for filenames if needed, but keeping fixed for now

from .ris_parser import extract_dois_from_ris, extract_identifiers_from_ris
from .apis.composite import CompositeAPI
from .analyzer import CocitationAnalyzer, SummaryRecord, ResultRecord, RawDataRecord, Doi # Import new types

# Application instance
app = typer.Typer(
    name="cca",
    help="Co-Citation Assist: Find relevant papers using backward/forward citation analysis."
)

# Configure basic logging (console only initially)
# TODO: Make log level configurable via CLI option
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def setup_file_logging(output_dir: Path):
    """Add file handler to save logs to output directory."""
    log_file = output_dir / "cli.log"
    file_handler = logging.FileHandler(log_file, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    
    # Add to root logger to capture all logs
    root_logger = logging.getLogger()
    root_logger.addHandler(file_handler)
    
    logger.info(f"CLI log will be saved to: {log_file}")
    return log_file

def write_csv(filepath: Path, data: list, fieldnames: list):
    """Helper function to write a list of dictionaries to a CSV file."""
    filename = filepath.name # For logging/printing
    if not data:
        logger.info(f"No data to write for {filename}. Skipping file creation.")
        print(f"No results found for {filename}.")
        return
    
    try:
        # Use the full Path object to open the file
        with filepath.open('w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"Successfully wrote {len(data)} rows to {filepath}")
        print(f"Results saved to: {filepath}")
    except IOError as e:
        logger.error(f"Failed to write to {filepath}: {e}")
        print(f"Error: Could not write results to {filepath}. Check permissions.", file=sys.stderr)
    except Exception as e:
        logger.error(f"An unexpected error occurred while writing {filepath}: {e}", exc_info=True)
        print(f"Error: An unexpected error occurred while writing {filepath}.", file=sys.stderr)

def validate_doi(doi: str) -> bool:
    """Validate a DOI string using the same logic as the RIS parser."""
    return doi.startswith('10.') and '/' in doi

def process_doi_input(doi: str) -> str:
    """Process and clean a DOI input string."""
    doi = doi.strip()
    # Handle potential prefixes like "doi:", "DOI:", "https://doi.org/"
    if doi.lower().startswith('doi:'):
        doi = doi[4:].strip()
    elif doi.lower().startswith('https://doi.org/'):
        doi = doi[16:].strip()
    elif doi.lower().startswith('http://doi.org/'):
        doi = doi[15:].strip()
    elif doi.lower().startswith('https://dx.doi.org/'):
        doi = doi[19:].strip()
    elif doi.lower().startswith('http://dx.doi.org/'):
        doi = doi[18:].strip()
    
    return doi.lower()

def write_json(filepath: Path, data: dict):
    """Helper function to write a dictionary to a JSON file."""
    filename = filepath.name # For logging/printing
    try:
        with filepath.open('w', encoding='utf-8') as jsonfile:
            # Use indent for readability
            json.dump(data, jsonfile, indent=4)
        logger.info(f"Successfully wrote detailed data to {filepath}")
        print(f"Detailed references/citations saved to: {filepath}")
    except IOError as e:
        logger.error(f"Failed to write to {filepath}: {e}")
        print(f"Error: Could not write results to {filepath}. Check permissions.", file=sys.stderr)
    except Exception as e:
        logger.error(f"An unexpected error occurred while writing {filepath}: {e}", exc_info=True)
        print(f"Error: An unexpected error occurred while writing {filepath}.", file=sys.stderr)

@app.command()
def run(
    ris_file: Annotated[Optional[Path],
        typer.Argument(
            help="Path to the input .ris file containing the initial set of references.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        )
    ] = None,
    n_threshold: Annotated[int,
        typer.Option(
            "-n",
            help="Minimum number (N) of initial papers that must reference a paper (for backward analysis). Set to 0 to skip.",
            min=0,
        )
    ] = 2,
    m_threshold: Annotated[int,
        typer.Option(
            "-m",
            help="Minimum number (M) of initial papers that must be cited by a paper (for forward analysis). Set to 0 to skip.",
            min=0,
        )
    ] = 2,
    base_only: Annotated[bool,
        typer.Option(
            "--base-only",
            help="Only collect references and citations data without performing co-citation analysis. Outputs only summary.csv and detailed_references_citations.json.",
        )
    ] = False,
    dois: Annotated[Optional[List[str]],
        typer.Option(
            "--doi",
            help="DOI(s) to analyze directly (can be specified multiple times). Use instead of RIS file.",
        )
    ] = None,
    # Removed output_file option
    # TODO: Add option for API choice (e.g., --api openalex)
    # TODO: Add option for log level (e.g., --verbose)
    # TODO: Add option for output directory (use a fixed 'output' for now)
):
    """
    Run co-citation analysis or base data collection on a given RIS file or DOI(s).

    Input options:
    - Provide a RIS file path as the first argument
    - Use --doi option to specify DOI(s) directly (can be used multiple times)

    In standard mode, outputs results into an 'output/' subdirectory:
    - output/summary.csv: Overview of data fetched for each initial DOI.
    - output/backward.csv: Details of novel papers found via backward analysis (N threshold).
    - output/forward.csv: Details of novel papers found via forward analysis (M threshold).
    - output/detailed_references_citations.json: Raw lists of references/citations for each initial DOI.
    - output/cli.log: Complete log of the CLI execution.

    In base-only mode (--base-only), outputs only:
    - output/summary.csv: Overview of data fetched for each initial DOI.
    - output/detailed_references_citations.json: Raw lists of references/citations for each initial DOI.
    - output/cli.log: Complete log of the CLI execution.
    """
    # Validate input - must provide either RIS file or DOIs
    if not ris_file and not dois:
        logger.error("No input provided. Must specify either RIS file or DOI(s).")
        print("Error: Please provide either a RIS file path or use --doi to specify DOI(s).", file=sys.stderr)
        raise typer.Exit(code=1)
    
    if ris_file and dois:
        logger.error("Cannot specify both RIS file and DOI options.")
        print("Error: Please use either RIS file OR --doi option, not both.", file=sys.stderr)
        raise typer.Exit(code=1)

    if not base_only and n_threshold == 0 and m_threshold == 0:
        logger.error("Both N and M thresholds are 0. No analysis will be performed.")
        print("Error: Please specify a non-zero value for -n and/or -m, or use --base-only.", file=sys.stderr)
        raise typer.Exit(code=1)

    # Define and create the output directory
    output_dir = Path("./output")
    try:
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Ensured output directory exists: {output_dir.resolve()}")
        
        # Setup file logging now that output directory exists
        log_file = setup_file_logging(output_dir)
        print(f"CLI log will be saved to: {log_file}")
        
    except OSError as e:
        logger.critical(f"Failed to create output directory {output_dir}: {e}", exc_info=True)
        print(f"Error: Could not create output directory {output_dir}. Check permissions.", file=sys.stderr)
        raise typer.Exit(code=1)

    input_source = ris_file.name if ris_file else f"{len(dois)} DOI(s)"
    logger.info(f"Starting analysis for input: {input_source}")
    if base_only:
        logger.info("Running in base-only mode (no co-citation analysis)")
    else:
        logger.info(f"Backward threshold N = {n_threshold}")
        logger.info(f"Forward threshold M = {m_threshold}")
    logger.info(f"Output files will be saved in: {output_dir.resolve()}")

    # --- Start: Process input (RIS file or DOIs) ---
    if ris_file:
        print(f"Parsing RIS file: {ris_file.name}...")

        # Count potential DOI lines first for comparison
        do_line_count = 0
        try:
            # Use utf-8-sig to handle potential BOM
            with ris_file.open('r', encoding='utf-8-sig') as f:
                for line in f:
                    # Adjusted to common RIS DOI tags (DO or DI)
                    tag = line[:2]
                    if tag in ("DO", "DI"): 
                        do_line_count += 1
            logger.debug(f"Found {do_line_count} lines starting with 'DO' or 'DI' in {ris_file.name}")
        except Exception as e:
            logger.warning(f"Could not pre-count DO/DI lines in {ris_file.name}: {e}")
            # Proceed without the count if reading fails here, parser will handle errors later

        # Extract DOIs and MAG IDs using the parser
        try:
            initial_dois, initial_mag_ids = extract_identifiers_from_ris(ris_file)
            initial_dois = set(initial_dois)
            initial_mag_ids = set(initial_mag_ids)
        except Exception as e:
             logger.error(f"Failed to parse RIS file {ris_file}: {e}", exc_info=True)
             print(f"Error: Failed to parse {ris_file}. Check file format and logs.", file=sys.stderr)
             raise typer.Exit(code=1)

        total_identifiers = len(initial_dois) + len(initial_mag_ids)
        if total_identifiers == 0:
            logger.error(f"No valid identifiers extracted from {ris_file}. Aborting.")
            print(f"Error: Could not extract any valid DOIs or MAG IDs from {ris_file}. Please check the file format and content.", file=sys.stderr)
            raise typer.Exit(code=1)
        
        print(f"Found {len(initial_dois)} unique DOIs and {len(initial_mag_ids)} unique MAG IDs in the initial set.")

        # Warn user if extracted count is much lower than DO line count
        if do_line_count > 0 and len(initial_dois) < do_line_count * 0.9: # Example threshold: < 90%
            logger.warning(
                f"Parser extracted {len(initial_dois)} unique DOIs, but found {do_line_count} potential DOI lines ('DO','DI'). "
                f"Some entries might have been missed, are duplicates, or invalid."
            )
            print(
                f"Warning: Extracted {len(initial_dois)} unique DOIs, but found {do_line_count} potential DOI lines. "
                f"Check logs or input file if this seems incorrect."
            )
    else:
        # Process DOI inputs directly
        print(f"Processing {len(dois)} DOI(s)...")
        initial_dois = set()
        initial_mag_ids = set()  # Empty set since we're only processing DOIs directly
        invalid_dois = []
        
        for doi in dois:
            processed_doi = process_doi_input(doi)
            if validate_doi(processed_doi):
                initial_dois.add(processed_doi)
                logger.debug(f"Added DOI: {processed_doi}")
            else:
                invalid_dois.append(doi)
                logger.warning(f"Invalid DOI format: {doi}")
        
        if invalid_dois:
            print(f"Warning: {len(invalid_dois)} invalid DOI(s) were skipped.")
            for invalid_doi in invalid_dois:
                print(f"  - {invalid_doi}")
        
        if not initial_dois:
            logger.error("No valid DOIs provided. Aborting.")
            print("Error: No valid DOIs found. DOIs must start with '10.' and contain '/'.", file=sys.stderr)
            raise typer.Exit(code=1)
            
        total_valid = len(initial_dois) + len(initial_mag_ids)
        print(f"Using {total_valid} valid identifier(s) for analysis ({len(initial_dois)} DOIs, {len(initial_mag_ids)} MAG IDs).")
    # --- End: Process input (RIS file or DOIs) --- 

    # 2. Initialize API Client and Analyzer
    print("\nInitializing API clients (OpenAlex + Semantic Scholar)...")
    try:
        # Use composite API that combines OpenAlex and Semantic Scholar
        api_client = CompositeAPI()
        analyzer = CocitationAnalyzer(api_client, initial_dois, initial_mag_ids)
    except Exception as e:
        logger.critical(f"Failed to initialize API client or Analyzer: {e}", exc_info=True)
        print(f"Error: Failed to initialize API client: {e}", file=sys.stderr)
        raise typer.Exit(code=1)


    # 3. Run Analysis
    if base_only:
        print(f"\nRunning base collection (no co-citation analysis). This may take some time...")
        summary_data: List[SummaryRecord] = []
        raw_data: Dict[Doi, RawDataRecord] = {}
        try:
            summary_data, raw_data = analyzer.run_base_collection()
        except Exception as e:
            logger.critical(f"An unexpected error occurred during base collection: {e}", exc_info=True)
            print(f"\nError during base collection: {e}. Check logs for details.", file=sys.stderr)
            raise typer.Exit(code=1)
        
        # Set empty results for co-citation analysis
        backward_results: List[ResultRecord] = []
        forward_results: List[ResultRecord] = []
    else:
        print(f"\nRunning analysis (N={n_threshold}, M={m_threshold}). This may take some time...")
        summary_data: List[SummaryRecord] = []
        backward_results: List[ResultRecord] = []
        forward_results: List[ResultRecord] = []
        raw_data: Dict[Doi, RawDataRecord] = {}
        try:
            # Unpack the fourth returned value (raw_data)
            summary_data, backward_results, forward_results, raw_data = analyzer.run_analysis(
                min_references_n=n_threshold,
                min_citations_m=m_threshold
            )
        except Exception as e:
             logger.critical(f"An unexpected error occurred during analysis: {e}", exc_info=True)
             print(f"\nError during analysis: {e}. Check logs for details.", file=sys.stderr)
             raise typer.Exit(code=1) # Exit if analysis fails catastrophically

    # 4. Write Results to Files in output_dir
    print("\nWriting results...")

    # Write Summary CSV
    # Define all possible fieldnames including API statistics
    summary_fieldnames = [
        'doi', 'references_found', 'citations_found', 'api', 'retrieval_timestamp',
        'references_OpenAlex', 'references_SemanticScholar', 'references_Overlap',
        'references_OpenAlex_unique', 'references_SemanticScholar_unique', 'references_Total_unique',
        'citations_OpenAlex', 'citations_SemanticScholar', 'citations_Overlap',
        'citations_OpenAlex_unique', 'citations_SemanticScholar_unique', 'citations_Total_unique'
    ]
    write_csv(output_dir / "summary.csv", summary_data, summary_fieldnames)

    # Write Backward CSV (skip in base-only mode)
    if not base_only and n_threshold > 0:
        backward_fieldnames = ['novel_doi', 'initial_citing_doi']
        write_csv(output_dir / "backward.csv", backward_results, backward_fieldnames)
    elif not base_only:
        logger.info("Skipping backward.csv creation as N=0.")
        print("Backward analysis skipped (N=0).")
    else:
        logger.info("Skipping backward.csv creation in base-only mode.")
        print("Backward analysis skipped (base-only mode).")

    # Write Forward CSV (skip in base-only mode)
    if not base_only and m_threshold > 0:
        forward_fieldnames = ['novel_doi', 'initial_cited_doi']
        write_csv(output_dir / "forward.csv", forward_results, forward_fieldnames)
    elif not base_only:
        logger.info("Skipping forward.csv creation as M=0.")
        print("Forward analysis skipped (M=0).")
    else:
        logger.info("Skipping forward.csv creation in base-only mode.")
        print("Forward analysis skipped (base-only mode).")

    # Write Detailed JSON
    write_json(output_dir / "detailed_references_citations.json", raw_data)

    print("\nAnalysis finished.")

# Entry point for the script defined in pyproject.toml
def main():
    app()

if __name__ == "__main__":
    main() 