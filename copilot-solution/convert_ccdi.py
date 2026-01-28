"""
CCDI WSI Converter - End-to-end conversion with metadata propagation.

Integrates CCDI loader, UID registry, metadata builder, and wsidicomizer
to convert WSI files with rich DICOM metadata from CCDI CSV tables.
"""

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
    tile_size: int = 1024,
    workers: int = 1
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
    print(f"Converting {input_file.name}...")
    
    # Initialize components
    loader = CCDIMetadataLoader(
        pathology_csv=str(pathology_csv),
        sample_csv=str(sample_csv),
        participant_csv=str(participant_csv),
        diagnosis_csv=str(diagnosis_csv),
        codes_dir=str(codes_dir)
    )
    
    registry = UIDRegistry(str(uid_registry_db))
    builder = MetadataBuilder(registry, dataset="CCDI")
    
    # Load domain metadata
    filename = input_file.name
    print(f"  Loading metadata for {filename}...")
    domain_metadata = loader.load_slide(filename)
    
    print(f"  Patient: {domain_metadata.patient.participant_id}")
    print(f"  Specimens: {len(domain_metadata.specimens)}")
    for spec in domain_metadata.specimens:
        print(f"    - {spec.specimen_id}: {spec.anatomic_site}")
    
    # Extract study datetime from TIFF
    print(f"  Extracting scan datetime...")
    study_datetime = extract_scan_datetime(input_file)
    if study_datetime:
        print(f"    Found: {study_datetime}")
    else:
        print(f"    Not found in TIFF, using fallback")
    
    # Build metadata
    print(f"  Building DICOM metadata...")
    wsi_metadata, supplement = builder.build(domain_metadata, study_datetime)
    
    print(f"  Study UID: {wsi_metadata.study.uid}")
    print(f"  Series: {wsi_metadata.series.number} - {wsi_metadata.series.description}")
    
    # Convert with wsidicomizer
    print(f"  Running wsidicomizer conversion...")
    output_folder.mkdir(parents=True, exist_ok=True)
    
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
    
    print(f"  Conversion complete: {result}")
    return result


if __name__ == "__main__":
    # Convert sample5
    input_file = Path("/Users/af61/Desktop/PW44/wsi-conversion/test_data/sample5/src/0DWWQ6.svs")
    output_folder = Path("/Users/af61/Desktop/PW44/wsi-conversion/test_data/sample5/copilot-output")
    
    # CCDI CSVs
    csv_base = Path("/Users/af61/Desktop/PW44/wsi-conversion/idc-wsi-conversion")
    csv_prefix = "phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6"
    
    pathology_csv = csv_base / f"{csv_prefix}_pathology_file.csv"
    sample_csv = csv_base / f"{csv_prefix}_sample.csv"
    participant_csv = csv_base / f"{csv_prefix}_participant.csv"
    diagnosis_csv = csv_base / f"{csv_prefix}_diagnosis.csv"
    
    # Code tables and registry
    codes_dir = Path("/Users/af61/Desktop/PW44/wsi-conversion/copilot-solution/codes")
    uid_registry_db = Path("/Users/af61/Desktop/PW44/wsi-conversion/copilot-solution/ccdi_uid_registry.db")
    
    # Run conversion
    convert_ccdi_slide(
        input_file=input_file,
        output_folder=output_folder,
        pathology_csv=pathology_csv,
        sample_csv=sample_csv,
        participant_csv=participant_csv,
        diagnosis_csv=diagnosis_csv,
        codes_dir=codes_dir,
        uid_registry_db=uid_registry_db,
        tile_size=1024,
        workers=1
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
