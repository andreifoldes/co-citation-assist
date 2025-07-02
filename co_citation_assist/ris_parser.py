import re
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)

def parse_ris_file(file_path: Path) -> List[Dict[str, str]]:
    """
    Parses a RIS file and extracts records.

    Handles potential BOM, common RIS line formats, and basic multi-line fields.

    Args:
        file_path: Path to the RIS file.

    Returns:
        A list of dictionaries, where each dictionary represents a record
        and keys are RIS tags (e.g., 'TY', 'TI', 'DO').
        Returns an empty list if the file cannot be parsed or found.
    """
    records = []
    current_record = {}
    # RIS format: TY<space><space>-<space>VALUE
    # Regex: matches start, 2 alphanumeric chars OR 'ER', 2 spaces, hyphen, optional space, capture rest
    ris_line_regex = re.compile(r"^([A-Z0-9]{2}|ER)\s{2}-\s?(.*)$")

    try:
        # Use utf-8-sig to handle potential Byte Order Mark (BOM)
        with open(file_path, 'r', encoding='utf-8-sig') as f:
            last_tag = None # Keep track of the last tag for multi-line fields
            for line in f:
                line = line.strip()
                if not line:
                    continue # Skip empty lines

                match = ris_line_regex.match(line)
                if match:
                    tag, value = match.groups()
                    tag = tag.strip()
                    value = value.strip()
                    last_tag = tag # Update last tag

                    if tag == 'ER': # End of Record tag
                        if current_record:
                            # Clean up potential empty values before appending
                            cleaned_record = {k: v for k, v in current_record.items() if v}
                            if cleaned_record:
                                records.append(cleaned_record)
                        current_record = {} # Reset for the next record
                        last_tag = None
                    elif value: # Only process if value is not empty
                        # Basic multi-line handling: append to existing key with newline
                        if tag in current_record:
                            current_record[tag] += "\n" + value
                        else:
                            current_record[tag] = value
                # Handle continuation lines (lines not matching the regex but belonging to the last tag)
                # Heuristic: if a line doesn't match the tag format and we have a last_tag
                # and that tag is already in current_record, append it.
                # Be cautious with this - might incorrectly merge unrelated lines.
                # Common for AB (Abstract) or N1 (Notes).
                elif last_tag and last_tag in current_record and last_tag != 'ER':
                    # Append with a space or newline? Space might be safer for most text.
                    current_record[last_tag] += " " + line

                # Handle 'ER' tag even if it doesn't perfectly match the regex (e.g., inconsistent spacing)
                elif line.strip() == 'ER':
                    if current_record:
                        cleaned_record = {k: v for k, v in current_record.items() if v}
                        if cleaned_record:
                            records.append(cleaned_record)
                    current_record = {}
                    last_tag = None

        # Add the last record if the file doesn't end with an 'ER' tag
        if current_record:
            cleaned_record = {k: v for k, v in current_record.items() if v}
            if cleaned_record:
                records.append(cleaned_record)

    except FileNotFoundError:
        logger.error(f"Error: RIS file not found at {file_path}")
        return []
    except Exception as e:
        logger.error(f"Error parsing RIS file {file_path}: {e}", exc_info=True) # Log traceback
        return []

    logger.info(f"Parsed {len(records)} records from {file_path.name}")
    return records


def extract_dois_from_ris(file_path: Path) -> List[str]:
    """
    Extracts unique DOIs from a RIS file.

    Handles common DOI tags ('DO', 'DI') and attempts basic validation
    and cleanup (lowercase, checks for '10.' prefix and '/').
    Now takes the full value from the DO/DI field without complex regex.

    Args:
        file_path: Path to the RIS file.

    Returns:
        A list of unique, lowercased DOIs found in the file.
        Returns an empty list if parsing fails or no DOIs are found.
    """
    records = parse_ris_file(file_path)
    if not records:
        return []

    dois = set()
    doi_keys = ("DO", "DI") # Common RIS tags for DOI

    for record in records:
        found_doi_in_record = None
        for key in doi_keys:
            if key in record and record[key]:
                potential_doi = record[key].strip()
                # Basic validation: starts with '10.' and contains '/'
                if potential_doi.startswith('10.') and '/' in potential_doi:
                    found_doi_in_record = potential_doi.lower() # Normalize to lowercase
                    # Optional: Clean up potential extra text? For now, assume the field contains only the DOI.
                    # Example: If field was "DOI: 10.xxxx/yyyy", this would fail.
                    # A slightly more robust check could try splitting on space and taking the last part.
                    parts = found_doi_in_record.split()
                    if len(parts) > 1 and parts[-1].startswith('10.'):
                         found_doi_in_record = parts[-1]

                    logger.debug(f"Found potential DOI '{found_doi_in_record}' in record field {key}")
                    break # Found a DOI using this key, move to next record
                else:
                    logger.debug(f"Value '{potential_doi}' in field {key} did not look like a DOI.")

        if found_doi_in_record:
            dois.add(found_doi_in_record)
        else:
            # Log records where no DOI was found
            title = record.get('TI', record.get('T1', '<No Title Found>'))
            logger.warning(f"No valid DOI found in record: {title[:60]}...")

    logger.info(f"Extracted {len(dois)} unique DOIs from {len(records)} records.")
    return list(dois)


def extract_mag_ids_from_ris(file_path: Path) -> List[str]:
    """
    Extracts unique Microsoft Academic Graph (MAG) IDs from a RIS file.
    
    Looks for MAG IDs in KW fields with format 'mag:XXXXXXXX'.
    
    Args:
        file_path: Path to the RIS file.
    
    Returns:
        A list of unique MAG IDs found in the file.
        Returns an empty list if parsing fails or no MAG IDs are found.
    """
    records = parse_ris_file(file_path)
    if not records:
        return []
    
    mag_ids = set()
    
    for record in records:
        if 'KW' in record and record['KW']:
            kw_field = record['KW'].strip()
            # Split KW field by newlines and check each line for mag: prefix
            for kw_line in kw_field.split('\n'):
                kw_line = kw_line.strip()
                if kw_line.startswith('mag:'):
                    mag_id = kw_line[4:]  # Remove 'mag:' prefix
                    if mag_id.isdigit():  # Basic validation - MAG IDs are numeric
                        mag_ids.add(mag_id)
                        logger.debug(f"Found MAG ID '{mag_id}' in record KW field")
                    else:
                        logger.debug(f"Value '{kw_line}' in KW field did not look like a valid MAG ID.")
        
        if not mag_ids:
            # Log records where no MAG ID was found (only if no DOI either)
            title = record.get('TI', record.get('T1', '<No Title Found>'))
            has_doi = any(key in record and record[key] for key in ('DO', 'DI'))
            if not has_doi:
                logger.debug(f"No MAG ID or DOI found in record: {title[:60]}...")
    
    logger.info(f"Extracted {len(mag_ids)} unique MAG IDs from {len(records)} records.")
    return list(mag_ids)


def extract_identifiers_from_ris(file_path: Path) -> tuple[List[str], List[str]]:
    """
    Extracts both DOIs and MAG IDs from a RIS file.
    
    Args:
        file_path: Path to the RIS file.
    
    Returns:
        A tuple of (dois, mag_ids) lists.
    """
    records = parse_ris_file(file_path)
    if not records:
        return [], []
    
    dois = set()
    mag_ids = set()
    doi_keys = ("DO", "DI")
    
    for record in records:
        found_doi = None
        found_mag_id = None
        
        # Try to extract DOI first
        for key in doi_keys:
            if key in record and record[key]:
                potential_doi = record[key].strip()
                if potential_doi.startswith('10.') and '/' in potential_doi:
                    found_doi = potential_doi.lower()
                    parts = found_doi.split()
                    if len(parts) > 1 and parts[-1].startswith('10.'):
                        found_doi = parts[-1]
                    logger.debug(f"Found DOI '{found_doi}' in record field {key}")
                    break
        
        # If no DOI found, try to extract MAG ID from KW field
        if not found_doi and 'KW' in record and record['KW']:
            kw_field = record['KW'].strip()
            for kw_line in kw_field.split('\n'):
                kw_line = kw_line.strip()
                if kw_line.startswith('mag:'):
                    mag_id = kw_line[4:]
                    if mag_id.isdigit():
                        found_mag_id = mag_id
                        logger.debug(f"Found MAG ID '{found_mag_id}' in record KW field")
                        break
        
        # Add to respective sets
        if found_doi:
            dois.add(found_doi)
        elif found_mag_id:
            mag_ids.add(found_mag_id)
        else:
            title = record.get('TI', record.get('T1', '<No Title Found>'))
            logger.warning(f"No valid DOI or MAG ID found in record: {title[:60]}...")
    
    logger.info(f"Extracted {len(dois)} unique DOIs and {len(mag_ids)} unique MAG IDs from {len(records)} records.")
    return list(dois), list(mag_ids) 