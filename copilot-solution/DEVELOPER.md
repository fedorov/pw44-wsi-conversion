# Developer Guide

## Architecture Overview

### Design Philosophy

The metadata propagation system follows a **pipeline architecture** with clear separation of concerns:

```
CSV Data → Loader → Domain Model → Builder → DICOM Output
```

**Key Design Decisions:**

1. **Domain-Driven Design**: The `DomainMetadata` dataclass decouples data loading from DICOM serialization, making it easier to:
   - Add new data sources (e.g., different dataset formats)
   - Test business logic independently
   - Support multiple output formats (not just DICOM)

2. **Registry Pattern**: `UIDRegistry` ensures UID stability across conversion runs, critical for:
   - Re-running conversions (updates, corrections)
   - Maintaining referential integrity in PACS systems
   - Audit trails and reproducibility

3. **Code Tables as Data**: Storing mappings in CSV files (not hardcoded) enables:
   - Non-programmer updates to terminology mappings
   - Version control of coding system changes
   - Easy addition of new anatomic sites or specimen types

4. **Two-Phase Metadata**: Using both `WsiDicomizerMetadata` (wsidicom native) and pydicom `Dataset` (supplement) because:
   - wsidicom doesn't model all WSI-specific attributes yet
   - Allows gradual migration as wsidicom API evolves
   - Keeps metadata post-processor pattern for custom fields

## Component Responsibilities

### ccdi_loader.py
**Purpose**: Transform CCDI CSV tables into normalized domain objects

**Key Methods:**
- `load_slide(filename)` - Main entry point, returns `DomainMetadata`
- `_find_*_row()` - CSV join operations
- `_build_*_info()` - Map CSV columns → dataclass fields

**Extension Points:**
- Override `_load_*_map()` methods to customize code table loading
- Subclass for other datasets (GTEx, GDC, MCI) with different CSV schemas
- Add new code tables in `codes/` directory

**Testing Strategy:**
```python
# Create minimal test CSVs with 1-2 rows
# Mock code tables to avoid large fixtures
# Test multi-specimen slides explicitly
```

### metadata_builder.py
**Purpose**: Convert domain model to DICOM-compliant metadata

**Key Methods:**
- `build()` - Main entry point, returns tuple (WsiDicomizerMetadata, Dataset)
- `_build_wsidicom_metadata()` - Primary specimen only (wsidicom limitation)
- `_build_pydicom_supplement()` - All specimens + clinical trial + prep sequences

**Extension Points:**
- `_add_*_fields()` methods for new DICOM modules
- Override `_build_specimen_prep_sequence()` for custom processing workflows
- Add new code sequences in `_build_code_item()`

**DICOM Compliance Notes:**
- Type 1 attributes: Must have value
- Type 2 attributes: Must be present (can be empty string)
- Type 3 attributes: Optional
- Use empty strings for missing Type 2 (e.g., `ClinicalTrialSiteID`)

### uid_registry.py
**Purpose**: Persistent storage for DICOM UIDs and study timestamps

**SQLite Schema:**
```sql
studies(dataset, patient_id, study_instance_uid, created_at)
specimens(dataset, specimen_id, specimen_uid, created_at)
study_datetimes(dataset, study_id, study_datetime, created_at)
```

**Thread Safety**: Uses `threading.Lock()` for concurrent access

**UID Generation**: Uses `pydicom.uid.generate_uid()` which produces UIDs with format:
- Prefix: `1.2.826.0.1.3680043.8.498` (pydicom's registered root)
- Suffix: Random 128-bit UUID converted to decimal

**Migration Path**: To use custom UID root, modify `generate_uid()` call:
```python
from pydicom.uid import generate_uid
uid = generate_uid(prefix="2.25.")  # For 2.25-based UIDs
```

## Adding Support for New Datasets

### Example: Adding GTEx Support

1. **Create GTEx Loader** (`gtex_loader.py`):
```python
class GTExMetadataLoader:
    def __init__(self, gtex_csv: str, codes_dir: str):
        self.gtex_csv = Path(gtex_csv)
        self._tissue_map = self._load_gtex_tissue_map()
    
    def load_slide(self, specimen_id: str) -> DomainMetadata:
        # Parse GTEx CSV format
        # Map GTEx tissue codes → SNOMED
        # Return DomainMetadata
        pass
```

2. **Add GTEx Code Tables** (`codes/gtex_tissue_map.csv`):
```csv
gtex_tissue,snomed_code,snomed_scheme,snomed_meaning
Lung,39607008,SCT,Lung
Brain - Cerebellum,113305005,SCT,Cerebellum
```

3. **Update Converter Script**:
```python
from gtex_loader import GTExMetadataLoader

loader = GTExMetadataLoader(gtex_csv, codes_dir)
metadata = loader.load_slide(specimen_id)
# Rest is identical - builder is dataset-agnostic
```

### Common Patterns by Dataset

| Dataset | Primary Key | Multi-Specimen? | Diagnosis Source | UID Strategy |
|---------|-------------|-----------------|------------------|--------------|
| CCDI/MCI | filename | Yes (multiple sample_ids) | Separate diagnosis CSV | patient_id → StudyUID |
| TCGA/GDC | filename (TCGA ID embedded) | No | Filename parsing | patient_id → StudyUID |
| GTEx | specimen_id | No | N/A (normal tissue) | subject_id → StudyUID |

## Code Table Management

### Adding New Anatomy Mappings

Edit `codes/ccdi_anatomy_map.csv`:
```csv
icdo3_topography,snomed_code,snomed_scheme,snomed_meaning
C41.1 : Mandible,91609006,SCT,Mandible
```

**Validation**: Run loader test to ensure code loads:
```bash
.venv/bin/python -c "from ccdi_loader import CCDIMetadataLoader; \
  loader = CCDIMetadataLoader(...); \
  print(loader._anatomy_map['C41.1 : Mandible'])"
```

### Handling Unknown Codes

**Current Behavior**: Unknown ICD-O-3/race values silently result in `None` SNOMED codes

**Recommended Enhancement**:
```python
def _load_anatomy_map(self):
    # ... existing code ...
    # Add validation
    if icdo3 not in self._anatomy_map:
        logging.warning(f"Unknown anatomy code: {icdo3}")
```

## Troubleshooting

### "Module not found" errors
**Cause**: Relative imports fail when running modules directly
**Fix**: Already handled with try/except fallback to absolute imports

### UID Registry lock contention
**Symptom**: Slow performance with `workers > 1` in wsidicomizer
**Fix**: Use single worker or implement read-through cache

### Missing DICOM attributes
**Check**: Run `dciodvfy` validation
**Common Issues**:
- Missing Type 2 attributes (add empty string)
- Wrong VR (Value Representation) - check DICOM standard
- Sequence nesting issues (use `DicomSequence()` wrapper)

### Study DateTime not persisting
**Cause**: `study_id` parameter doesn't match `patient_id` used for StudyUID
**Fix**: Ensure both use same ID:
```python
study_uid = registry.get_or_create_study_uid(patient_id, "CCDI")
study_dt = registry.get_or_create_study_datetime(patient_id, dt, "CCDI")
```

### Multi-specimen slides show only one specimen
**Cause**: `WsiDicomizerMetadata` only accepts single specimen
**Solution**: Primary specimen in wsidicom metadata, additional specimens in pydicom supplement `SpecimenDescriptionSequence`

## Performance Considerations

### Large Slide Conversion (>10GB)
- Use `tile_size=512` or `tile_size=1024` (larger = fewer tiles = faster)
- Set `workers=1` to avoid memory pressure
- Consider `include_levels` to skip intermediate pyramid levels

### Batch Conversion
```python
for slide_file in slide_directory.glob("*.svs"):
    try:
        convert_ccdi_slide(slide_file, output_dir, ...)
    except Exception as e:
        logging.error(f"Failed to convert {slide_file}: {e}")
        continue  # Don't stop batch on single failure
```

### UID Registry Growth
**Current**: SQLite grows indefinitely
**Future Enhancement**: Add archival/cleanup for old entries
```python
def archive_old_studies(self, days_old=365):
    cutoff = datetime.now() - timedelta(days=days_old)
    # Move to archive table or separate DB
```

## Testing Strategy

### Unit Tests
- **Loader**: Mock CSV readers, test code table lookups
- **Builder**: Test dataclass → DICOM mapping with minimal fixtures
- **Registry**: Test UID persistence, concurrency

### Integration Tests
- **End-to-end**: Real CSV + small test slide (1-2MB)
- **Validation**: Run `dciodvfy` on outputs
- **Comparison**: Compare metadata fields vs. PixelMed reference outputs

### Test Data Requirements
- Minimal CCDI CSVs with 1-2 patients, 2-3 specimens
- Small SVS file (~1-5MB) with known metadata
- Expected DICOM output for regression testing

## Future Enhancements

### Priority 1: Core Functionality
1. **SpecimenPreparationSequence completeness**
   - Add collection method codes (biopsy, excision, etc.)
   - Add fixation duration, embedding duration timestamps
   - Support for parent specimen relationships beyond sample→vial→portion

2. **Enhanced validation**
   - Pre-conversion checks (missing CSVs, invalid slide IDs)
   - Post-conversion DICOM validation (automated dciodvfy checks)
   - Code table validation (ensure all referenced codes exist)

3. **Logging infrastructure**
   - Structured logging (JSON format)
   - Per-slide log files
   - Metadata mapping audit trail

### Priority 2: Usability
1. **CLI interface**
   - Argparse-based command-line tool
   - Config file support (YAML/TOML)
   - Batch conversion with progress bars

2. **Error recovery**
   - Checkpoint/resume for large batches
   - Partial conversion on specimen-level failures
   - Detailed error reports (missing codes, malformed data)

### Priority 3: Scale
1. **Parallel processing**
   - Multi-process converter for batches
   - Distributed UID registry (Redis/PostgreSQL)
   - Object storage support (S3, Azure Blob)

2. **Metadata caching**
   - Cache loaded CSVs in memory for batch conversions
   - Compiled code table lookups (dict vs. CSV)

## Dependencies

### Core Libraries
- **pydicom** (3.0+): DICOM dataset manipulation, UID generation
- **wsidicom** (0.29+): WSI DICOM metadata model
- **wsidicomizer** (0.24+): WSI conversion engine
- **tifffile** (2023.8+): TIFF header parsing (datetime extraction)

### Version Constraints
- **tifffile**: Pin to `2023.8.30` to avoid OpenTile issues (per sardana-dcm)
- **pydicom**: `>=2.4` for `generate_uid()` support
- **wsidicom**: `>=0.9` for Patient/Study/Series API

### Optional
- **pandas**: For efficient CSV processing in batches
- **pydantic**: For schema validation of domain dataclasses
- **structlog**: For structured logging

## Code Organization Rationale

```
copilot-solution/
├── metadata_schema.py      # Domain model (no dependencies)
├── uid_registry.py          # Persistence layer (sqlite3 only)
├── tiff_datetime.py         # I/O utility (tifffile only)
├── ccdi_loader.py           # Dataset adapter (csv + schema)
├── metadata_builder.py      # Output adapter (pydicom + wsidicom)
├── convert_ccdi.py          # Application/orchestration
└── codes/                   # Data (no code)
```

**Dependency Flow**:
```
convert_ccdi.py
    ↓
ccdi_loader.py → metadata_schema.py
    ↓
metadata_builder.py → uid_registry.py
    ↓
wsidicomizer
```

**Benefits**:
- Clean separation allows testing each layer independently
- Schema changes don't force loader/builder changes
- Can swap loaders without touching builder
- Can add new output formats without touching loaders

## Common Customization Scenarios

### Scenario 1: Add Custom Private Tags
**Location**: `metadata_builder.py` → `_build_pydicom_supplement()`
```python
# Add custom hospital ID
ds.add_new((0x0099, 0x0010), 'LO', 'HOSPITAL_NAME')
ds.add_new((0x0099, 0x1001), 'LO', hospital_id)
```

### Scenario 2: Change UID Root
**Location**: `uid_registry.py` → `get_or_create_study_uid()`
```python
# Use institution-specific root
study_uid = "2.25." + str(uuid.uuid4().int)
```

### Scenario 3: Custom Specimen Processing
**Location**: `metadata_builder.py` → `_build_specimen_prep_sequence()`
```python
# Add custom staining protocol
if specimen.staining_method == "IHC-CD20":
    # Add IHC-specific prep steps
    pass
```

### Scenario 4: Alternative Study Grouping
**Location**: `ccdi_loader.py` + `metadata_builder.py`
```python
# Group by collection event instead of patient
study_uid = registry.get_or_create_study_uid(
    f"{patient_id}_{collection_event}", 
    "CCDI"
)
```

## Git Workflow Recommendations

### Branch Strategy
- `main` - stable, tested conversions
- `dev` - integration branch
- `feature/*` - new dataset support, enhancements
- `fix/*` - bug fixes, metadata corrections

### Commit Message Format
```
type(scope): description

[optional body]

Refs: #issue-number
```

Examples:
```
feat(loader): add GTEx tissue mapping support
fix(builder): add missing ClinicalTrialSiteID (Type 2)
docs(codes): update anatomy map with CNS codes
test(ccdi): add multi-specimen slide test case
```

### Code Review Checklist
- [ ] Code table changes reviewed by medical informaticist
- [ ] DICOM output validated with dciodvfy
- [ ] Tests added for new code paths
- [ ] README/Developer Guide updated
- [ ] No hardcoded file paths in committed code
