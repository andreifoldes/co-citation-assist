# Co-Citation Assist (cca)

`cca` is a command-line tool to perform backward and forward co-citation analysis using academic APIs like OpenAlex. Given an initial set of papers (in RIS format), it helps identify potentially novel or related research by finding:

1.  **Backward Co-Citation (Shared References):** Papers that are frequently referenced *by* the initial set.
2.  **Forward Co-Citation (Shared Citations):** Papers that frequently cite *members of* the initial set.

## Features

*   Parses `.ris` files to extract DOIs for the initial paper set, or accepts DOIs directly via command line.
*   Uses multiple academic APIs for comprehensive citation data:
    *   [OpenAlex](https://openalex.org/) API via the `pyalex` library
    *   [Semantic Scholar](https://www.semanticscholar.org/) Academic Graph API
    *   Composite API mode that combines results from both sources
*   Performs backward co-citation analysis based on a configurable threshold (N).
*   Performs forward co-citation analysis based on a configurable threshold (M).
*   Base-only mode for data collection without co-citation analysis using the `--base-only` flag.
*   Outputs results into structured CSV and JSON files within an `output/` directory:
    *   `output/summary.csv`: Provides a summary of references and citations found for each initial DOI.
    *   `output/backward.csv`: Lists novel papers found through backward analysis and the initial papers that cite them (created when n > 0).
    *   `output/forward.csv`: Lists novel papers found through forward analysis and the initial papers they cite (created when m > 0).
    *   `output/detailed_references_citations.json`: Contains the raw lists of reference and citation DOIs fetched for each initial paper.
    *   `output/cli.log`: Complete execution log with detailed API calls, timing, and debugging information.

## Installation

Ensure you have Python 3.8 or higher installed.

1.  **(Optional) Install uv:**
    If you don't have `uv` installed, you can install it using pip or other methods described in the [uv documentation](https://github.com/astral-sh/uv#installation):
    ```bash
    pip install uv 
    ```
    *Or check the official guide for preferred installation methods.*

2.  **Clone the repository (Optional, if not installing from PyPI):**
    ```bash
    git clone <repository-url> # Replace with the actual URL
    cd co-citation-assist
    ```

3.  **Create and Activate a Virtual Environment:**
    It's highly recommended to install Python packages in a virtual environment. You can create one using `uv`:
    ```bash
    # Create a virtual environment named .venv in the current directory
    uv venv 
    ```
    Then, activate it:
    *   **Linux/macOS (bash/zsh):**
        ```bash
        source .venv/bin/activate
        ```
    *   **Windows (Command Prompt):**
        ```cmd
        .venv\Scripts\activate.bat
        ```
    *   **Windows (PowerShell):**
        ```powershell
        .venv\Scripts\Activate.ps1
        ```
    You should see the environment name (e.g., `(.venv)`) appear at the beginning of your terminal prompt.

4.  **Install the package using uv:**
    *   **From the local clone (ensure your virtual environment is active):**
        ```bash
        uv pip install .
        ```
    *   **Directly from GitHub:**
        ```bash
        uv pip install git+https://github.com/andreifoldes/co-citation-assist.git # Replace with the actual URL
        ```

This will install the `cca` command-line tool and its dependencies (`typer`, `pyalex`) using `uv`.

## Configuration (Optional)

The tool supports configuration for both OpenAlex and Semantic Scholar APIs:

### OpenAlex Configuration
While the tool can work without an email address, providing one helps OpenAlex track API usage and maintain service quality:

1.  **Environment Variable:**
    ```bash
    export OPENALEX_EMAIL="your.email@example.com" 
    ```

2.  **`.env` File:**
    Create a `.env` file in the directory where you run the `cca` command:
    ```
    OPENALEX_EMAIL=your.email@example.com
    ```

### Semantic Scholar Configuration (Recommended)
For better rate limits and reliability, configure a Semantic Scholar API key:

1.  **Get an API Key:**
    Request a free API key from [Semantic Scholar](https://www.semanticscholar.org/product/api#api-key-form)

2.  **Environment Variable:**
    ```bash
    export SEMANTIC_SCHOLAR_API_KEY="your-api-key-here"
    ```

3.  **`.env` File:**
    Add to your `.env` file:
    ```
    OPENALEX_EMAIL=your.email@example.com
    SEMANTIC_SCHOLAR_API_KEY=your-api-key-here
    ```

*Note: An `example.env` file is provided in the repository. You can copy it to `.env` and add your credentials.*

## Tutorial: Running an Analysis

Let's run a sample analysis using the provided `testing/tiab_screening_results.ris` file.

**Important Note:** For best results, ensure the DOIs in your `.ris` file are accurate. We recommend validating the DOIs in your reference manager (like Zotero) *before* exporting the `.ris` file. Plugins like the [Zotero DOI Manager](https://github.com/bwiernik/zotero-shortdoi) [[1]](https://github.com/bwiernik/zotero-shortdoi) can help automate DOI validation and cleaning.

1.  **Navigate to the project directory** (if you cloned it) or ensure the `testing/tiab_screening_results.ris` file is accessible from your current directory.
2.  **Run the `cca` command:**

    ```bash
    # Standard co-citation analysis
    cca testing/tiab_screening_results.ris -n 2 -m 2
    
    # Base-only mode (data collection without analysis)
    cca testing/tiab_screening_results.ris --base-only
    
    # Using DOIs directly instead of RIS file
    cca --doi 10.1000/example1 --doi 10.1000/example2 -n 2 -m 2
    
    # Skip backward analysis (only forward)
    cca testing/tiab_screening_results.ris -n 0 -m 2
    
    # Skip forward analysis (only backward)
    cca testing/tiab_screening_results.ris -n 2 -m 0
    ```

**Explanation of the command options:**

*   `cca`: The command-line tool itself.
*   `testing/tiab_screening_results.ris`: The path to the input RIS file containing the initial set of papers.
*   `-n 2`: Sets the backward co-citation threshold (N) to 2. This means we are looking for papers that are referenced by *at least 2* papers in the initial set.
*   `-m 2`: Sets the forward co-citation threshold (M) to 2. This means we are looking for papers that cite *at least 2* papers in the initial set.
*   `--base-only`: Collects references and citations data without performing co-citation analysis.
*   `--doi`: Specify DOI(s) directly instead of using a RIS file (can be used multiple times).

**Expected Process:**

*   The tool will parse the `.ris` file and extract the DOIs (or use DOIs provided via `--doi` options).
*   It will create an `output/` directory in the current working directory if it doesn't exist.
*   It will contact academic APIs to fetch references and citations for each initial DOI:
    *   By default, uses a composite approach querying both OpenAlex and Semantic Scholar APIs
    *   Combines results from multiple sources to maximize data coverage
    *   This may take some time depending on the number of initial papers and their citation counts
*   If not using `--base-only`, it will analyze the collected data to find papers meeting the `-n` and `-m` thresholds.
*   Finally, it will save the results into CSV and JSON files within the `output/` directory, plus a detailed execution log.

**Output Files (in `output/` directory):**

*   **`summary.csv`**: 
    *   Contains one row per initial DOI processed.
    *   Columns: `doi`, `references_found`, `citations_found`, `api`, `retrieval_timestamp`.
    *   Provides a high-level overview of the data fetched for each input paper.
    *   In composite API mode, shows combined results from multiple sources.
*   **`backward.csv`** (created if n > 0 and not using `--base-only`):
    *   Lists the relationships for papers identified through backward co-citation.
    *   Columns: `novel_doi`, `initial_citing_doi`.
    *   Each row indicates that `initial_citing_doi` (from the input set) references `novel_doi` (the paper identified).
*   **`forward.csv`** (created if m > 0 and not using `--base-only`):
    *   Lists the relationships for papers identified through forward co-citation.
    *   Columns: `novel_doi`, `initial_cited_doi`.
    *   Each row indicates that `novel_doi` (the paper identified) cites `initial_cited_doi` (from the input set).
*   **`detailed_references_citations.json`**:
    *   A JSON object where keys are the DOIs from the initial input set.
    *   Each value is another object containing two keys: `references` and `citations`.
    *   The value associated with `references` is a list of DOIs referenced by the initial DOI (or `null` if none found/error).
    *   The value associated with `citations` is a list of DOIs that cite the initial DOI (or `null` if none found/error).
    *   In composite API mode, includes metadata about which APIs contributed to each result.
*   **`cli.log`**:
    *   Complete execution log with timestamps and detailed information about:
        *   API calls made to each service (OpenAlex, Semantic Scholar)
        *   Processing time for each step
        *   Error messages and warnings
        *   DOI validation results
        *   Data overlap statistics (in composite mode)
    *   Useful for debugging issues, understanding performance, and auditing API usage.

You can adjust the `-n` and `-m` values to control the strictness of the analysis. Setting a threshold to `0` will skip that part of the analysis and prevent the corresponding CSV file (`backward.csv` or `forward.csv`) from being created.

## Network Generation

After completing a co-citation analysis, you can generate network visualizations from the collected data using the `network_cli` module:

```bash
# Generate bibliographic coupling network (papers linked by shared references)
python -m co_citation_assist.network_cli output/detailed_references_citations.json

# Generate co-citation network (papers linked by being cited together)
python -m co_citation_assist.network_cli output/detailed_references_citations.json --mode co_citation

# Advanced options: minimum link strength, maximum nodes, custom output
python -m co_citation_assist.network_cli output/detailed_references_citations.json \
  --min-strength 2 --max-nodes 50 -o output/my_network.json
```

**Network Generation Options:**

*   `input_file`: Path to the `detailed_references_citations.json` file from a previous analysis
*   `--mode`: Network type - `bibliographic_coupling` (default) or `co_citation`
    *   **Bibliographic coupling**: Links papers that share references (papers citing the same sources)
    *   **Co-citation**: Links papers that are cited together by other papers
*   `--min-strength`: Minimum number of shared connections required for a link (default: 1)
*   `--max-nodes`: Maximum number of nodes to include in the network (default: 100)
*   `-o, --output`: Custom output file path (default: auto-generated based on mode)

**Network Output:**

*   Generates JSON files with network data suitable for visualization tools
*   Real metadata (title, authors, publication year) is fetched from the OpenAlex API
*   Node labels use format "firstauthor-surname (year)", e.g. "smith (2020)"
*   Output files are named based on the mode:
    *   `network_bibliographic_coupling.json`
    *   `network_co_citation.json`
*   Compatible with network visualization tools like Gephi, Cytoscape, or web-based libraries

**Interpreting the Results:**

After the analysis completes, examine the output files to understand your results:

**1. Check `output/summary.csv`** - Look for rows where `references_found` or `citations_found` is 0:
*   A value of 0 might indicate that the paper truly has no references or citations recorded in the academic databases.
*   However, it could also mean the specific DOI wasn't found or indexed correctly at the time of the query, but that data could exist in other academic databases (like Scopus, Web of Science, etc.).
*   You can use the list of DOIs with 0 counts to manually check these papers in other databases or search engines (like Google Scholar).

**2. Review `output/cli.log`** - This detailed log file contains:
*   Specific error messages if DOIs couldn't be processed
*   API response details and timing information
*   Data overlap statistics when using composite API mode
*   Validation results for each DOI processed

**3. Examine `output/detailed_references_citations.json`** - This provides a complete record of what was (or wasn't) retrieved from the academic APIs for each initial DOI during the run, including metadata about which APIs contributed data in composite mode.

## Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details.

## References

[1] Brenton M. Wiernik. *zotero-shortdoi* (Version v1.5.0). GitHub Repository. https://github.com/bwiernik/zotero-shortdoi (Accessed [Date]) 