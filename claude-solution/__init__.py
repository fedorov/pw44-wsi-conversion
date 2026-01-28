"""
WSI to DICOM Metadata Handler Package

This package provides classes for propagating metadata from CSV tables
into DICOM attributes when converting WSI files using wsidicomizer.
"""

from .collection_config import CollectionConfig, MCI_CCDI_CONFIG
from .uid_manager import UIDMappingManager
from .code_mapper import DicomCodeMapper
from .csv_loaders import CSVLoaderBase, MCICCDILoader
from .specimen_builder import SpecimenMetadataBuilder
from .metadata_handler import WSIMetadataHandler, SlideData, SampleData, PatientData
from .converter import convert_with_metadata

__all__ = [
    'CollectionConfig',
    'MCI_CCDI_CONFIG',
    'UIDMappingManager',
    'DicomCodeMapper',
    'CSVLoaderBase',
    'MCICCDILoader',
    'SpecimenMetadataBuilder',
    'WSIMetadataHandler',
    'SlideData',
    'SampleData',
    'PatientData',
    'convert_with_metadata',
]
