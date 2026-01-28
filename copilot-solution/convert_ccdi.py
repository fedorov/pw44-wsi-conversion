"""
CCDI WSI Converter - End-to-end conversion with metadata propagation.

Integrates CCDI loader, UID registry, metadata builder, and wsidicomizer
to convert WSI files with rich DICOM metadata from CCDI CSV tables.
"""

import time
import shutil
from pathlib import Path
from wsidicomizer import WsiDicomizer
from wsidicomizer.sources import TiffSlideSource
from wsidicom.codec.settings import Jpeg2kSettings
from wsidicom.codec.encoder import Jpeg2kEncoder
from pydicom.uid import JPEG2000, UID

try:
    from .ccdi_loader import CCDIMetadataLoader
    from .metadata_builder import MetadataBuilder
    from .uid_registry import UIDRegistry
    from .tiff_datetime import extract_scan_datetime
except ImportError:
    from ccdi_loader import CCDIMetadataLoader
    from metadata_builder import MetadataBuilder
    from uid_registry import UIDRegistry
    from tiff_datetime import extract_scan_datetime


# Conversion Configuration
DEFAULT_TILE_SIZE = 240
DEFAULT_WORKERS = 8


class Jpeg2kLosslessEncoder(Jpeg2kEncoder):
    """JPEG 2000 lossless encoder for testing."""
    
    def __init__(self):
        settings = Jpeg2kSettings(levels=[0])
        super().__init__(settings)
    
    @property
    def lossy(self) -> bool:
        return False
    
    @property
    def transfer_syntax(self) -> UID:
        return JPEG2000
    
    @property
    def photometric_interpretation(self) -> str:
        return "YBR_ICT"


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
    workers: int = DEFAULT_WORKERS
):
    """
    Convert CCDI slide to DICOM with metadata propagation.
    
    Args:
        input_file: Input SVS/TIFF file path
        output_folder: Output directory for DICOM files
        pathology_csv: CCDI pathology_file CSV
        sample_csv: CCDI sample CSV
        participant_csv: CCDI participant CSV
        diagnosis_csv: CCDI diagnosis CSV
        codes_dir: Directory with code mapping CSVs
        uid_registry_db: SQLite database for UID persistence
        tile_size: Tile size for DICOM pyramid
        workers: Number of worker threads
    """
    start_time = time.time()
    print(f"Converting {input_file.name}...")
    print(f"  Configuration: tile_size={tile_size}, workers={workers}")
    
    # Check if output directory exists and is not empty
    if output_folder.exists():
        existing_files = list(output_folder.iterdir())
        if existing_files:
            print(f"\n  WARNING: Output directory is not empty!")
            print(f"  Path: {output_folder}")
            print(f"  Contains {len(existing_files)} items")
            print(f"  Mixing multiple DICOM series in one folder can cause issues.\n")
            
            response = input("  Delete existing content and continue? (yes/no): ").strip().lower()
            if response in ['yes', 'y']:
                print(f"  Deleting existing content...")
                shutil.rmtree(output_folder)
                output_folder.mkdir(parents=True, exist_ok=True)
                print(f"  Output directory cleared.")
            else:
                print(f"  Aborting conversion to avoid mixing DICOM series.")
                print(f"  Please empty the directory or choose a different output path.")
                return None
    
    # Initialize components
    init_start = time.time()
    loader = CCDIMetadataLoader(
        pathology_csv=str(pathology_csv),
        sample_csv=str(sample_csv),
        participant_csv=str(participant_csv),
        diagnosis_csv=str(diagnosis_csv),
        codes_dir=str(codes_dir)
    )
    
    registry = UIDRegistry(str(uid_registry_db))
    builder = MetadataBuilder(registry, dataset="CCDI")
    init_time = time.time() - init_start
    print(f"  Initialization time: {init_time:.2f}s")
    
    # Load domain metadata
    filename = input_file.name
    print(f"  Loading metadata for {filename}...")
    load_start = time.time()
    domain_metadata = loader.load_slide(filename)
    load_time = time.time() - load_start
    print(f"  Metadata loading time: {load_time:.2f}s")
    
    print(f"  Patient: {domain_metadata.patient.participant_id}")
    print(f"  Specimens: {len(domain_metadata.specimens)}")
    for spec in domain_metadata.specimens:
        print(f"    - {spec.specimen_id}: {spec.anatomic_site}")
    
    # Extract study datetime from TIFF
    print(f"  Extracting scan datetime...")
    datetime_start = time.time()
    study_datetime = extract_scan_datetime(input_file)
    datetime_time = time.time() - datetime_start
    if study_datetime:
        print(f"    Found: {study_datetime} (took {datetime_time:.2f}s)")
    else:
        print(f"    Not found in TIFF, using fallback (took {datetime_time:.2f}s)")
    
    # Build metadata
    print(f"  Building DICOM metadata...")
    build_start = time.time()
    wsi_metadata, supplement = builder.build(domain_metadata, study_datetime)
    build_time = time.time() - build_start
    print(f"  Metadata build time: {build_time:.2f}s")
    
    print(f"  Study UID: {wsi_metadata.study.uid}")
    print(f"  Series: {wsi_metadata.series.number} - {wsi_metadata.series.description}")
    
    # Convert with wsidicomizer
    print(f"  Running wsidicomizer conversion...")
    output_folder.mkdir(parents=True, exist_ok=True)
    
    conversion_start = time.time()
    result = WsiDicomizer.convert(
        filepath=input_file,
        output_path=output_folder,
        metadata=wsi_metadata,
        metadata_post_processor=supplement,
        workers=workers,
        preferred_source=TiffSlideSource,
        tile_size=tile_size,
        encoding=Jpeg2kLosslessEncoder()
    )
    conversion_time = time.time() - conversion_start
    total_time = time.time() - start_time
    
    print(f"  Conversion time: {conversion_time:.2f}s")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Conversion complete: {result}")
    print(f"\n  Profiling Summary:")
    print(f"    Initialization:     {init_time:6.2f}s ({init_time/total_time*100:5.1f}%)")
    print(f"    Metadata Loading:   {load_time:6.2f}s ({load_time/total_time*100:5.1f}%)")
    print(f"    DateTime Extract:   {datetime_time:6.2f}s ({datetime_time/total_time*100:5.1f}%)")
    print(f"    Metadata Build:     {build_time:6.2f}s ({build_time/total_time*100:5.1f}%)")
    print(f"    WSI Conversion:     {conversion_time:6.2f}s ({conversion_time/total_time*100:5.1f}%)")
    print(f"    Total:              {total_time:6.2f}s")
    
    return result


if __name__ == "__main__":
    # Sample directory
    sample_root = Path("/Users/af61/Desktop/PW44/pw44-wsi-conversion/test_data/sample5")
    
    # Convert sample5
    input_file = sample_root / "src/0DWWQ6.svs"
    output_folder = sample_root / "copilot-output"
    
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
    
    # Run conversion (using module-level defaults or override here)
    tile_size = DEFAULT_TILE_SIZE  # Can override: e.g., tile_size = 512
    workers = DEFAULT_WORKERS      # Can override: e.g., workers = 16
    
    convert_ccdi_slide(
        input_file=input_file,
        output_folder=output_folder,
        pathology_csv=pathology_csv,
        sample_csv=sample_csv,
        participant_csv=participant_csv,
        diagnosis_csv=diagnosis_csv,
        codes_dir=codes_dir,
        uid_registry_db=uid_registry_db,
        tile_size=tile_size,
        workers=workers
    )
    
    print("\nConversion finished!")
    print(f"Output files: {output_folder}")
    
    # List output files
    if output_folder.exists():
        dcm_files = list(output_folder.glob("*.dcm"))
        print(f"Generated {len(dcm_files)} DICOM files:")
        for dcm in sorted(dcm_files)[:5]:  # Show first 5
            print(f"  {dcm.name}")
        if len(dcm_files) > 5:
            print(f"  ... and {len(dcm_files) - 5} more")
