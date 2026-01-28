# Claude Context: WSI to DICOM Metadata Handler

This file provides context for Claude when working on this codebase.

## Project Overview

Python library for propagating metadata from CSV tables into DICOM attributes when converting Whole Slide Images (WSI) using wsidicomizer. Replaces the pixelmed Java-based converter with a pure Python solution.

## Architecture

```
CSV Files → CSVLoaderBase → WSIMetadataHandler → WsiDicomizerMetadata + post-processor → WsiDicomizer.convert()
                ↑                   ↑
          UIDMappingManager    DicomCodeMapper
```

### Component Responsibilities

| Component | File | Responsibility |
|-----------|------|----------------|
| `CSVLoaderBase` | csv_loaders.py | Abstract base for collection-specific CSV parsing |
| `MCICCDILoader` | csv_loaders.py | MCI/CCDI 4-file format (pathology_file, sample, participant, diagnosis) |
| `UIDMappingManager` | uid_manager.py | Persistent UID mappings across conversion runs |
| `DicomCodeMapper` | code_mapper.py | Translate CSV values to DICOM coded concepts |
| `SpecimenMetadataBuilder` | specimen_builder.py | Build specimen preparation metadata |
| `WSIMetadataHandler` | metadata_handler.py | Main orchestrator, builds wsidicomizer metadata |
| `CollectionConfig` | collection_config.py | Collection-specific settings (sponsor, protocol, etc.) |

### Data Flow

1. `CSVLoaderBase.load()` - Parse CSV files into pandas DataFrames
2. `WSIMetadataHandler.load_metadata_for_file()` - Resolve file → samples → participant → diagnosis
3. `WSIMetadataHandler.build_wsidicomizer_metadata()` - Create `WsiDicomizerMetadata` object
4. `WSIMetadataHandler.build_additional_metadata()` - Create `pydicom.Dataset` for post-processor
5. `WsiDicomizer.convert()` - Run conversion with metadata and post-processor callback

## Key Design Decisions

### 1. UUID-based DICOM UIDs (2.25.{integer})

**Decision**: Use UUID-derived OIDs in format `2.25.{uuid_as_integer}`

**Rationale**:
- Matches pixelmed's `UUIDBasedOID` approach for consistency with existing conversions
- No need for organizational OID root
- Guaranteed uniqueness without central registry
- Persistent mappings stored in CSV files ensure same input → same UID across runs

**Implementation**: `uid_manager.py:generate_new_uid()`

### 2. Post-processor Pattern for Additional Attributes

**Decision**: Use wsidicomizer's `metadata_post_processor` callback for attributes not in `WsiDicomizerMetadata`

**Rationale**:
- `WsiDicomizerMetadata` only exposes common DICOM attributes
- Clinical Trial Module, Admitting Diagnoses need direct pydicom access
- Post-processor is called for each output file, can add arbitrary attributes

**Implementation**: `converter.py:create_metadata_post_processor()`

### 3. Relational CSV Model

**Decision**: Support multi-file CSV with relational lookups (file → sample → participant → diagnosis)

**Rationale**:
- Matches CCDI Submission Template structure
- Allows normalized data without duplication
- Supports multiple samples per file, multiple diagnoses per participant

**Implementation**: `csv_loaders.py:MCICCDILoader`

### 4. Try/Except Import Pattern

**Decision**: Use try/except for relative vs absolute imports

```python
try:
    from .module import Class  # When used as package
except ImportError:
    from module import Class   # When run directly
```

**Rationale**:
- Allows running test scripts directly (`python test_sample5.py`)
- Also works when imported as package (`from claude_solution import ...`)

## Code Patterns

### Adding a New Code Mapping

In `code_mapper.py`, add to the appropriate dictionary:

```python
# Anatomy: ICD-O topography code → (SNOMED CT code, meaning)
ANATOMY_CODES = {
    "C50.9": ("76752008", "Breast"),  # Add new mapping
    ...
}
```

### Adding a New Collection

1. Create loader in `csv_loaders.py`:
```python
class MyCollectionLoader(CSVLoaderBase):
    def load(self, csv_directory: Path) -> None:
        # Load your CSV structure
        pass

    def get_samples_for_file(self, filename: str) -> List[str]:
        # Return sample IDs for filename
        pass

    # Implement remaining abstract methods...
```

2. Add config in `collection_config.py`:
```python
MY_COLLECTION_CONFIG = CollectionConfig(
    sponsor_name="My Sponsor",
    protocol_id="my-protocol-123",
    protocol_name="My Collection Name",
    coordinating_center="My Institution"
)
```

3. Add convenience function in `converter.py` if needed.

### Building Specimen Metadata

Use `SpecimenMetadataBuilder` for consistent specimen preparation:

```python
builder = SpecimenMetadataBuilder(code_mapper)
specimen = builder.build_specimen(
    specimen_id="SAMPLE123",
    specimen_uid=uid_manager.get_or_create_specimen_uid("SAMPLE123"),
    fixation_method="FFPE",
    anatomic_site="C50.9 : Breast"
)
```

## Testing

### Running Tests

```bash
cd claude-solution
source .venv/bin/activate
python test_sample5.py          # Unit tests only
python test_sample5.py --convert  # Full conversion test
```

### Test Data Location

- SVS file: `../test_data/sample5/src/0DWWQ6.svs`
- CSV files: `../idc-wsi-conversion/`
- Expected output: Compare with `../test_data/sample5/idc/` (pixelmed output)

### Adding New Tests

Add test functions to `test_sample5.py`:

```python
def test_my_feature():
    """Test description."""
    print("\n=== Testing My Feature ===")
    # Setup
    # Assert
    print("[PASS] My feature tests passed")
```

### Verification Checklist

When modifying conversion:
- [ ] Patient ID matches CSV
- [ ] Study UID is persistent (same input → same UID)
- [ ] Specimen UIDs are persistent
- [ ] Anatomy codes map to correct SNOMED CT
- [ ] Clinical Trial attributes present
- [ ] Diagnosis codes in ICD-O-3 format

## Known Limitations

### Missing Anatomy Mappings

`code_mapper.py` has ~80 ICD-O topography codes. If a code is missing:
1. Look up SNOMED CT equivalent
2. Add to `ANATOMY_CODES` dictionary
3. Format: `"C##.#": ("snomed_code", "meaning")`

### Unsupported CSV Formats

Currently only `MCICCDILoader` is fully implemented. Stubs exist for:
- `GTExLoader` - GTEx collection format
- Other collections need new loader classes

### Single Diagnosis per Slide

Current implementation uses first diagnosis found. Multiple diagnoses per participant exist in data but only first is used for `AdmittingDiagnosesCodeSequence`.

### No Label Image Extraction

`include_label=False` by default because label images often contain PHI. Enable carefully.

## Dependencies

### wsidicom/wsidicomizer API

Pinned to specific commits for stability:

```
wsidicom @ git+https://github.com/imi-bigpicture/wsidicom.git@09a052e4
wsidicomizer @ git+https://github.com/imi-bigpicture/wsidicomizer.git@f78a8382
```

Key classes used:
- `wsidicom.metadata`: `Patient`, `PatientSex`, `Study`, `Series`, `Slide`, `Image`, `SlideSample`, `Staining`, `Specimen`, `Fixation`, `Embedding`
- `wsidicom.conceptcode`: `SpecimenStainsCode`, `SpecimenFixativesCode`, `SpecimenEmbeddingMediaCode`, `AnatomicPathologySpecimenTypesCode`
- `wsidicomizer.metadata`: `WsiDicomizerMetadata`, `MetadataPostProcessor`
- `wsidicomizer`: `WsiDicomizer`

### API Notes

- `Series()` takes only `uid` and `number`, not `description`
- `Pyramid` class is in `wsidicom.series.pyramid`, not `wsidicom.metadata`
- Use `image` parameter in `WsiDicomizerMetadata` for acquisition datetime

## File Structure

```
claude-solution/
├── __init__.py              # Package exports
├── collection_config.py     # CollectionConfig dataclass + presets
├── uid_manager.py           # UIDMappingManager - persistent UIDs
├── code_mapper.py           # DicomCodeMapper - SNOMED/ICD-O translations
├── csv_loaders.py           # CSVLoaderBase + MCICCDILoader
├── specimen_builder.py      # SpecimenMetadataBuilder
├── metadata_handler.py      # WSIMetadataHandler - main orchestrator
├── converter.py             # wsidicomizer integration
├── test_sample5.py          # Test script
├── requirements.txt         # Dependencies
├── README.md                # User documentation
└── CLAUDE.md                # This file (Claude context)
```

## Common Tasks

### Debug Missing Metadata

1. Check CSV loader found the file: `csv_loader.get_samples_for_file(filename)`
2. Check sample data: `csv_loader.get_sample_data(sample_id)`
3. Check participant lookup: `csv_loader.get_participant_data(participant_id)`
4. Check diagnosis lookup: `csv_loader.get_diagnosis_data(participant_id, sample_id)`

### Add New DICOM Attribute

If attribute is supported by `WsiDicomizerMetadata`:
- Add to appropriate section in `metadata_handler.py:build_wsidicomizer_metadata()`

If attribute needs direct pydicom access:
- Add to `metadata_handler.py:build_additional_metadata()`
- Will be applied via post-processor callback

### Verify Output DICOM

```bash
# Using dcmtk
dcmdump output.dcm | grep -E "PatientID|ClinicalTrial|Specimen"

# Using pydicom
python -c "import pydicom; ds = pydicom.dcmread('output.dcm'); print(ds.PatientID)"
```
