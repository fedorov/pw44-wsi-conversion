#!/usr/bin/env python3
"""
Test script for sample5 conversion.

This script tests the metadata handler and converter with the sample5
test data (0DWWQ6.svs, patient PBCPZR from CCDI/MCI collection).

Expected metadata:
- PatientID: PBCPZR
- PatientSex: M
- Diagnosis: 9470/3 Medulloblastoma, NOS
- Anatomy: Brain stem (C71.7)
- Fixation: OCT
- Staining: H&E
- ClinicalTrialProtocolID: phs002790
"""

import sys
from pathlib import Path

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from csv_loaders import MCICCDILoader
from uid_manager import UIDMappingManager
from code_mapper import DicomCodeMapper
from metadata_handler import WSIMetadataHandler
from collection_config import MCI_CCDI_CONFIG
from converter import convert_mci_wsi_to_dicom


# Paths for test data
SCRIPT_DIR = Path(__file__).parent
BASE_DIR = SCRIPT_DIR.parent
TEST_DATA_DIR = BASE_DIR / "test_data" / "sample5"
CSV_DIR = BASE_DIR / "idc-wsi-conversion"
INPUT_FILE = TEST_DATA_DIR / "src" / "0DWWQ6.svs"
OUTPUT_DIR = TEST_DATA_DIR / "converted"
UID_DIR = SCRIPT_DIR  # UID maps stored in claude-solution

METADATA_BASENAME = "phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6"


def test_csv_loader():
    """Test CSV loading and lookups."""
    print("\n=== Testing CSV Loader ===")

    loader = MCICCDILoader(METADATA_BASENAME)
    loader.load(CSV_DIR)

    # Test file lookup
    filename = "0DWWQ6.svs"
    sample_ids = loader.get_samples_for_file(filename)
    print(f"Samples for {filename}: {sample_ids}")
    assert len(sample_ids) >= 1, f"Expected samples for {filename}"

    # Test sample data
    for sample_id in sample_ids:
        sample_data = loader.get_sample_data(sample_id)
        print(f"\nSample {sample_id}:")
        print(f"  Participant: {sample_data.participant_id}")
        print(f"  Anatomic site: {sample_data.anatomic_site}")
        print(f"  Tumor status: {sample_data.tumor_status}")

        # Test participant data
        participant = loader.get_participant_data(sample_data.participant_id)
        print(f"\nParticipant {sample_data.participant_id}:")
        print(f"  Sex: {participant.get('sex_at_birth')}")
        print(f"  Race: {participant.get('race')}")

        # Test diagnosis data
        diagnosis = loader.get_diagnosis_data(sample_data.participant_id, sample_id)
        print(f"\nDiagnosis:")
        print(f"  Code: {diagnosis.get('diagnosis')}")
        print(f"  System: {diagnosis.get('diagnosis_classification_system')}")
        print(f"  Anatomic site: {diagnosis.get('anatomic_site')}")

        # Test imaging data
        imaging = loader.get_imaging_data(filename, sample_id)
        print(f"\nImaging data:")
        print(f"  Fixation: {imaging.get('fixation_embedding_method')}")
        print(f"  Staining: {imaging.get('staining_method')}")
        print(f"  Magnification: {imaging.get('magnification')}")

    print("\n[PASS] CSV loader tests passed")
    return loader


def test_code_mapper():
    """Test code mapping functions."""
    print("\n=== Testing Code Mapper ===")

    mapper = DicomCodeMapper()

    # Test anatomy mapping
    anatomy = mapper.map_anatomy_to_snomed("C71.7 : Brain stem")
    print(f"Anatomy mapping (C71.7 : Brain stem):")
    print(f"  Code: {anatomy.value if anatomy else None}")
    print(f"  Meaning: {anatomy.meaning if anatomy else None}")
    assert anatomy is not None, "Expected anatomy mapping for C71.7"
    assert anatomy.value == "15926001", f"Expected 15926001, got {anatomy.value}"

    # Test fixation mapping
    fix_code, embed_code = mapper.map_fixation_to_codes("OCT")
    print(f"\nFixation mapping (OCT):")
    print(f"  Fixative: {fix_code.meaning if fix_code else None}")
    print(f"  Embedding: {embed_code.meaning if embed_code else None}")

    # Test staining mapping
    stains = mapper.map_staining_to_codes("H&E")
    print(f"\nStaining mapping (H&E):")
    for stain in stains:
        print(f"  {stain.meaning} ({stain.value})")
    assert len(stains) == 2, "Expected 2 stains for H&E"

    # Test sex mapping
    sex = mapper.map_sex("Male")
    print(f"\nSex mapping (Male): {sex}")
    assert sex == "M", f"Expected M, got {sex}"

    # Test diagnosis resolution
    diagnosis_data = {
        'diagnosis': "9470/3 : Medulloblastoma, NOS",
        'diagnosis_classification_system': "ICD-O-3.2"
    }
    code, scheme, meaning = mapper.resolve_diagnosis_code(diagnosis_data)
    print(f"\nDiagnosis mapping:")
    print(f"  Code: {code}")
    print(f"  Scheme: {scheme}")
    print(f"  Meaning: {meaning}")
    assert code == "9470/3", f"Expected 9470/3, got {code}"

    print("\n[PASS] Code mapper tests passed")
    return mapper


def test_uid_manager():
    """Test UID management."""
    print("\n=== Testing UID Manager ===")

    # Use temp files for testing
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        manager = UIDMappingManager(
            specimen_map_file=tmpdir / "specimen_map.csv",
            study_uid_map_file=tmpdir / "study_map.csv",
            study_datetime_map_file=tmpdir / "datetime_map.csv"
        )

        # Test UID generation
        uid1 = manager.generate_new_uid()
        print(f"Generated UID: {uid1}")
        assert uid1.startswith("2.25."), f"Expected 2.25.* prefix, got {uid1}"

        # Test specimen UID persistence
        spec_uid1 = manager.get_or_create_specimen_uid("SAMPLE001")
        spec_uid2 = manager.get_or_create_specimen_uid("SAMPLE001")
        print(f"Specimen UID (first): {spec_uid1}")
        print(f"Specimen UID (second): {spec_uid2}")
        assert spec_uid1 == spec_uid2, "Specimen UIDs should be consistent"

        # Test study UID persistence
        study_uid1 = manager.get_or_create_study_uid("PATIENT001")
        study_uid2 = manager.get_or_create_study_uid("PATIENT001")
        print(f"Study UID (first): {study_uid1}")
        print(f"Study UID (second): {study_uid2}")
        assert study_uid1 == study_uid2, "Study UIDs should be consistent"

        # Test reload
        manager2 = UIDMappingManager(
            specimen_map_file=tmpdir / "specimen_map.csv",
            study_uid_map_file=tmpdir / "study_map.csv",
            study_datetime_map_file=tmpdir / "datetime_map.csv"
        )
        spec_uid3 = manager2.get_or_create_specimen_uid("SAMPLE001")
        print(f"Specimen UID (after reload): {spec_uid3}")
        assert spec_uid1 == spec_uid3, "Specimen UID should persist across instances"

    print("\n[PASS] UID manager tests passed")


def test_metadata_handler():
    """Test metadata handler with sample5 data."""
    print("\n=== Testing Metadata Handler ===")

    # Initialize components
    loader = MCICCDILoader(METADATA_BASENAME)
    loader.load(CSV_DIR)

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        uid_manager = UIDMappingManager(
            specimen_map_file=tmpdir / "specimen_map.csv",
            study_uid_map_file=tmpdir / "study_map.csv"
        )

        code_mapper = DicomCodeMapper()

        handler = WSIMetadataHandler(
            csv_loader=loader,
            uid_manager=uid_manager,
            code_mapper=code_mapper,
            collection_config=MCI_CCDI_CONFIG
        )

        # Load metadata for test file
        slide_data = handler.load_metadata_for_file(INPUT_FILE)
        print(f"Slide ID: {slide_data.slide_id}")
        print(f"Filename: {slide_data.filename}")
        print(f"Number of samples: {len(slide_data.samples)}")

        for sample in slide_data.samples:
            print(f"\nSample {sample.sample_id}:")
            print(f"  Participant: {sample.participant_id}")
            print(f"  Fixation: {sample.fixation_method}")
            print(f"  Staining: {sample.staining_method}")

        # Get patient data
        patient_data = handler.get_patient_data(slide_data)
        print(f"\nPatient data:")
        print(f"  ID: {patient_data.patient_id}")
        print(f"  Sex: {patient_data.sex}")
        print(f"  Diagnosis: {patient_data.diagnosis_meaning}")

        # Verify expected values
        assert patient_data.patient_id == "PBCPZR", f"Expected PBCPZR, got {patient_data.patient_id}"
        assert patient_data.sex == "Male", f"Expected Male, got {patient_data.sex}"
        assert "Medulloblastoma" in (patient_data.diagnosis_meaning or ""), "Expected Medulloblastoma diagnosis"

        # Build wsidicomizer metadata
        metadata = handler.build_wsidicomizer_metadata(slide_data, patient_data)
        print(f"\nWsiDicomizerMetadata:")
        print(f"  Study UID: {metadata.study.uid}")
        print(f"  Patient ID: {metadata.patient.identifier}")
        print(f"  Patient Sex: {metadata.patient.sex}")
        print(f"  Slide ID: {metadata.slide.identifier}")

        # Build additional metadata
        additional = handler.build_additional_metadata(patient_data, slide_data)
        print(f"\nAdditional DICOM attributes:")
        print(f"  ClinicalTrialProtocolID: {additional.ClinicalTrialProtocolID}")
        print(f"  ClinicalTrialSubjectID: {additional.ClinicalTrialSubjectID}")
        if hasattr(additional, 'AdmittingDiagnosesDescription'):
            print(f"  AdmittingDiagnosesDescription: {additional.AdmittingDiagnosesDescription}")

    print("\n[PASS] Metadata handler tests passed")


def test_full_conversion():
    """Test full conversion with metadata (requires input file)."""
    print("\n=== Testing Full Conversion ===")

    if not INPUT_FILE.exists():
        print(f"[SKIP] Input file not found: {INPUT_FILE}")
        return

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Input: {INPUT_FILE}")
    print(f"Output: {OUTPUT_DIR}")

    try:
        convert_mci_wsi_to_dicom(
            input_file=INPUT_FILE,
            output_folder=OUTPUT_DIR,
            csv_directory=CSV_DIR,
            metadata_basename=METADATA_BASENAME,
            uid_base_path=UID_DIR
        )
        print("\n[PASS] Full conversion completed")

        # List output files
        output_files = list(OUTPUT_DIR.glob("*.dcm"))
        print(f"\nOutput files ({len(output_files)}):")
        for f in output_files:
            print(f"  {f.name} ({f.stat().st_size / 1024 / 1024:.1f} MB)")

    except Exception as e:
        print(f"\n[FAIL] Conversion failed: {e}")
        import traceback
        traceback.print_exc()


def verify_dicom_output():
    """Verify DICOM output metadata."""
    print("\n=== Verifying DICOM Output ===")

    output_files = list(OUTPUT_DIR.glob("*.dcm"))
    if not output_files:
        print("[SKIP] No output files found")
        return

    import pydicom

    for dcm_file in output_files[:1]:  # Check first file
        print(f"\nVerifying {dcm_file.name}:")

        ds = pydicom.dcmread(dcm_file, stop_before_pixels=True)

        # Check key attributes
        checks = [
            ("PatientID", "PBCPZR"),
            ("PatientSex", "M"),
            ("ClinicalTrialProtocolID", "phs002790"),
        ]

        for attr, expected in checks:
            actual = getattr(ds, attr, None)
            status = "PASS" if actual == expected else "FAIL"
            print(f"  [{status}] {attr}: {actual} (expected: {expected})")

        # Print additional info
        print(f"\n  StudyInstanceUID: {ds.StudyInstanceUID}")
        print(f"  SeriesInstanceUID: {ds.SeriesInstanceUID}")
        print(f"  Modality: {ds.Modality}")

        if hasattr(ds, 'AdmittingDiagnosesDescription'):
            print(f"  AdmittingDiagnosesDescription: {ds.AdmittingDiagnosesDescription}")

        if hasattr(ds, 'SpecimenDescriptionSequence'):
            print(f"  Specimens: {len(ds.SpecimenDescriptionSequence)}")
            for i, spec in enumerate(ds.SpecimenDescriptionSequence):
                print(f"    [{i}] {spec.SpecimenIdentifier}: {getattr(spec, 'SpecimenShortDescription', 'N/A')}")


def main():
    """Run all tests."""
    print("=" * 60)
    print("WSI Metadata Handler Test Suite")
    print("Test data: sample5 (0DWWQ6.svs, patient PBCPZR)")
    print("=" * 60)

    # Check prerequisites
    if not CSV_DIR.exists():
        print(f"[ERROR] CSV directory not found: {CSV_DIR}")
        return 1

    # Run tests
    test_csv_loader()
    test_code_mapper()
    test_uid_manager()
    test_metadata_handler()

    # Optional: run full conversion (takes time)
    if "--convert" in sys.argv:
        test_full_conversion()
        verify_dicom_output()
    else:
        print("\n[INFO] Use --convert flag to run full conversion test")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
