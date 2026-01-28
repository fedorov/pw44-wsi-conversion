# Common Issues and Solutions

## Problem: dciodvfy reports missing Type 2 attributes

**Symptoms**:
```
Error - Missing attribute Type 2 Required Element=<ClinicalTrialSiteID>
Error - Missing attribute Type 2 Required Element=<IssuerOfTheSpecimenIdentifierSequence>
```

**Solution**: Type 2 attributes must be present but can be empty. Add to `metadata_builder.py`:
```python
ds.ClinicalTrialSiteID = ""  # Empty string for Type 2
ds.ClinicalTrialSiteName = ""
```

---

## Problem: Wrong UID format (not 2.25-based)

**Symptoms**: UIDs start with `1.2.826...` instead of `2.25...`

**Explanation**: pydicom's `generate_uid()` uses its registered root by default. Both formats are valid DICOM.

**To force 2.25 format** (if required), modify `uid_registry.py`:
```python
import uuid
study_uid = f"2.25.{uuid.uuid4().int}"
```

---

## Problem: Multi-specimen slide shows duplicate specimens

**Symptoms**: Both specimens have identical `SpecimenIdentifier`

**Cause**: Loop variable reuse or incorrect CSV join

**Debug**:
```python
# In ccdi_loader.py, add logging
for pathology_row, sample_row in zip(pathology_rows, sample_rows):
    print(f"Processing sample_id: {sample_row['sample_id']}")
```

---

## Problem: Study datetime changes between conversions

**Symptoms**: Same slide gets different StudyDate/StudyTime on re-conversion

**Cause**: Study datetime not cached in registry

**Fix**: Ensure `study_id` matches between StudyUID and datetime calls:
```python
study_uid = registry.get_or_create_study_uid(patient_id, dataset)
study_dt = registry.get_or_create_study_datetime(patient_id, dt, dataset)
# Both use same patient_id as key
```

---

## Problem: Conversion extremely slow (>1 hour for 1GB slide)

**Possible Causes**:
1. Too many pyramid levels
2. Small tile size
3. High worker count causing memory thrashing

**Solutions**:
```python
# Reduce pyramid levels
WsiDicomizer.convert(
    ...
    include_levels=[0, 2, 4, 6],  # Skip intermediate levels
    tile_size=1024,  # Larger tiles = fewer tiles
    workers=1  # Reduce memory pressure
)
```

---

## Problem: Import errors with relative imports

**Symptoms**:
```
ImportError: attempted relative import with no known parent package
```

**Cause**: Running module directly instead of as package

**Already Fixed**: All modules use try/except for imports:
```python
try:
    from .metadata_schema import DomainMetadata
except ImportError:
    from metadata_schema import DomainMetadata
```

---

## Problem: Missing anatomy code for new ICD-O-3 site

**Symptoms**: Specimen has `anatomic_site` but `anatomic_site_snomed_code` is None

**Solution**: Add mapping to `codes/ccdi_anatomy_map.csv`:
```csv
C44.5 : Skin of trunk,181485001,SCT,Skin of trunk
```

**Validation**:
```bash
grep "C44.5" codes/ccdi_anatomy_map.csv
.venv/bin/python -c "from ccdi_loader import CCDIMetadataLoader; \
  loader = CCDIMetadataLoader(..., codes_dir='codes'); \
  print(loader._anatomy_map.get('C44.5 : Skin of trunk'))"
```

---

## Problem: Race/ethnicity code not mapping

**Symptoms**: `EthnicGroupCodeSequence` is empty

**Cause**: Race string from CSV doesn't match code table exactly

**Debug**:
```python
# In ccdi_loader.py
race = participant_row['race']
print(f"Looking for race: '{race}'")  # Note exact string with spaces
print(f"Available keys: {list(self._race_map.keys())[:5]}")
```

**Common Issue**: Extra whitespace or capitalization
```csv
# codes/ccdi_race_map.csv - must match CSV exactly
Unknown;White,White,413773004,SCT,Caucasian race,,,,,,
```

---

## Problem: Specimen preparation sequence missing steps

**Symptoms**: dciodvfy warns about incomplete specimen prep

**Cause**: Code tables missing fixation/staining entries

**Check**:
```bash
grep "OCT" codes/ccdi_fixation_embedding.csv
grep "H&E" codes/ccdi_staining.csv
```

**Add missing entries**:
```csv
# ccdi_fixation_embedding.csv
OCT,433469005,SCT,Tissue freezing medium,,,

# ccdi_staining.csv
H&E,12710003,SCT,hematoxylin stain,36879007,SCT,water soluble eosin stain
```

---

## Problem: UID registry database locked

**Symptoms**:
```
sqlite3.OperationalError: database is locked
```

**Cause**: Multiple processes accessing registry simultaneously

**Solutions**:
1. Use `workers=1` in wsidicomizer (already default)
2. Implement connection pooling
3. Switch to client-server database (PostgreSQL)

**Quick Fix**: Add timeout in `uid_registry.py`:
```python
def _init_db(self):
    with sqlite3.connect(self.db_path, timeout=30.0) as conn:
        # ...
```

---

## Problem: TIFF datetime extraction fails

**Symptoms**: `extract_scan_datetime()` returns None

**Cause**: Non-standard ImageDescription format

**Debug**:
```python
import tifffile
with tifffile.TiffFile("slide.svs") as tif:
    desc = tif.pages[0].description
    print(desc)  # Check actual format
```

**Solution**: Add new regex pattern in `tiff_datetime.py`:
```python
# Try custom format: "Scanned: 2024-01-15 10:30:00"
custom_match = re.search(
    r'Scanned:\s*(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})',
    description
)
```

---

## Problem: wsidicomizer encoding error

**Symptoms**:
```
ValueError: Photometric Interpretation YBR_ICT not supported
```

**Cause**: Encoder transfer syntax mismatch

**Fix** in `convert_ccdi.py`:
```python
class Jpeg2kLosslessEncoder(Jpeg2kEncoder):
    @property
    def transfer_syntax(self) -> UID:
        return JPEG2000Lossless  # Instead of JPEG2000
```

---

## Problem: Diagnosis code not populating

**Symptoms**: `AdmittingDiagnosesCodeSequence` is empty

**Cause**: ICD-O-3 format not parsed correctly

**Check**:
```python
# In ccdi_loader.py, add debug
diagnosis_str = diagnosis_row.get('diagnosis', '')
print(f"Raw diagnosis: '{diagnosis_str}'")
# Expected: "9470/3 : Medulloblastoma, NOS"
```

**Validate** split logic:
```python
if ' : ' in diagnosis_str:
    code, description = diagnosis_str.split(' : ', 1)
```

---

## Problem: Output directory permission denied

**Symptoms**:
```
PermissionError: [Errno 13] Permission denied: '/output/file.dcm'
```

**Solutions**:
1. Check directory exists and is writable
2. Use `output_folder.mkdir(parents=True, exist_ok=True)` (already done)
3. Check filesystem permissions
4. On NFS/network drives, verify mount permissions

---

## Problem: Memory usage grows during batch conversion

**Cause**: UID registry or CSV data cached in memory

**Solutions**:
1. Process slides in smaller batches
2. Clear registry cache periodically:
```python
# After N slides
registry = None
gc.collect()
registry = UIDRegistry(db_path)
```

3. Use streaming CSV readers for large files
