"""
CCDI WSI Converter - End-to-end conversion with metadata propagation.

Integrates CCDI loader, UID registry, metadata builder, and wsidicomizer
to convert WSI files with rich DICOM metadata from CCDI CSV tables.
"""

import time
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Union
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


class CCDIConverter:
    """
    Unified converter for single-slide and batch CCDI WSI conversions.
    
    Initializes components once and reuses them across multiple conversions,
    tracking aggregate statistics for batch operations.
    """
    
    def __init__(
        self,
        pathology_csv: Union[str, Path],
        sample_csv: Union[str, Path],
        participant_csv: Union[str, Path],
        diagnosis_csv: Union[str, Path],
        codes_dir: Union[str, Path],
        uid_registry_db: Union[str, Path],
        tile_size: int = DEFAULT_TILE_SIZE,
        workers: int = DEFAULT_WORKERS
    ):
        """
        Initialize the CCDI converter with configuration.
        
        Args:
            pathology_csv: CCDI pathology_file CSV
            sample_csv: CCDI sample CSV
            participant_csv: CCDI participant CSV
            diagnosis_csv: CCDI diagnosis CSV
            codes_dir: Directory with code mapping CSVs
            uid_registry_db: SQLite database for UID persistence
            tile_size: Tile size for DICOM pyramid (default: 240)
            workers: Number of worker threads (default: 8)
        """
        self.tile_size = tile_size
        self.workers = workers
        
        # Initialize components once
        init_start = time.time()
        self.loader = CCDIMetadataLoader(
            pathology_csv=str(pathology_csv),
            sample_csv=str(sample_csv),
            participant_csv=str(participant_csv),
            diagnosis_csv=str(diagnosis_csv),
            codes_dir=str(codes_dir)
        )
        self.registry = UIDRegistry(str(uid_registry_db))
        self.builder = MetadataBuilder(self.registry, dataset="CCDI")
        init_time = time.time() - init_start
        
        print(f"CCDIConverter initialized (took {init_time:.2f}s)")
        print(f"Configuration: tile_size={tile_size}, workers={workers}")
        
        # Batch statistics
        self.batch_stats = {
            'conversions': [],
            'total_slides': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0
        }
    
    def _check_output_directory(self, output_folder: Path, auto_clear: bool = False) -> bool:
        """
        Check if output directory is empty and handle accordingly.
        
        Args:
            output_folder: Output directory path
            auto_clear: If True, clear automatically without prompt
            
        Returns:
            True if safe to proceed, False if should abort
        """
        if output_folder.exists():
            existing_files = list(output_folder.iterdir())
            if existing_files:
                print(f"\n  WARNING: Output directory is not empty!")
                print(f"  Path: {output_folder}")
                print(f"  Contains {len(existing_files)} items")
                print(f"  Mixing multiple DICOM series in one folder can cause issues.\n")
                
                if auto_clear:
                    print(f"  Auto-clearing enabled: deleting existing content...")
                    shutil.rmtree(output_folder)
                    output_folder.mkdir(parents=True, exist_ok=True)
                    print(f"  Output directory cleared.")
                    return True
                else:
                    response = input("  Delete existing content and continue? (yes/no): ").strip().lower()
                    if response in ['yes', 'y']:
                        print(f"  Deleting existing content...")
                        shutil.rmtree(output_folder)
                        output_folder.mkdir(parents=True, exist_ok=True)
                        print(f"  Output directory cleared.")
                        return True
                    else:
                        print(f"  Aborting conversion to avoid mixing DICOM series.")
                        return False
        return True
    
    def convert_slide(
        self,
        input_file: Union[str, Path],
        output_folder: Union[str, Path],
        tile_size: Optional[int] = None,
        workers: Optional[int] = None,
        auto_clear: bool = False
    ) -> Optional[List[str]]:
        """
        Convert a single CCDI slide to DICOM.
        
        Args:
            input_file: Input SVS/TIFF file path
            output_folder: Output directory for DICOM files
            tile_size: Override instance tile_size if provided
            workers: Override instance workers if provided
            auto_clear: Auto-clear output directory without prompt
            
        Returns:
            List of generated DICOM file paths, or None if conversion failed/aborted
        """
        input_file = Path(input_file)
        output_folder = Path(output_folder)
        tile_size = tile_size or self.tile_size
        workers = workers or self.workers
        
        start_time = time.time()
        print(f"\nConverting {input_file.name}...")
        print(f"  Configuration: tile_size={tile_size}, workers={workers}")
        
        # Check output directory
        if not self._check_output_directory(output_folder, auto_clear):
            self.batch_stats['skipped'] += 1
            return None
        
        try:
            # Load domain metadata
            filename = input_file.name
            print(f"  Loading metadata for {filename}...")
            load_start = time.time()
            domain_metadata = self.loader.load_slide(filename)
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
            wsi_metadata, supplement = self.builder.build(domain_metadata, study_datetime)
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
            print(f"  Conversion complete: {len(result)} DICOM files generated")
            print(f"\n  Profiling Summary:")
            print(f"    Metadata Loading:   {load_time:6.2f}s ({load_time/total_time*100:5.1f}%)")
            print(f"    DateTime Extract:   {datetime_time:6.2f}s ({datetime_time/total_time*100:5.1f}%)")
            print(f"    Metadata Build:     {build_time:6.2f}s ({build_time/total_time*100:5.1f}%)")
            print(f"    WSI Conversion:     {conversion_time:6.2f}s ({conversion_time/total_time*100:5.1f}%)")
            print(f"    Total:              {total_time:6.2f}s")
            
            # Record statistics
            self.batch_stats['conversions'].append({
                'filename': input_file.name,
                'load_time': load_time,
                'datetime_time': datetime_time,
                'build_time': build_time,
                'conversion_time': conversion_time,
                'total_time': total_time,
                'num_files': len(result)
            })
            self.batch_stats['successful'] += 1
            self.batch_stats['total_slides'] += 1
            
            return result
            
        except Exception as e:
            print(f"  ERROR: Conversion failed: {e}")
            self.batch_stats['failed'] += 1
            self.batch_stats['total_slides'] += 1
            return None
    
    def convert_batch(
        self,
        input_files: List[Union[str, Path]],
        output_base: Union[str, Path],
        tile_size: Optional[int] = None,
        workers: Optional[int] = None,
        create_subfolders: bool = True
    ) -> Dict[str, List[str]]:
        """
        Convert multiple CCDI slides to DICOM.
        
        Args:
            input_files: List of input SVS/TIFF file paths
            output_base: Base output directory
            tile_size: Override instance tile_size if provided
            workers: Override instance workers if provided
            create_subfolders: Create a subfolder for each slide (recommended)
            
        Returns:
            Dictionary mapping input filename to list of output DICOM paths
        """
        output_base = Path(output_base)
        results = {}
        
        print(f"\n{'='*70}")
        print(f"BATCH CONVERSION: {len(input_files)} slides")
        print(f"{'='*70}")
        
        batch_start = time.time()
        
        for i, input_file in enumerate(input_files, 1):
            input_file = Path(input_file)
            print(f"\n[{i}/{len(input_files)}] Processing {input_file.name}")
            
            # Create output folder
            if create_subfolders:
                output_folder = output_base / input_file.stem
            else:
                output_folder = output_base
            
            # Convert (auto-clear for batch processing)
            result = self.convert_slide(
                input_file=input_file,
                output_folder=output_folder,
                tile_size=tile_size,
                workers=workers,
                auto_clear=True
            )
            
            results[input_file.name] = result if result else []
        
        batch_time = time.time() - batch_start
        
        # Print batch summary
        print(f"\n{'='*70}")
        print(f"BATCH CONVERSION COMPLETE")
        print(f"{'='*70}")
        self.print_batch_statistics(batch_time)
        
        return results
    
    def print_batch_statistics(self, batch_time: Optional[float] = None):
        """Print aggregate statistics for batch conversions."""
        stats = self.batch_stats
        
        print(f"\nBatch Statistics:")
        print(f"  Total slides:       {stats['total_slides']}")
        print(f"  Successful:         {stats['successful']}")
        print(f"  Failed:             {stats['failed']}")
        print(f"  Skipped:            {stats['skipped']}")
        
        if stats['conversions']:
            # Aggregate timing
            total_load = sum(c['load_time'] for c in stats['conversions'])
            total_datetime = sum(c['datetime_time'] for c in stats['conversions'])
            total_build = sum(c['build_time'] for c in stats['conversions'])
            total_conversion = sum(c['conversion_time'] for c in stats['conversions'])
            total_time = sum(c['total_time'] for c in stats['conversions'])
            
            avg_load = total_load / len(stats['conversions'])
            avg_datetime = total_datetime / len(stats['conversions'])
            avg_build = total_build / len(stats['conversions'])
            avg_conversion = total_conversion / len(stats['conversions'])
            avg_total = total_time / len(stats['conversions'])
            
            print(f"\nAggregate Timing (all successful conversions):")
            print(f"  Metadata Loading:   {total_load:7.2f}s (avg: {avg_load:6.2f}s)")
            print(f"  DateTime Extract:   {total_datetime:7.2f}s (avg: {avg_datetime:6.2f}s)")
            print(f"  Metadata Build:     {total_build:7.2f}s (avg: {avg_build:6.2f}s)")
            print(f"  WSI Conversion:     {total_conversion:7.2f}s (avg: {avg_conversion:6.2f}s)")
            print(f"  Total:              {total_time:7.2f}s (avg: {avg_total:6.2f}s)")
            
            if batch_time:
                print(f"\nEnd-to-end batch time: {batch_time:.2f}s")
                if stats['successful'] > 0:
                    print(f"Average per slide:     {batch_time/stats['successful']:.2f}s")
    
    def reset_statistics(self):
        """Reset batch statistics."""
        self.batch_stats = {
            'conversions': [],
            'total_slides': 0,
            'successful': 0,
            'failed': 0,
            'skipped': 0
        }


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
        tile_size: Tile size for DICOM pyramid
        workers: Number of worker threads
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
        workers=workers
    )
    
    return converter.convert_slide(input_file, output_folder)


if __name__ == "__main__":
    # Sample directory
    sample_root = Path("/Users/af61/Desktop/PW44/pw44-wsi-conversion/test_data/sample5")
    
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
    # Example 1: Single slide conversion using CCDIConverter class
    # ============================================================================
    print("Example 1: Single slide conversion")
    print("=" * 70)
    
    converter = CCDIConverter(
        pathology_csv=pathology_csv,
        sample_csv=sample_csv,
        participant_csv=participant_csv,
        diagnosis_csv=diagnosis_csv,
        codes_dir=codes_dir,
        uid_registry_db=uid_registry_db,
        tile_size=DEFAULT_TILE_SIZE,
        workers=DEFAULT_WORKERS
    )
    
    input_file = sample_root / "src/0DWWQ6.svs"
    output_folder = sample_root / "copilot-output"
    
    result = converter.convert_slide(input_file, output_folder)
    
    if result:
        print(f"\nConversion finished!")
        print(f"Output files: {output_folder}")
        print(f"Generated {len(result)} DICOM files")
    
    # ============================================================================
    # Example 2: Batch conversion (uncomment to use)
    # ============================================================================
    # print("\n\nExample 2: Batch conversion")
    # print("=" * 70)
    # 
    # # Reset statistics for new batch
    # converter.reset_statistics()
    # 
    # # List of input files
    # input_files = [
    #     sample_root / "src/0DWWQ6.svs",
    #     # Add more slides here
    # ]
    # 
    # output_base = sample_root / "batch-output"
    # 
    # results = converter.convert_batch(
    #     input_files=input_files,
    #     output_base=output_base,
    #     create_subfolders=True  # Each slide gets its own subfolder
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
    #     tile_size=DEFAULT_TILE_SIZE,
    #     workers=DEFAULT_WORKERS
    # )
