"""
CCDI WSI Converter - End-to-end conversion with metadata propagation.

Command-line script for converting CCDI slides using CCDIConverter.
"""

from pathlib import Path

try:
    from .ccdi_converter import CCDIConverter, DEFAULT_TILE_SIZE, DEFAULT_WORKERS, DEFAULT_ENCODING
except ImportError:
    from ccdi_converter import CCDIConverter, DEFAULT_TILE_SIZE, DEFAULT_WORKERS, DEFAULT_ENCODING


def convert_ccdi_slide(
    input_file: Path,
    output_folder: Path,
    pathology_csv: Path,
    sample_csv: Path,
    participant_csv: Path,
    diagnosis_csv: Path,
    codes_dir: Path,
    uid_registry_db: Path,
    tile_size: int = DEFAULT_TILE_SIZE,
    workers: int = DEFAULT_WORKERS,
    encoding = DEFAULT_ENCODING,
    compression_ratio: float = 10.0
):
    """
    Convert CCDI slide to DICOM with metadata propagation.
    
    DEPRECATED: Use CCDIConverter class for better performance in batch operations.
    This function is kept for backward compatibility.
    
    Args:
        input_file: Input SVS/TIFF file path
        output_folder: Output directory for DICOM files
        pathology_csv: CCDI pathology_file CSV
        sample_csv: CCDI sample CSV
        participant_csv: CCDI participant CSV
        diagnosis_csv: CCDI diagnosis CSV
        codes_dir: Directory with code mapping CSVs
        uid_registry_db: SQLite database for UID persistence
        tile_size: Tile size for DICOM pyramid (None = use native)
        workers: Number of worker threads
        encoding: Encoding specification (None = use native)
        compression_ratio: Compression ratio for lossy encoding
    """
    # Use the class-based approach internally
    converter = CCDIConverter(
        pathology_csv=pathology_csv,
        sample_csv=sample_csv,
        participant_csv=participant_csv,
        diagnosis_csv=diagnosis_csv,
        codes_dir=codes_dir,
        uid_registry_db=uid_registry_db,
        tile_size=tile_size,
        workers=workers,
        encoding=encoding,
        compression_ratio=compression_ratio
    )
    
    return converter.convert_slide(input_file, output_folder)


if __name__ == "__main__":
    # Sample directory
    sample_root = Path("/Users/af61/Desktop/PW44/pw44-wsi-conversion/test_data/sample7")
    
    # CCDI CSVs
    csv_base = Path("/Users/af61/Desktop/PW44/pw44-wsi-conversion/idc-wsi-conversion")
    csv_prefix = "phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6"
    
    pathology_csv = csv_base / f"{csv_prefix}_pathology_file.csv"
    sample_csv = csv_base / f"{csv_prefix}_sample.csv"
    participant_csv = csv_base / f"{csv_prefix}_participant.csv"
    diagnosis_csv = csv_base / f"{csv_prefix}_diagnosis.csv"
    
    # Code tables and registry
    codes_dir = Path("/Users/af61/Desktop/PW44/pw44-wsi-conversion/copilot-solution/codes")
    uid_registry_db = Path("/Users/af61/Desktop/PW44/pw44-wsi-conversion/copilot-solution/ccdi_uid_registry.db")
    
    # ============================================================================
    # Example 1: Single slide conversion with native tile size and encoding
    # ============================================================================
    print("Example 1: Single slide conversion with native tile size and encoding")
    print("=" * 70)
    
    # Find input file in src directory
    src_dir = sample_root / "src"
    if not src_dir.exists():
        print(f"ERROR: Source directory not found: {src_dir}")
        exit(1)
    
    # Look for slide files (common WSI extensions)
    slide_extensions = ['.svs', '.tiff', '.tif', '.ndpi', '.scn', '.mrxs']
    input_files = []
    for ext in slide_extensions:
        input_files.extend(src_dir.glob(f'*{ext}'))
    
    if len(input_files) == 0:
        print(f"ERROR: No slide files found in {src_dir}")
        print(f"Looking for extensions: {', '.join(slide_extensions)}")
        exit(1)
    elif len(input_files) > 1:
        print(f"ERROR: Multiple slide files found in {src_dir}:")
        for f in input_files:
            print(f"  - {f.name}")
        print(f"\nPlease ensure only one slide file is present in the directory.")
        exit(1)
    
    input_file = input_files[0]
    print(f"Found slide file: {input_file.name}")
    
    # Create output folder if it doesn't exist
    output_folder = sample_root / "copilot-output"
    output_folder.mkdir(parents=True, exist_ok=True)
    
    converter = CCDIConverter(
        pathology_csv=pathology_csv,
        sample_csv=sample_csv,
        participant_csv=participant_csv,
        diagnosis_csv=diagnosis_csv,
        codes_dir=codes_dir,
        uid_registry_db=uid_registry_db,
        tile_size=None,  # Use native tile size
        workers=DEFAULT_WORKERS,
        encoding=None  # Use native encoding
    )
    
    result = converter.convert_slide(input_file, output_folder)
    
    if result:
        print(f"\nConversion finished!")
        print(f"Output files: {output_folder}")
        print(f"Generated {len(result)} DICOM files")
    
    # ============================================================================
    # Example 2: Batch conversion with lossy compression (uncomment to use)
    # ============================================================================
    # print("\n\nExample 2: Batch conversion with lossy JPEG2000")
    # print("=" * 70)
    # 
    # converter_lossy = CCDIConverter(
    #     pathology_csv=pathology_csv,
    #     sample_csv=sample_csv,
    #     participant_csv=participant_csv,
    #     diagnosis_csv=diagnosis_csv,
    #     codes_dir=codes_dir,
    #     uid_registry_db=uid_registry_db,
    #     tile_size=256,
    #     workers=8,
    #     encoding="jpeg2k-lossy",
    #     compression_ratio=15.0
    # )
    # 
    # input_files = [
    #     sample_root / "src/0DWWQ6.svs",
    #     # Add more slides here
    # ]
    # 
    # output_base = sample_root / "batch-output"
    # 
    # results = converter_lossy.convert_batch(
    #     input_files=input_files,
    #     output_base=output_base,
    #     create_subfolders=True
    # )
    # 
    # print(f"\nBatch conversion complete!")
    # print(f"Successfully converted: {len([r for r in results.values() if r])}")
    # print(f"Failed: {len([r for r in results.values() if not r])}")
    
    # ============================================================================
    # Example 3: Using the legacy function (backward compatibility)
    # ============================================================================
    # print("\n\nExample 3: Legacy function interface")
    # print("=" * 70)
    # 
    # convert_ccdi_slide(
    #     input_file=input_file,
    #     output_folder=sample_root / "legacy-output",
    #     pathology_csv=pathology_csv,
    #     sample_csv=sample_csv,
    #     participant_csv=participant_csv,
    #     diagnosis_csv=diagnosis_csv,
    #     codes_dir=codes_dir,
    #     uid_registry_db=uid_registry_db,
    #     tile_size=None,
    #     workers=DEFAULT_WORKERS,
    #     encoding=None
    # )
