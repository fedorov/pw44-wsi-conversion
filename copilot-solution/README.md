# CCDI Metadata Loader for wsidicomizer

Provides reusable metadata propagation from CCDI CSV tables into DICOM WSI conversions using wsidicomizer.

## Features

- **CSV-driven loaders**: Join CCDI pathology_file → sample → participant → diagnosis
- **Multi-specimen slides**: Support multiple sample_ids per slide (e.g., 0DWWQ6.svs with 0DX2D2, 0DX2CX)
- **Code mapping**: ICD-O-3 → SNOMED CT anatomy/diagnosis, race/ethnicity → SNOMED/NCIt, fixative/embedding/stain → SNOMED/DCM
- **UID persistence**: SQLite registry with DICOM 2.25 UIDs (StudyInstanceUID, SpecimenUID, study datetime)
- **Specimen prep sequences**: FFPE (fixation+embedding) and OCT (fixation only), H&E staining
- **Clinical trial metadata**: Protocol ID (phs002790), sponsor, coordinating center

## Usage

```python
from copilot_solution.ccdi_loader import CCDIMetadataLoader
from copilot_solution.metadata_builder import MetadataBuilder
from copilot_solution.uid_registry import UIDRegistry

# Initialize
loader = CCDIMetadataLoader(
    pathology_csv="path/to/pathology_file.csv",
    sample_csv="path/to/sample.csv",
    participant_csv="path/to/participant.csv",
    diagnosis_csv="path/to/diagnosis.csv",
    codes_dir="copilot-solution/codes"
)
registry = UIDRegistry("uid_registry.db")

# Load metadata for a slide
metadata = loader.load_slide("0DWWQ6.svs")

# Build wsidicom metadata + pydicom supplement
builder = MetadataBuilder(registry)
wsi_metadata, supplement = builder.build(metadata)

# Pass to wsidicomizer
WsiDicomizer.convert(
    filepath=input_file,
    output_path=output_folder,
    metadata=wsi_metadata,
    metadata_post_processor=supplement,
    ...
)
```

## Directory Structure

```
copilot-solution/
├── __init__.py
├── README.md
├── metadata_schema.py      # Domain dataclasses
├── uid_registry.py         # SQLite UID storage (2.25 UIDs)
├── tiff_datetime.py        # TIFF header datetime extraction
├── ccdi_loader.py          # CSV join + parsing logic
├── metadata_builder.py     # wsidicom + pydicom builder
└── codes/                  # CSV code tables
    ├── ccdi_anatomy_map.csv           # ICD-O-3 topography → SNOMED
    ├── ccdi_race_map.csv              # Race/ethnicity → SNOMED/NCIt
    ├── ccdi_specimen_prep.csv         # Fixative/embedding/stain codes
    └── icdo3_morphology.csv           # ICD-O-3 morphology lookup
```

## Code Tables

CSV tables in `codes/` directory map between coding systems:
- **SNOMED CT**: Anatomy, specimen prep (fixative/embedding/staining), tissue types, race
- **ICD-O-3**: Diagnosis morphology/topography
- **DCM**: Optical path, illumination, container types
- **NCIt**: Ethnicity (where SNOMED unavailable)

## Validation

Run `dciodvfy` on outputs:
```bash
dciodvfy output/*.dcm
```

## Documentation

- **README.md** (this file) - Quick start and usage
- **DEVELOPER.md** - Architecture, design decisions, extension guide
- **TROUBLESHOOTING.md** - Common issues and solutions

## Testing

Run individual module tests:
```bash
cd copilot-solution
.venv/bin/python uid_registry.py        # Test UID generation
.venv/bin/python ccdi_loader.py         # Test CSV loading
.venv/bin/python metadata_builder.py    # Test metadata building
.venv/bin/python convert_ccdi.py        # Full conversion
```

Inspect generated DICOM:
```bash
.venv/bin/python inspect_dicom.py
```
