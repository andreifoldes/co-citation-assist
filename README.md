# Co-Citation Assist (cca)

`cca` is a command-line tool to perform backward and forward co-citation analysis using academic APIs like OpenAlex. Given an initial set of papers (in RIS format), it helps identify potentially novel or related research by finding:

1.  **Backward Co-Citation (Shared References):** Papers that are frequently referenced *by* the initial set.
2.  **Forward Co-Citation (Shared Citations):** Papers that frequently cite *members of* the initial set.

## Features

*   Parses `.ris` files to extract DOIs for the initial paper set.
*   Uses the [OpenAlex](https://openalex.org/) API via the `pyalex` library to retrieve citation data.
*   Performs backward co-citation analysis based on a configurable threshold (N).
*   Performs forward co-citation analysis based on a configurable threshold (M).
*   Outputs results into structured CSV and JSON files within an `output/` directory.
    *   `output/summary.csv`: Provides a summary of references and citations found for each initial DOI.
    *   `output/backward.csv`: Lists novel papers found through backward analysis and the initial papers that cite them.
    *   `output/forward.csv`: Lists novel papers found through forward analysis and the initial papers they cite.
    *   `output/detailed_references_citations.json`: Contains the raw lists of reference and citation DOIs fetched for each initial paper.

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

While the tool can work without an email address, providing one helps OpenAlex track API usage and maintain service quality. You can configure an email in one of two ways:

1.  **Environment Variable:**
    Set the `OPENALEX_EMAIL` environment variable:
    ```bash
    export OPENALEX_EMAIL="your.email@example.com" 
    ```
    (Add this to your `.bashrc`, `.zshrc`, or equivalent shell configuration file for persistence).

2.  **`.env` File:**
    Create a file named `.env` in the directory *where you run the `cca` command* (or in the project root if running from source). Add the following line:
    ```
    OPENALEX_EMAIL=your.email@example.com
    ```
    *Note: An `example.env` file is provided in the repository. You can copy it to `.env` and add your email.*

## Tutorial: Running an Analysis

Let's run a sample analysis using the provided `testing/displacement-mnr.ris` file.

**Important Note:** For best results, ensure the DOIs in your `.ris` file are accurate. We recommend validating the DOIs in your reference manager (like Zotero) *before* exporting the `.ris` file. Plugins like the [Zotero DOI Manager](https://github.com/bwiernik/zotero-shortdoi) [[1]](https://github.com/bwiernik/zotero-shortdoi) can help automate DOI validation and cleaning.

1.  **Navigate to the project directory** (if you cloned it) or ensure the `testing/displacement-mnr.ris` file is accessible from your current directory.
2.  **Run the `cca` command:**

    ```bash
    cca testing/displacement-mnr.ris -n 2 -m 2
    ```

**Explanation of the command:**

*   `cca`: The command-line tool itself.
*   `testing/displacement-mnr.ris`: The path to the input RIS file containing the initial set of papers.
*   `-n 2`: Sets the backward co-citation threshold (N) to 2. This means we are looking for papers that are referenced by *at least 2* papers in the initial set.
*   `-m 2`: Sets the forward co-citation threshold (M) to 2. This means we are looking for papers that cite *at least 2* papers in the initial set.

**Expected Process:**

*   The tool will parse the `.ris` file and extract the DOIs.
*   It will create an `output/` directory in the current working directory if it doesn't exist.
*   It will then contact the OpenAlex API to fetch references for each initial DOI (for backward analysis, if n>0) and citations for each initial DOI (for forward analysis, if m>0). This may take some time depending on the number of initial papers and their citation counts.
*   It will analyze the collected data to find papers meeting the `-n` and `-m` thresholds.
*   Finally, it will save the results into four files within the `output/` directory.

**Output Files (in `output/` directory):**

*   **`summary.csv`**: 
    *   Contains one row per initial DOI processed.
    *   Columns: `doi`, `references_found`, `citations_found`, `api`, `retrieval_timestamp`.
    *   Provides a high-level overview of the data fetched for each input paper.
*   **`backward.csv`** (created if n > 0):
    *   Lists the relationships for papers identified through backward co-citation.
    *   Columns: `novel_doi`, `initial_citing_doi`.
    *   Each row indicates that `initial_citing_doi` (from the input set) references `novel_doi` (the paper identified).
*   **`forward.csv`** (created if m > 0):
    *   Lists the relationships for papers identified through forward co-citation.
    *   Columns: `novel_doi`, `initial_cited_doi`.
    *   Each row indicates that `novel_doi` (the paper identified) cites `initial_cited_doi` (from the input set).
*   **`detailed_references_citations.json`**:
    *   A JSON object where keys are the DOIs from the initial input set.
    *   Each value is another object containing two keys: `references` and `citations`.
    *   The value associated with `references` is a list of DOIs referenced by the initial DOI (or `null` if none found/error).
    *   The value associated with `citations` is a list of DOIs that cite the initial DOI (or `null` if none found/error).

You can adjust the `-n` and `-m` values to control the strictness of the analysis. Setting a threshold to `0` will skip that part of the analysis and prevent the corresponding CSV file (`backward.csv` or `forward.csv`) from being created.

**Interpreting the Results:**

After the analysis completes, it's worth examining `output/summary.csv`. Look for rows where `references_found` or `citations_found` is 0. 

*   A value of 0 might indicate that the paper truly has no references or citations recorded in the OpenAlex database.
*   However, it could also mean the specific DOI wasn't found or indexed correctly by OpenAlex at the time of the query, but that data could exist in other academic databases (like Scopus, Web of Science, etc.).
*   You can use the list of DOIs with 0 counts from `summary.csv` to manually check these papers in other databases or search engines (like Google Scholar).
*   The `output/detailed_references_citations.json` file provides a record of exactly what was (or wasn't) retrieved from OpenAlex for each initial DOI during the run.

## Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request.

## License

This project is licensed under the MIT License - see the `LICENSE` file for details.

## References

[1] Brenton M. Wiernik. *zotero-shortdoi* (Version v1.5.0). GitHub Repository. https://github.com/bwiernik/zotero-shortdoi (Accessed [Date]) 