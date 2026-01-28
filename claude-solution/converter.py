"""
WSI to DICOM Converter Module

Integrates the metadata handler with wsidicomizer for full
metadata propagation during WSI to DICOM conversion.
"""

from pathlib import Path
from typing import Optional, Callable

import pydicom
from pydicom.uid import UID, JPEG2000

from wsidicomizer import WsiDicomizer
from wsidicomizer.metadata import WsiDicomizerMetadata, MetadataPostProcessor
from wsidicomizer.sources import TiffSlideSource
from wsidicom.codec.encoder import Jpeg2kEncoder
from wsidicom.codec.settings import Jpeg2kSettings
from wsidicom.metadata import WsiMetadata

try:
    from .metadata_handler import WSIMetadataHandler, SlideData, PatientData
    from .csv_loaders import MCICCDILoader, CSVLoaderBase
    from .uid_manager import UIDMappingManager
    from .code_mapper import DicomCodeMapper
    from .collection_config import CollectionConfig, MCI_CCDI_CONFIG
except ImportError:
    from metadata_handler import WSIMetadataHandler, SlideData, PatientData
    from csv_loaders import MCICCDILoader, CSVLoaderBase
    from uid_manager import UIDMappingManager
    from code_mapper import DicomCodeMapper
    from collection_config import CollectionConfig, MCI_CCDI_CONFIG


class Jpeg2kLosslessEncoder(Jpeg2kEncoder):
    """
    JPEG 2000 encoder for lossless encoding.

    Encodes losslessly to preserve image quality while using
    JPEG 2000 compression for efficient storage.
    """

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


def create_metadata_post_processor(
    additional_ds: pydicom.Dataset
) -> MetadataPostProcessor:
    """
    Create a metadata post-processor callback for wsidicomizer.

    The post-processor is called for each DICOM file generated and
    can add or modify attributes in the output dataset.

    Parameters
    ----------
    additional_ds : pydicom.Dataset
        Dataset with additional attributes to add

    Returns
    -------
    MetadataPostProcessor
        Post-processor function for wsidicomizer
    """
    def post_processor(ds: pydicom.Dataset, metadata: WsiMetadata) -> pydicom.Dataset:
        # Copy all attributes from additional_ds to the output dataset
        for elem in additional_ds:
            ds.add(elem)
        return ds

    return post_processor


def convert_with_metadata(
    input_file: Path,
    output_folder: Path,
    csv_loader: CSVLoaderBase,
    uid_manager: UIDMappingManager,
    collection_config: CollectionConfig,
    code_mapper: Optional[DicomCodeMapper] = None,
    tile_size: int = 1024,
    workers: int = 4,
    include_label: bool = False,
    include_overview: bool = True,
    encoding: Optional[Jpeg2kEncoder] = None
) -> None:
    """
    Convert WSI file to DICOM with full metadata propagation.

    Parameters
    ----------
    input_file : Path
        Path to input WSI file (e.g., .svs)
    output_folder : Path
        Path to output directory for DICOM files
    csv_loader : CSVLoaderBase
        Loaded CSV loader instance with metadata
    uid_manager : UIDMappingManager
        Manager for persistent UID mappings
    collection_config : CollectionConfig
        Collection-specific configuration
    code_mapper : DicomCodeMapper, optional
        Code mapper instance. If None, creates a new one.
    tile_size : int
        Tile size for output DICOM (default 1024)
    workers : int
        Number of worker threads (default 4)
    include_label : bool
        Include label image (default False)
    include_overview : bool
        Include overview/macro image (default True)
    encoding : Jpeg2kEncoder, optional
        Encoder to use. If None, uses Jpeg2kLosslessEncoder.
    """
    input_file = Path(input_file)
    output_folder = Path(output_folder)
    output_folder.mkdir(parents=True, exist_ok=True)

    # Initialize code mapper if not provided
    if code_mapper is None:
        code_mapper = DicomCodeMapper()

    # Create metadata handler
    handler = WSIMetadataHandler(
        csv_loader=csv_loader,
        uid_manager=uid_manager,
        code_mapper=code_mapper,
        collection_config=collection_config
    )

    # Load metadata from CSVs
    print(f"Loading metadata for {input_file.name}...")
    slide_data = handler.load_metadata_for_file(input_file)
    patient_data = handler.get_patient_data(slide_data)

    print(f"  Patient ID: {patient_data.patient_id}")
    print(f"  Samples: {[s.sample_id for s in slide_data.samples]}")
    if patient_data.diagnosis_meaning:
        print(f"  Diagnosis: {patient_data.diagnosis_meaning}")

    # Build wsidicomizer metadata
    wsidicom_metadata = handler.build_wsidicomizer_metadata(slide_data, patient_data)

    # Build additional metadata (clinical trial, diagnosis, etc.)
    additional_metadata = handler.build_additional_metadata(patient_data, slide_data)

    # Create post-processor
    post_processor = create_metadata_post_processor(additional_metadata)

    # Use provided encoder or default
    if encoding is None:
        encoding = Jpeg2kLosslessEncoder()

    # Run conversion
    print(f"Converting {input_file.name} to DICOM...")
    try:
        WsiDicomizer.convert(
            filepath=input_file,
            output_path=output_folder,
            metadata=wsidicom_metadata,
            metadata_post_processor=post_processor,
            tile_size=tile_size,
            include_label=include_label,
            include_overview=include_overview,
            workers=workers,
            offset_table='eot',
            preferred_source=TiffSlideSource,
            encoding=encoding
        )
        print(f"Conversion completed. Output in {output_folder}")
    except Exception as e:
        print(f"Conversion failed: {e}")
        raise


def convert_mci_wsi_to_dicom(
    input_file: Path,
    output_folder: Path,
    csv_directory: Path,
    metadata_basename: str,
    uid_base_path: Path,
    icd_o_file: Optional[Path] = None
) -> None:
    """
    Convert MCI/CCDI WSI file to DICOM with full metadata propagation.

    Convenience function that sets up all components for MCI/CCDI collection.

    Parameters
    ----------
    input_file : Path
        Path to input WSI file (e.g., .svs)
    output_folder : Path
        Path to output directory for DICOM files
    csv_directory : Path
        Path to directory containing CSV metadata files
    metadata_basename : str
        Base name for CSV files (e.g., "phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6")
    uid_base_path : Path
        Base path for UID mapping files
    icd_o_file : Path, optional
        Path to ICD-O-3 code file for diagnosis lookup
    """
    # Initialize components
    csv_loader = MCICCDILoader(metadata_basename)
    csv_loader.load(Path(csv_directory))

    uid_manager = UIDMappingManager(
        specimen_map_file=Path(uid_base_path) / "MCIspecimenIDToUIDMap.csv",
        study_uid_map_file=Path(uid_base_path) / "MCIstudyIDToUIDMap.csv",
        study_datetime_map_file=Path(uid_base_path) / "MCIstudyIDToDateTimeMap.csv"
    )

    code_mapper = DicomCodeMapper(icd_o_file=icd_o_file)

    convert_with_metadata(
        input_file=input_file,
        output_folder=output_folder,
        csv_loader=csv_loader,
        uid_manager=uid_manager,
        collection_config=MCI_CCDI_CONFIG,
        code_mapper=code_mapper
    )


# Convenience export
__all__ = [
    'convert_with_metadata',
    'convert_mci_wsi_to_dicom',
    'create_metadata_post_processor',
    'Jpeg2kLosslessEncoder',
]
