#!/usr/bin/env python3
"""
Script to fix Unicode escape sequences in JSON files.
Converts \\u sequences back to proper Unicode characters.
"""
import json
import sys
import unicodedata

def normalize_unicode_text(text):
    """Normalize Unicode text to ASCII where possible, keeping readability."""
    if not isinstance(text, str):
        return text
    
    # Decode any escaped Unicode sequences first
    try:
        # Handle escaped Unicode like \u2019
        decoded = text.encode().decode('unicode_escape')
        # Normalize to ASCII where possible
        normalized = unicodedata.normalize('NFKD', decoded).encode('ascii', 'ignore').decode('ascii')
        # If normalization results in empty string, use original decoded
        return normalized if normalized else decoded
    except:
        return text

def fix_unicode_in_data(data):
    """Recursively fix Unicode in JSON data structure."""
    if isinstance(data, dict):
        return {key: fix_unicode_in_data(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [fix_unicode_in_data(item) for item in data]
    elif isinstance(data, str):
        return normalize_unicode_text(data)
    else:
        return data

def main():
    if len(sys.argv) != 2:
        print("Usage: python fix_unicode_json.py <json_file>")
        sys.exit(1)
    
    json_file = sys.argv[1]
    
    try:
        # Read the JSON file
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Fix Unicode issues
        fixed_data = fix_unicode_in_data(data)
        
        # Write back with proper Unicode handling
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(fixed_data, f, indent=2, ensure_ascii=False)
        
        print(f"Fixed Unicode issues in {json_file}")
        
    except Exception as e:
        print(f"Error processing {json_file}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()