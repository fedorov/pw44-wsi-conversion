"""Quick script to inspect generated DICOM metadata."""
import pydicom
import sys

dcm_file = "/Users/af61/Desktop/PW44/wsi-conversion/test_data/sample5/copilot-output/1.2.826.0.1.3680043.8.498.57601106514112399213886558205099597776.dcm"

ds = pydicom.dcmread(dcm_file, stop_before_pixels=True)

print("=== Patient Module ===")
print(f"PatientName: {ds.get('PatientName', 'N/A')}")
print(f"PatientID: {ds.get('PatientID', 'N/A')}")
print(f"PatientSex: {ds.get('PatientSex', 'N/A')}")
print(f"PatientAge: {ds.get('PatientAge', 'N/A')}")
print(f"EthnicGroup: {ds.get('EthnicGroup', 'N/A')}")

print("\n=== Study Module ===")
print(f"StudyInstanceUID: {ds.get('StudyInstanceUID', 'N/A')}")
print(f"StudyID: {ds.get('StudyID', 'N/A')}")
print(f"StudyDate: {ds.get('StudyDate', 'N/A')}")
print(f"StudyTime: {ds.get('StudyTime', 'N/A')}")

print("\n=== Series Module ===")
print(f"SeriesInstanceUID: {ds.get('SeriesInstanceUID', 'N/A')}")
print(f"SeriesNumber: {ds.get('SeriesNumber', 'N/A')}")
print(f"SeriesDescription: {ds.get('SeriesDescription', 'N/A')}")

print("\n=== Clinical Trial Module ===")
print(f"ClinicalTrialSponsorName: {ds.get('ClinicalTrialSponsorName', 'N/A')}")
print(f"ClinicalTrialProtocolID: {ds.get('ClinicalTrialProtocolID', 'N/A')}")
print(f"ClinicalTrialProtocolName: {ds.get('ClinicalTrialProtocolName', 'N/A')}")
print(f"ClinicalTrialSubjectID: {ds.get('ClinicalTrialSubjectID', 'N/A')}")

print("\n=== Specimen Module ===")
if 'SpecimenDescriptionSequence' in ds:
    print(f"SpecimenDescriptionSequence: {len(ds.SpecimenDescriptionSequence)} specimens")
    for i, spec in enumerate(ds.SpecimenDescriptionSequence):
        print(f"\n  Specimen {i+1}:")
        print(f"    SpecimenIdentifier: {spec.get('SpecimenIdentifier', 'N/A')}")
        print(f"    SpecimenUID: {spec.get('SpecimenUID', 'N/A')}")
        print(f"    SpecimenShortDescription: {spec.get('SpecimenShortDescription', 'N/A')}")
        
        if 'PrimaryAnatomicStructureSequence' in spec:
            anat = spec.PrimaryAnatomicStructureSequence[0]
            print(f"    Anatomy: {anat.get('CodeValue')} - {anat.get('CodeMeaning')}")
        
        if 'PrimaryAnatomicStructureModifierSequence' in spec:
            mod = spec.PrimaryAnatomicStructureModifierSequence[0]
            print(f"    Modifier: {mod.get('CodeValue')} - {mod.get('CodeMeaning')}")
        
        if 'SpecimenPreparationSequence' in spec:
            print(f"    Preparation steps: {len(spec.SpecimenPreparationSequence)}")

print("\n=== Container Module ===")
print(f"ContainerIdentifier: {ds.get('ContainerIdentifier', 'N/A')}")

print("\n=== Admitting Diagnosis ===")
if 'AdmittingDiagnosesDescription' in ds:
    print(f"AdmittingDiagnosesDescription: {ds.AdmittingDiagnosesDescription}")
    if 'AdmittingDiagnosesCodeSequence' in ds:
        diag = ds.AdmittingDiagnosesCodeSequence[0]
        print(f"  Code: {diag.get('CodeValue')} ({diag.get('CodingSchemeDesignator')}) - {diag.get('CodeMeaning')}")

print("\n=== Optical Path ===")
if 'OpticalPathSequence' in ds:
    print(f"OpticalPathSequence: {len(ds.OpticalPathSequence)} paths")
