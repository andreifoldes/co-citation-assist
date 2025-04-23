import typer
from pathlib import Path
import logging
from typing_extensions import Annotated
import sys
import csv # Import csv module
import json # Import json module
import os # Import os module for directory creation
import datetime # To potentially use for filenames if needed, but keeping fixed for now

from .ris_parser import extract_dois_from_ris
from .apis.openalex import OpenAlexAPI
from .analyzer import CocitationAnalyzer, SummaryRecord, ResultRecord, RawDataRecord # Import new types

# Application instance
app = typer.Typer(
    name="cca",
    help="Co-Citation Assist: Find relevant papers using backward/forward citation analysis."
)

# Configure basic logging
# TODO: Make log level configurable via CLI option
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

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
    ris_file: Annotated[Path,
        typer.Argument(
            help="Path to the input .ris file containing the initial set of references.",
            exists=True,
            file_okay=True,
            dir_okay=False,
            readable=True,
            resolve_path=True,
        )
    ],
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
    # Removed output_file option
    # TODO: Add option for API choice (e.g., --api openalex)
    # TODO: Add option for log level (e.g., --verbose)
    # TODO: Add option for output directory (use a fixed 'output' for now)
):
    """
    Run co-citation analysis on a given RIS file.

    Outputs results into an 'output/' subdirectory:
    - output/summary.csv: Overview of data fetched for each initial DOI.
    - output/backward.csv: Details of novel papers found via backward analysis (N threshold).
    - output/forward.csv: Details of novel papers found via forward analysis (M threshold).
    - output/detailed_references_citations.json: Raw lists of references/citations for each initial DOI.
    """
    if n_threshold == 0 and m_threshold == 0:
        logger.error("Both N and M thresholds are 0. No analysis will be performed.")
        print("Error: Please specify a non-zero value for -n and/or -m.", file=sys.stderr)
        raise typer.Exit(code=1)

    # Define and create the output directory
    output_dir = Path("./output")
    try:
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Ensured output directory exists: {output_dir.resolve()}")
    except OSError as e:
        logger.critical(f"Failed to create output directory {output_dir}: {e}", exc_info=True)
        print(f"Error: Could not create output directory {output_dir}. Check permissions.", file=sys.stderr)
        raise typer.Exit(code=1)

    logger.info(f"Starting analysis for file: {ris_file}")
    logger.info(f"Backward threshold N = {n_threshold}")
    logger.info(f"Forward threshold M = {m_threshold}")
    logger.info(f"Output files will be saved in: {output_dir.resolve()}")

    # --- Start: Count DO lines and Parse RIS file --- 
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

    # Extract DOIs using the parser
    try:
        initial_dois = set(extract_dois_from_ris(ris_file))
    except Exception as e:
         logger.error(f"Failed to parse RIS file {ris_file}: {e}", exc_info=True)
         print(f"Error: Failed to parse {ris_file}. Check file format and logs.", file=sys.stderr)
         raise typer.Exit(code=1)

    if not initial_dois:
        logger.error(f"No valid DOIs extracted from {ris_file}. Aborting.")
        print(f"Error: Could not extract any valid DOIs from {ris_file}. Please check the file format and content.", file=sys.stderr)
        raise typer.Exit(code=1)
    
    extracted_doi_count = len(initial_dois)
    print(f"Found {extracted_doi_count} unique DOIs in the initial set.")

    # Warn user if extracted count is much lower than DO line count
    if do_line_count > 0 and extracted_doi_count < do_line_count * 0.9: # Example threshold: < 90%
        logger.warning(
            f"Parser extracted {extracted_doi_count} unique DOIs, but found {do_line_count} potential DOI lines ('DO','DI'). "
            f"Some entries might have been missed, are duplicates, or invalid."
        )
        print(
            f"Warning: Extracted {extracted_doi_count} unique DOIs, but found {do_line_count} potential DOI lines. "
            f"Check logs or input file if this seems incorrect."
        )
    # --- End: Count DO lines and Parse RIS file --- 

    # 2. Initialize API Client and Analyzer
    print("\nInitializing API client...")
    try:
        # Currently hardcoded to OpenAlex
        api_client = OpenAlexAPI()
        analyzer = CocitationAnalyzer(api_client, initial_dois)
    except Exception as e:
        logger.critical(f"Failed to initialize API client or Analyzer: {e}", exc_info=True)
        print(f"Error: Failed to initialize API client: {e}", file=sys.stderr)
        raise typer.Exit(code=1)


    # 3. Run Analysis (Single Call)
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
    summary_fieldnames = ['doi', 'references_found', 'citations_found', 'api', 'retrieval_timestamp']
    write_csv(output_dir / "summary.csv", summary_data, summary_fieldnames)

    # Write Backward CSV
    if n_threshold > 0:
        backward_fieldnames = ['novel_doi', 'initial_citing_doi']
        write_csv(output_dir / "backward.csv", backward_results, backward_fieldnames)
    else:
        logger.info("Skipping backward.csv creation as N=0.")
        print("Backward analysis skipped (N=0).")


    # Write Forward CSV
    if m_threshold > 0:
        forward_fieldnames = ['novel_doi', 'initial_cited_doi']
        write_csv(output_dir / "forward.csv", forward_results, forward_fieldnames)
    else:
        logger.info("Skipping forward.csv creation as M=0.")
        print("Forward analysis skipped (M=0).")

    # Write Detailed JSON
    write_json(output_dir / "detailed_references_citations.json", raw_data)

    print("\nAnalysis finished.")

# Entry point for the script defined in pyproject.toml
def main():
    app()

if __name__ == "__main__":
    main() 