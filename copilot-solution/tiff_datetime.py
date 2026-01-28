"""
TIFF header datetime extraction for WSI files.

Extracts scan datetime from Aperio and SCN TIFF ImageDescription headers.
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional
import tifffile


def extract_scan_datetime(tiff_path: Path) -> Optional[datetime]:
    """
    Extract scan datetime from TIFF ImageDescription header.
    
    Supports Aperio SVS and Leica SCN formats as used in mcitodcm.sh.
    
    Args:
        tiff_path: Path to TIFF/SVS file
        
    Returns:
        Scan datetime if found, else None
    """
    try:
        with tifffile.TiffFile(tiff_path) as tif:
            if not tif.pages:
                return None
            
            # Get ImageDescription from first page
            page = tif.pages[0]
            if not hasattr(page, 'description') or not page.description:
                return None
            
            description = page.description
            
            # Try Aperio format: "Date = MM/DD/YY|Time = HH:MM:SS"
            # Example from mcitodcm.sh lines 2843-2859
            aperio_match = re.search(
                r'Date\s*=\s*(\d{2})/(\d{2})/(\d{2})\s*\|.*?Time\s*=\s*(\d{2}):(\d{2}):(\d{2})',
                description,
                re.IGNORECASE
            )
            if aperio_match:
                month, day, year, hour, minute, second = aperio_match.groups()
                # Assume 20xx for 2-digit year
                full_year = 2000 + int(year)
                return datetime(full_year, int(month), int(day), int(hour), int(minute), int(second))
            
            # Try SCN format: "Date: YYYY-MM-DD Time: HH:MM:SS"
            scn_match = re.search(
                r'Date:\s*(\d{4})-(\d{2})-(\d{2})\s+Time:\s*(\d{2}):(\d{2}):(\d{2})',
                description,
                re.IGNORECASE
            )
            if scn_match:
                year, month, day, hour, minute, second = scn_match.groups()
                return datetime(int(year), int(month), int(day), int(hour), int(minute), int(second))
            
            # Alternative Aperio format without pipe separator
            aperio_alt_match = re.search(
                r'Date\s*=\s*(\d{2})/(\d{2})/(\d{2}).*?Time\s*=\s*(\d{2}):(\d{2}):(\d{2})',
                description,
                re.IGNORECASE
            )
            if aperio_alt_match:
                month, day, year, hour, minute, second = aperio_alt_match.groups()
                full_year = 2000 + int(year)
                return datetime(full_year, int(month), int(day), int(hour), int(minute), int(second))
            
            return None
            
    except Exception as e:
        print(f"Warning: Could not extract datetime from {tiff_path}: {e}")
        return None


def get_study_datetime(
    tiff_path: Path,
    fallback: Optional[datetime] = None
) -> datetime:
    """
    Get study datetime with fallback.
    
    Args:
        tiff_path: Path to TIFF/SVS file
        fallback: Fallback datetime if extraction fails
        
    Returns:
        Extracted or fallback datetime
    """
    extracted = extract_scan_datetime(tiff_path)
    if extracted:
        return extracted
    
    if fallback:
        return fallback
    
    # Last resort: current time
    return datetime.now()


if __name__ == "__main__":
    # Test with sample5 file
    test_file = Path("/Users/af61/Desktop/PW44/wsi-conversion/test_data/sample5/src/0DWWQ6.svs")
    
    if test_file.exists():
        dt = extract_scan_datetime(test_file)
        if dt:
            print(f"Extracted datetime from {test_file.name}: {dt}")
        else:
            print(f"Could not extract datetime from {test_file.name}")
    else:
        print(f"Test file not found: {test_file}")
