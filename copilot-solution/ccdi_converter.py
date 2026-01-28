"""
CCDIConverter - Unified converter for single-slide and batch CCDI WSI conversions.

Provides a class-based interface for converting WSI files to DICOM with CCDI metadata,
supporting both single conversions and batch processing with aggregate statistics.
"""

import time
import shutil
from pathlib import Path
from typing import List, Dict, Optional, Union, Literal
import tifffile
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
DEFAULT_TILE_SIZE = None  # Use native tile size by default
DEFAULT_WORKERS = 8
DEFAULT_ENCODING = None  # Use native encoding by default

# Type alias for encoding specification
EncodingSpec = Union[None, Literal["native", "jpeg2k-lossless", "jpeg2k-lossy"], Jpeg2kEncoder]


class Jpeg2kLosslessEncoder(Jpeg2kEncoder):
    """JPEG 2000 lossless encoder."""
    
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


class Jpeg2kLossyEncoder(Jpeg2kEncoder):
    """JPEG 2000 lossy encoder with configurable quality."""
    
    def __init__(self, compression_ratio: float = 10.0):
        """
        Args:
            compression_ratio: Target compression ratio (higher = more compression, lower quality).
                             Typical values: 5-20. Default: 10.
        """
        settings = Jpeg2kSettings(compression_ratio=compression_ratio)
        super().__init__(settings)
        self.compression_ratio = compression_ratio
    
    @property
    def lossy(self) -> bool:
        return True
    
    @property
    def transfer_syntax(self) -> UID:
        return JPEG2000
    
    @property
    def photometric_interpretation(self) -> str:
        return "YBR_ICT"


def create_encoder(encoding: EncodingSpec, compression_ratio: float = 10.0) -> Optional[Jpeg2kEncoder]:
    """
    Create an encoder based on the encoding specification.
    
    Args:
        encoding: Encoding specification:
            - None or "native": Don't pass encoding (use native encoding from source) - DEFAULT
            - "jpeg2k-lossless": Re-encode as JPEG 2000 lossless
            - "jpeg2k-lossy": Re-encode as JPEG 2000 lossy with compression_ratio
            - Jpeg2kEncoder instance: Use directly
        compression_ratio: Compression ratio for lossy JPEG2000 (default: 10.0)
        
    Returns:
        Encoder instance, or None for native encoding
    """
    if encoding is None or encoding == "native":
        return None
    elif encoding == "jpeg2k-lossless":
        return Jpeg2kLosslessEncoder()
    elif encoding == "jpeg2k-lossy":
        return Jpeg2kLossyEncoder(compression_ratio=compression_ratio)
    elif isinstance(encoding, Jpeg2kEncoder):
        return encoding
    else:
        raise ValueError(
            f"Invalid encoding: {encoding}. "
            f"Must be None, 'native', 'jpeg2k-lossless', 'jpeg2k-lossy', or an encoder instance."
        )


def get_native_tile_size(filepath: Path) -> Optional[int]:
    """
    Extract native tile size from TIFF/SVS file.
    
    Args:
        filepath: Path to TIFF/SVS file
        
    Returns:
        Native tile width, or None if not tiled or cannot determine
    """
    try:
        with tifffile.TiffFile(filepath) as tif:
            page = tif.pages[0]  # Get first page (full resolution)
            
            # Check if image is tiled
            if hasattr(page, 'is_tiled') and page.is_tiled:
                tile_width = page.tilewidth
                tile_height = page.tilelength
                
                # Most WSI use square tiles, verify
                if tile_width == tile_height:
                    return tile_width
                else:
                    print(f"  Warning: Non-square tiles ({tile_width}x{tile_height}), using width")
                    return tile_width
            else:
                print(f"  Warning: Image is not tiled, no native tile size")
                return None
                
    except Exception as e:
        print(f"  Warning: Could not determine native tile size: {e}")
        return None


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
        tile_size: Optional[int] = DEFAULT_TILE_SIZE,
        workers: int = DEFAULT_WORKERS,
        encoding: EncodingSpec = DEFAULT_ENCODING,
        compression_ratio: float = 10.0
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
            tile_size: Tile size for DICOM pyramid (None = use native, default)
            workers: Number of worker threads (default: 8)
            encoding: Encoding specification (None = use native, default)
                - None or "native": Use native encoding from source
                - "jpeg2k-lossless": JPEG 2000 lossless
                - "jpeg2k-lossy": JPEG 2000 lossy
                - Encoder instance: Custom encoder
            compression_ratio: Compression ratio for lossy encoding (default: 10.0)
        """
        self.tile_size = tile_size
        self.workers = workers
        self.encoding = encoding
        self.compression_ratio = compression_ratio
        
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
        
        encoding_str = encoding if isinstance(encoding, str) or encoding is None else type(encoding).__name__
        tile_str = tile_size if tile_size is not None else "native"
        print(f"\n{'='*70}")
        print(f"CCDIConverter Initialized")
        print(f"{'='*70}")
        print(f"  Initialization time: {init_time:.3f}s")
        print(f"\n  Default Configuration:")
        print(f"    Tile Size:         {tile_str}")
        print(f"    Workers:           {workers}")
        print(f"    Encoding:          {encoding_str or 'native'}")
        if encoding == "jpeg2k-lossy":
            print(f"    Compression Ratio: {compression_ratio}")
        print(f"\n  Note: These defaults can be overridden per conversion.")
        print(f"{'='*70}")
        
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
        encoding: Optional[EncodingSpec] = None,
        compression_ratio: Optional[float] = None,
        auto_clear: bool = False
    ) -> Optional[List[str]]:
        """
        Convert a single CCDI slide to DICOM.
        
        Args:
            input_file: Input SVS/TIFF file path
            output_folder: Output directory for DICOM files
            tile_size: Override instance tile_size if provided (None = use native)
            workers: Override instance workers if provided
            encoding: Override instance encoding if provided (None = use native)
            compression_ratio: Override instance compression_ratio if provided
            auto_clear: Auto-clear output directory without prompt
            
        Returns:
            List of generated DICOM file paths, or None if conversion failed/aborted
        """
        input_file = Path(input_file)
        output_folder = Path(output_folder)
        workers = workers if workers is not None else self.workers
        encoding = encoding if encoding is not None else self.encoding
        compression_ratio = compression_ratio if compression_ratio is not None else self.compression_ratio
        
        start_time = time.time()
        
        # Check output directory FIRST before doing any work
        if not self._check_output_directory(output_folder, auto_clear):
            self.batch_stats['skipped'] += 1
            return None
        
        # Handle tile_size - use native if None
        tile_size_source = "override"
        if tile_size is None and self.tile_size is None:
            detected_tile_size = get_native_tile_size(input_file)
            if detected_tile_size:
                tile_size = detected_tile_size
                tile_size_source = "native (detected)"
                print(f"  ✓ Native tile size detected: {tile_size}x{tile_size}")
            else:
                tile_size = None  # Let wsidicomizer choose
                tile_size_source = "default (wsidicomizer)"
                print(f"  ⚠ No native tile size found, using wsidicomizer default")
        else:
            tile_size = tile_size if tile_size is not None else self.tile_size
            if tile_size:
                tile_size_source = "specified"
                print(f"  ✓ Using specified tile size: {tile_size}x{tile_size}")
        
        encoding_str = encoding if isinstance(encoding, str) or encoding is None else type(encoding).__name__
        tile_str = tile_size if tile_size is not None else "wsidicomizer-default"
        
        print(f"\n{'='*70}")
        print(f"CONVERTING: {input_file.name}")
        print(f"{'='*70}")
        print(f"  Input:  {input_file}")
        print(f"  Output: {output_folder}")
        print(f"\n  Conversion Parameters:")
        print(f"    Tile Size:         {tile_str} ({tile_size_source})")
        print(f"    Workers:           {workers}")
        print(f"    Encoding:          {encoding_str or 'native'}")
        if encoding == "jpeg2k-lossy":
            print(f"    Compression Ratio: {compression_ratio}")
        
        print(f"\n  Phase 1: Metadata Preparation")
        print(f"  {'-'*68}")
        
        try:
            # Load domain metadata
            filename = input_file.name
            print(f"  • Loading CCDI metadata for {filename}...")
            load_start = time.time()
            domain_metadata = self.loader.load_slide(filename)
            load_time = time.time() - load_start
            
            print(f"    ✓ Loaded in {load_time:.2f}s")
            print(f"    Patient ID: {domain_metadata.patient.participant_id}")
            print(f"    Specimens:  {len(domain_metadata.specimens)}")
            for spec in domain_metadata.specimens:
                print(f"      - {spec.specimen_id}: {spec.anatomic_site}")
            
            # Extract study datetime from TIFF
            print(f"\n  • Extracting scan datetime from TIFF...")
            datetime_start = time.time()
            study_datetime = extract_scan_datetime(input_file)
            datetime_time = time.time() - datetime_start
            if study_datetime:
                print(f"    ✓ Found: {study_datetime} ({datetime_time:.3f}s)")
            else:
                print(f"    ⚠ Not found in TIFF, using fallback date ({datetime_time:.3f}s)")
            
            # Build metadata
            print(f"\n  • Building DICOM metadata...")
            build_start = time.time()
            wsi_metadata, supplement = self.builder.build(domain_metadata, study_datetime)
            build_time = time.time() - build_start
            
            print(f"    ✓ Built in {build_time:.2f}s")
            print(f"    Study UID:  {wsi_metadata.study.uid}")
            print(f"    Series:     {wsi_metadata.series.number} - {wsi_metadata.series.description}")
            
            # Convert with wsidicomizer
            print(f"\n  Phase 2: WSI Conversion")
            print(f"  {'-'*68}")
            output_folder.mkdir(parents=True, exist_ok=True)
            
            # Create encoder
            encoder = create_encoder(encoding, compression_ratio)
            if encoder:
                print(f"  • Encoder:  {type(encoder).__name__}")
                if hasattr(encoder, 'compression_ratio'):
                    print(f"    Compression ratio: {encoder.compression_ratio}")
            else:
                print(f"  • Encoder:  Native (preserving source encoding)")
            
            # Log conversion parameters
            print(f"  • Starting conversion with {workers} worker(s)...")
            if tile_size:
                print(f"    Tile size: {tile_size}x{tile_size} ({tile_size_source})")
            else:
                print(f"    Tile size: Using wsidicomizer default")
            
            conversion_start = time.time()
            # Build convert args - only pass optional params if specified
            convert_args = {
                'filepath': input_file,
                'output_path': output_folder,
                'metadata': wsi_metadata,
                'metadata_post_processor': supplement,
                'workers': workers,
                'preferred_source': TiffSlideSource,
            }
            if tile_size is not None:
                convert_args['tile_size'] = tile_size
            if encoder:
                convert_args['encoding'] = encoder
            
            result = WsiDicomizer.convert(**convert_args)
            conversion_time = time.time() - conversion_start
            total_time = time.time() - start_time
            
            print(f"\n  {'='*68}")
            print(f"  ✓ CONVERSION SUCCESSFUL")
            print(f"  {'='*68}")
            print(f"  Generated {len(result)} DICOM file(s)")
            print(f"  Output: {output_folder}")
            
            print(f"\n  Timing Breakdown:")
            print(f"    Metadata Loading:   {load_time:7.2f}s  ({load_time/total_time*100:5.1f}%)")
            print(f"    DateTime Extract:   {datetime_time:7.2f}s  ({datetime_time/total_time*100:5.1f}%)")
            print(f"    Metadata Build:     {build_time:7.2f}s  ({build_time/total_time*100:5.1f}%)")
            print(f"    WSI Conversion:     {conversion_time:7.2f}s  ({conversion_time/total_time*100:5.1f}%)")
            print(f"    {'─'*68}")
            print(f"    Total Time:         {total_time:7.2f}s")
            
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
            total_time = time.time() - start_time
            print(f"\n  {'='*68}")
            print(f"  ✗ CONVERSION FAILED")
            print(f"  {'='*68}")
            print(f"  Error: {e}")
            print(f"  Time elapsed: {total_time:.2f}s")
            print(f"\n  Stack trace:")
            import traceback
            traceback.print_exc()
            self.batch_stats['failed'] += 1
            self.batch_stats['total_slides'] += 1
            return None
    
    def convert_batch(
        self,
        input_files: List[Union[str, Path]],
        output_base: Union[str, Path],
        tile_size: Optional[int] = None,
        workers: Optional[int] = None,
        encoding: Optional[EncodingSpec] = None,
        compression_ratio: Optional[float] = None,
        create_subfolders: bool = True
    ) -> Dict[str, List[str]]:
        """
        Convert multiple CCDI slides to DICOM.
        
        Args:
            input_files: List of input SVS/TIFF file paths
            output_base: Base output directory
            tile_size: Override instance tile_size if provided (None = use native)
            workers: Override instance workers if provided
            encoding: Override instance encoding if provided (None = use native)
            compression_ratio: Override instance compression_ratio if provided
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
                encoding=encoding,
                compression_ratio=compression_ratio,
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
