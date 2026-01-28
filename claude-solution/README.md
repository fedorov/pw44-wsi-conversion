# WSI to DICOM Metadata Handler

A Python library for propagating metadata from CSV tables into DICOM attributes when converting Whole Slide Images (WSI) using wsidicomizer.

## Overview

This package provides a modular class architecture that:
- Loads metadata from collection-specific CSV files (MCI/CCDI, GTEx, CMB formats)
- Performs relational lookups across multiple CSV tables
- Translates values to DICOM coded concepts (SNOMED CT, ICD-O-3)
- Manages persistent UID mappings across conversion runs
- Generates `WsiDicomizerMetadata` objects for wsidicomizer

## Architecture

```
CSV Files (MCI/CCDI Format)
├── pathology_file.csv  (file_name → sample_id, fixation, staining)
├── sample.csv          (sample_id → participant_id, anatomic_site)
├── participant.csv     (participant_id → sex, race)
└── diagnosis.csv       (participant_id → diagnosis codes)
            │
            ▼
┌─────────────────────────────────────────────────────────────┐
│                    MCICCDILoader                            │
│              (implements CSVLoaderBase)                     │
└─────────────────────────────────────────────────────────────┘
            │
            ├──────────────────┬──────────────────┐
            ▼                  ▼                  ▼
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│  UIDMappingManager│  │  DicomCodeMapper │  │ CollectionConfig │
│                  │  │                  │  │                  │
│ - specimen UIDs  │  │ - anatomy codes  │  │ - sponsor_name   │
│ - study UIDs     │  │ - diagnosis codes│  │ - protocol_id    │
│ - datetime maps  │  │ - fixation codes │  │ - protocol_name  │
└──────────────────┘  └──────────────────┘  └──────────────────┘
            │                  │                  │
            └──────────────────┴──────────────────┘
                               │
                               ▼
               ┌───────────────────────────────┐
               │      WSIMetadataHandler       │
               │                               │
               │ - load_metadata_for_file()    │
               │ - get_patient_data()          │
               │ - build_wsidicomizer_metadata │
               │ - build_additional_metadata   │
               └───────────────────────────────┘
                               │
               ┌───────────────┴───────────────┐
               ▼                               ▼
    ┌─────────────────────┐     ┌─────────────────────────┐
    │ WsiDicomizerMetadata│     │ pydicom.Dataset         │
    │                     │     │ (additional attributes) │
    │ - study             │     │                         │
    │ - patient           │     │ - ClinicalTrial*        │
    │ - slide             │     │ - AdmittingDiagnoses*   │
    │ - image             │     │ - PatientAge            │
    └─────────────────────┘     └─────────────────────────┘
               │                               │
               └───────────────┬───────────────┘
                               ▼
               ┌───────────────────────────────┐
               │    WsiDicomizer.convert()     │
               │                               │
               │  metadata=                    │
               │  metadata_post_processor=     │
               └───────────────────────────────┘
                               │
                               ▼
               ┌───────────────────────────────┐
               │       DICOM WSI Files         │
               └───────────────────────────────┘
```

## Features

### CSV Loading (`csv_loaders.py`)
- Abstract `CSVLoaderBase` for custom collection formats
- `MCICCDILoader` for CCDI Submission Template (4-file structure)
- `GTExLoader` stub for GTEx collection format
- Relational lookups: pathology_file → sample → participant → diagnosis

### UID Management (`uid_manager.py`)
- Persistent UID mappings stored in CSV files
- UUID-derived OID format: `2.25.{uuid_as_integer}`
- Ensures consistent UIDs across conversion runs
- Matches pixelmed's `UUIDBasedOID` approach

### Code Mapping (`code_mapper.py`)
- 80+ ICD-O topography to SNOMED CT anatomy mappings
- Fixation methods: FFPE, OCT, Formalin, PAXgene
- Staining methods: H&E, IHC, PAS, Masson trichrome
- Diagnosis resolution from ICD-O-3 format
- Sex mapping to DICOM PatientSex enum

### Collection Configuration (`collection_config.py`)
Pre-configured settings for:
- MCI/CCDI (Childhood Cancer Data Initiative)
- GTEx (Genotype-Tissue Expression)
- CMB (Cancer Model Biobank)
- CPTAC, TCGA, HTAN

### Metadata Handler (`metadata_handler.py`)
- Main orchestrator coordinating all components
- Builds `WsiDicomizerMetadata` for wsidicomizer
- Builds additional DICOM attributes via post-processor:
  - Clinical Trial Module (sponsor, protocol, subject ID)
  - Admitting Diagnoses (ICD-O-3 codes)
  - Patient Age (converted from days)

## Installation

```bash
cd claude-solution
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

## Usage

### Basic Usage

```python
from pathlib import Path
from claude_solution import (
    MCICCDILoader,
    UIDMappingManager,
    DicomCodeMapper,
    WSIMetadataHandler,
    MCI_CCDI_CONFIG,
    convert_with_metadata
)

# Initialize CSV loader
csv_loader = MCICCDILoader("phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6")
csv_loader.load(Path("/path/to/csv/directory"))

# Initialize UID manager
uid_manager = UIDMappingManager(
    specimen_map_file=Path("MCIspecimenIDToUIDMap.csv"),
    study_uid_map_file=Path("MCIstudyIDToUIDMap.csv")
)

# Initialize code mapper
code_mapper = DicomCodeMapper()

# Create metadata handler
handler = WSIMetadataHandler(
    csv_loader=csv_loader,
    uid_manager=uid_manager,
    code_mapper=code_mapper,
    collection_config=MCI_CCDI_CONFIG
)

# Load metadata for a file
slide_data = handler.load_metadata_for_file(Path("input.svs"))
patient_data = handler.get_patient_data(slide_data)

# Build wsidicomizer metadata
metadata = handler.build_wsidicomizer_metadata(slide_data, patient_data)
additional = handler.build_additional_metadata(patient_data, slide_data)
```

### Convenience Function

```python
from claude_solution import convert_mci_wsi_to_dicom

convert_mci_wsi_to_dicom(
    input_file=Path("0DWWQ6.svs"),
    output_folder=Path("output/"),
    csv_directory=Path("idc-wsi-conversion/"),
    metadata_basename="phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6",
    uid_base_path=Path("./")
)
```

## Testing

Run the test suite with sample5 data:

```bash
cd claude-solution
source .venv/bin/activate
python test_sample5.py
```

Run with full conversion:

```bash
python test_sample5.py --convert
```

### Test Data: sample5

- **File**: `0DWWQ6.svs`
- **Patient**: PBCPZR (Male)
- **Samples**: 0DX2CX, 0DX2D2
- **Anatomy**: C71.7 Brain stem → SCT 15926001
- **Diagnosis**: 9470/3 Medulloblastoma, NOS (ICD-O-3.2)
- **Fixation**: OCT
- **Staining**: H&E
- **Protocol**: phs002790

## File Structure

```
claude-solution/
├── __init__.py              # Package exports
├── collection_config.py     # Collection-specific configs
├── uid_manager.py           # Persistent UID mapping
├── code_mapper.py           # SNOMED/ICD-O code translations
├── csv_loaders.py           # CSV loading (MCICCDILoader, GTExLoader)
├── specimen_builder.py      # Specimen preparation helpers
├── metadata_handler.py      # Main orchestrator
├── converter.py             # wsidicomizer integration
├── test_sample5.py          # Test script
├── requirements.txt         # Dependencies
└── README.md                # This file
```

## DICOM Attributes Populated

### Via WsiDicomizerMetadata
| Attribute | Source |
|-----------|--------|
| PatientID | participant.csv |
| PatientName | participant.csv |
| PatientSex | participant.csv (mapped to M/F/O) |
| StudyInstanceUID | Generated, persistent |
| StudyID | participant_id |
| AccessionNumber | participant_id |
| StudyDescription | "Histopathology" |
| ContainerIdentifier | filename (slide_id) |
| SpecimenDescriptionSequence | sample.csv + pathology_file.csv |

### Via Post-Processor
| Attribute | Source |
|-----------|--------|
| ClinicalTrialSponsorName | CollectionConfig |
| ClinicalTrialProtocolID | CollectionConfig |
| ClinicalTrialProtocolName | CollectionConfig |
| ClinicalTrialSubjectID | participant_id |
| AdmittingDiagnosesDescription | diagnosis.csv |
| AdmittingDiagnosesCodeSequence | diagnosis.csv (ICD-O-3) |
| PatientAge | diagnosis.csv (age_at_diagnosis) |

## Extending for New Collections

1. Create a new loader class inheriting from `CSVLoaderBase`
2. Implement the abstract methods for your CSV format
3. Add collection config to `collection_config.py`
4. Add any collection-specific code mappings to `code_mapper.py`

```python
class MyCollectionLoader(CSVLoaderBase):
    def load(self, csv_directory: Path) -> None:
        # Load your CSV files
        pass

    def get_samples_for_file(self, filename: str) -> List[str]:
        # Return sample IDs for a given filename
        pass

    # ... implement other abstract methods
```

## Dependencies

- wsidicom (git commit 09a052e4)
- wsidicomizer (git commit f78a8382)
- pandas >= 2.0.0
- pydicom >= 2.4.0
- tifffile == 2023.8.30
- imagecodecs
- pillow
- numpy

## License

This code is provided for the IDC WSI conversion project.
