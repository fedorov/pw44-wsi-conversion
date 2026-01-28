"""
Metadata builder for wsidicomizer.

Converts DomainMetadata into WsiDicomizerMetadata and supplemental pydicom Dataset
for CCDI WSI conversion.
"""

from typing import Tuple, Optional
from datetime import datetime
import pydicom
from pydicom.dataset import Dataset
from pydicom.sequence import Sequence as DicomSequence
from wsidicomizer.metadata import WsiDicomizerMetadata
from wsidicom.metadata import Patient, PatientSex, Study, Equipment, Series

try:
    from .metadata_schema import DomainMetadata, SpecimenInfo
    from .uid_registry import UIDRegistry
except ImportError:
    from metadata_schema import DomainMetadata, SpecimenInfo
    from uid_registry import UIDRegistry


class MetadataBuilder:
    """Build wsidicom metadata and pydicom supplements from domain metadata."""
    
    def __init__(self, uid_registry: UIDRegistry, dataset: str = "CCDI"):
        """
        Initialize builder.
        
        Args:
            uid_registry: UID registry for persistent UIDs
            dataset: Dataset identifier for UID namespacing
        """
        self.uid_registry = uid_registry
        self.dataset = dataset
    
    def build(
        self,
        domain_metadata: DomainMetadata,
        study_datetime: Optional[datetime] = None
    ) -> Tuple[WsiDicomizerMetadata, Dataset]:
        """
        Build wsidicom metadata and pydicom supplement.
        
        Args:
            domain_metadata: Normalized metadata from CCDI loader
            study_datetime: Optional study datetime (from TIFF or fallback)
            
        Returns:
            Tuple of (WsiDicomizerMetadata, supplemental Dataset)
        """
        # Get or create UIDs
        patient_id = domain_metadata.patient.participant_id
        study_uid = self.uid_registry.get_or_create_study_uid(patient_id, self.dataset)
        
        # Get or store study datetime
        if not study_datetime:
            study_datetime = datetime.now()
        study_datetime = self.uid_registry.get_or_create_study_datetime(
            patient_id, study_datetime, self.dataset
        )
        
        # Generate SpecimenUIDs for all specimens
        for specimen in domain_metadata.specimens:
            specimen.specimen_uid = self.uid_registry.get_or_create_specimen_uid(
                specimen.specimen_id, self.dataset
            )
        
        # Store UIDs in domain metadata
        domain_metadata.study_instance_uid = study_uid
        
        # Build wsidicom metadata (primary specimen only)
        wsi_metadata = self._build_wsidicom_metadata(domain_metadata, study_datetime)
        
        # Build pydicom supplement (multi-specimen, clinical trial, prep sequences)
        supplement = self._build_pydicom_supplement(domain_metadata, study_datetime)
        
        return wsi_metadata, supplement
    
    def _build_wsidicom_metadata(
        self,
        domain_metadata: DomainMetadata,
        study_datetime: datetime
    ) -> WsiDicomizerMetadata:
        """Build WsiDicomizerMetadata from domain metadata."""
        patient_info = domain_metadata.patient
        slide_info = domain_metadata.slide
        primary_specimen = domain_metadata.get_primary_specimen()
        
        # Patient
        sex_map = {"Male": PatientSex.M, "Female": PatientSex.F}
        patient_sex = sex_map.get(patient_info.sex_at_birth, PatientSex.O)
        
        patient = Patient(
            name=patient_info.participant_id,
            identifier=patient_info.participant_id,
            sex=patient_sex
        )
        
        # Study
        study = Study(
            identifier=patient_info.participant_id,
            uid=domain_metadata.study_instance_uid,
            date=study_datetime.date() if study_datetime else None,
            time=study_datetime.time() if study_datetime else None,
            accession_number=patient_info.participant_id,
            description="Histopathology"
        )
        
        # Series
        series_description = domain_metadata.get_series_description()
        series = Series(
            number=1,
            description=series_description
        )
        
        # Equipment (minimal)
        equipment = Equipment(
            manufacturer="Unknown",
            model_name="Unknown"
        )
        
        return WsiDicomizerMetadata(
            patient=patient,
            study=study,
            series=series,
            equipment=equipment
        )
    
    def _build_pydicom_supplement(
        self,
        domain_metadata: DomainMetadata,
        study_datetime: datetime
    ) -> Dataset:
        """Build supplemental pydicom Dataset with fields not in wsidicom."""
        ds = Dataset()
        
        # Patient module additions
        self._add_patient_fields(ds, domain_metadata)
        
        # Clinical trial module
        self._add_clinical_trial_fields(ds, domain_metadata)
        
        # Specimen module (multi-specimen support)
        self._add_specimen_fields(ds, domain_metadata)
        
        # Container module
        self._add_container_fields(ds, domain_metadata)
        
        # Optical path module
        self._add_optical_path_fields(ds)
        
        # Acquisition context (minimal)
        ds.AcquisitionContextSequence = DicomSequence([])
        
        return ds
    
    def _add_patient_fields(self, ds: Dataset, domain_metadata: DomainMetadata):
        """Add patient demographics and diagnosis."""
        patient = domain_metadata.patient
        diagnosis = domain_metadata.diagnosis
        
        # PatientAge (DICOM format: nnnY, nnnM, nnnD)
        if diagnosis and diagnosis.age_at_diagnosis:
            age_days = diagnosis.age_at_diagnosis
            if age_days >= 365:
                age_years = age_days // 365
                ds.PatientAge = f"{age_years:03d}Y"
            elif age_days >= 30:
                age_months = age_days // 30
                ds.PatientAge = f"{age_months:03d}M"
            else:
                ds.PatientAge = f"{age_days:03d}D"
        
        # EthnicGroup (short string, 16 char max)
        if patient.race_codes:
            # Use first race as ethnic group string
            dicom_race = patient.race.split(';')[0] if ';' in patient.race else patient.race
            if dicom_race in ["White", "Unknown;White"]:
                ds.EthnicGroup = "White"
            elif "Asian" in dicom_race:
                ds.EthnicGroup = "Asian"
            elif "Black" in dicom_race or "African" in dicom_race:
                ds.EthnicGroup = "Black"
            elif "Hispanic" in dicom_race:
                ds.EthnicGroup = "Hispanic"
        
        # EthnicGroupCodeSequence
        if patient.race_codes:
            ethnic_seq = DicomSequence()
            for code, scheme, meaning in patient.race_codes:
                code_item = Dataset()
                code_item.CodeValue = code
                code_item.CodingSchemeDesignator = scheme
                code_item.CodeMeaning = meaning
                ethnic_seq.append(code_item)
            ds.EthnicGroupCodeSequence = ethnic_seq
        
        # Admitting diagnosis
        if diagnosis and diagnosis.diagnosis_description:
            ds.AdmittingDiagnosesDescription = diagnosis.diagnosis_description
            
            if diagnosis.diagnosis_code:
                diag_seq = DicomSequence()
                diag_item = Dataset()
                diag_item.CodeValue = diagnosis.diagnosis_code
                diag_item.CodingSchemeDesignator = "ICDO3"
                diag_item.CodeMeaning = diagnosis.diagnosis_description
                diag_seq.append(diag_item)
                ds.AdmittingDiagnosesCodeSequence = diag_seq
    
    def _add_clinical_trial_fields(self, ds: Dataset, domain_metadata: DomainMetadata):
        """Add clinical trial identification fields."""
        trial = domain_metadata.clinical_trial
        if not trial:
            return
        
        ds.ClinicalTrialSponsorName = trial.sponsor_name
        ds.ClinicalTrialProtocolID = trial.protocol_id
        ds.IssuerOfClinicalTrialProtocolID = trial.protocol_id_issuer
        ds.ClinicalTrialProtocolName = trial.protocol_name
        ds.ClinicalTrialCoordinatingCenterName = trial.coordinating_center
        
        # Per DICOM standard, site info is Type 2 (required but may be empty)
        ds.ClinicalTrialSiteID = ""
        ds.ClinicalTrialSiteName = ""
        
        if trial.subject_id:
            ds.ClinicalTrialSubjectID = trial.subject_id
        
        # Other protocol IDs (e.g., Zenodo DOI)
        if trial.other_protocol_ids:
            other_seq = DicomSequence()
            for issuer, protocol_id in trial.other_protocol_ids:
                item = Dataset()
                item.IssuerOfClinicalTrialProtocolID = issuer
                item.ClinicalTrialProtocolID = protocol_id
                other_seq.append(item)
            ds.OtherClinicalTrialProtocolIDsSequence = other_seq
        
        # Private CTP tags for TCIA compatibility
        ds.add_new((0x0013, 0x0010), 'LO', 'CTP')
        ds.add_new((0x0013, 0x1010), 'LO', trial.protocol_id)
    
    def _add_specimen_fields(self, ds: Dataset, domain_metadata: DomainMetadata):
        """Add specimen description sequence (multi-specimen support)."""
        specimen_seq = DicomSequence()
        
        for specimen in domain_metadata.specimens:
            spec_item = Dataset()
            
            # Specimen identifier and UID
            spec_item.SpecimenIdentifier = specimen.specimen_id
            spec_item.SpecimenUID = specimen.specimen_uid
            
            # Short description
            spec_item.SpecimenShortDescription = domain_metadata.get_specimen_short_description(specimen)
            
            # Primary anatomic structure
            if specimen.anatomic_site_snomed_code:
                anat_seq = DicomSequence()
                anat_item = Dataset()
                anat_item.CodeValue = specimen.anatomic_site_snomed_code
                anat_item.CodingSchemeDesignator = "SCT"
                anat_item.CodeMeaning = specimen.anatomic_site_snomed_meaning or specimen.anatomic_site
                anat_seq.append(anat_item)
                spec_item.PrimaryAnatomicStructureSequence = anat_seq
            
            # Primary anatomic structure modifier (tissue type: Tumor/Normal)
            if specimen.tissue_type_code:
                mod_seq = DicomSequence()
                mod_item = Dataset()
                mod_item.CodeValue = specimen.tissue_type_code
                mod_item.CodingSchemeDesignator = "SCT"
                mod_item.CodeMeaning = specimen.tissue_type_meaning
                mod_seq.append(mod_item)
                spec_item.PrimaryAnatomicStructureModifierSequence = mod_seq
            
            # Specimen preparation sequence
            prep_seq = self._build_specimen_prep_sequence(specimen)
            if prep_seq:
                spec_item.SpecimenPreparationSequence = prep_seq
            
            specimen_seq.append(spec_item)
        
        ds.SpecimenDescriptionSequence = specimen_seq
    
    def _build_specimen_prep_sequence(self, specimen: SpecimenInfo) -> Optional[DicomSequence]:
        """Build SpecimenPreparationSequence for fixation, embedding, staining."""
        prep_seq = DicomSequence()
        
        # Fixation step
        if specimen.fixation_code:
            fix_item = Dataset()
            fix_item.SpecimenPreparationStepContentItemSequence = self._build_prep_step(
                "9265001", "SCT", "Specimen processing",
                specimen.fixation_code, "SCT", specimen.fixation_meaning
            )
            prep_seq.append(fix_item)
        
        # Embedding step (FFPE only)
        if specimen.embedding_code:
            emb_item = Dataset()
            emb_item.SpecimenPreparationStepContentItemSequence = self._build_prep_step(
                "9265001", "SCT", "Specimen processing",
                specimen.embedding_code, "SCT", specimen.embedding_meaning
            )
            prep_seq.append(emb_item)
        
        # Staining step
        if specimen.staining_codes:
            for stain_code, stain_scheme, stain_meaning in specimen.staining_codes:
                stain_item = Dataset()
                stain_item.SpecimenPreparationStepContentItemSequence = self._build_prep_step(
                    "127790008", "SCT", "Staining",
                    stain_code, stain_scheme, stain_meaning
                )
                prep_seq.append(stain_item)
        
        return prep_seq if prep_seq else None
    
    def _build_prep_step(
        self,
        type_code: str,
        type_scheme: str,
        type_meaning: str,
        substance_code: str,
        substance_scheme: str,
        substance_meaning: str
    ) -> DicomSequence:
        """Build a single specimen preparation step content item sequence."""
        content_seq = DicomSequence()
        
        # Processing type
        type_item = Dataset()
        type_item.ValueType = "CODE"
        type_item.ConceptNameCodeSequence = self._build_code_item("111701", "DCM", "Processing type")
        type_item.ConceptCodeSequence = self._build_code_item(type_code, type_scheme, type_meaning)
        content_seq.append(type_item)
        
        # Substance (fixative, embedding medium, or stain)
        substance_item = Dataset()
        substance_item.ValueType = "CODE"
        if "Staining" in type_meaning:
            substance_item.ConceptNameCodeSequence = self._build_code_item("424361007", "SCT", "Using substance")
        else:
            substance_item.ConceptNameCodeSequence = self._build_code_item("430863003", "SCT", "Tissue Fixative")
        substance_item.ConceptCodeSequence = self._build_code_item(substance_code, substance_scheme, substance_meaning)
        content_seq.append(substance_item)
        
        return content_seq
    
    def _build_code_item(self, code: str, scheme: str, meaning: str) -> DicomSequence:
        """Build a single-item code sequence."""
        seq = DicomSequence()
        item = Dataset()
        item.CodeValue = code
        item.CodingSchemeDesignator = scheme
        item.CodeMeaning = meaning
        seq.append(item)
        return seq
    
    def _add_container_fields(self, ds: Dataset, domain_metadata: DomainMetadata):
        """Add container identification."""
        slide = domain_metadata.slide
        
        ds.ContainerIdentifier = slide.slide_id
        
        # Container type: microscope slide
        container_seq = DicomSequence()
        container_item = Dataset()
        container_item.CodeValue = "433466003"
        container_item.CodingSchemeDesignator = "SCT"
        container_item.CodeMeaning = "Microscope slide"
        container_seq.append(container_item)
        ds.ContainerTypeCodeSequence = container_seq
    
    def _add_optical_path_fields(self, ds: Dataset):
        """Add optical path sequence (brightfield microscopy)."""
        optical_seq = DicomSequence()
        optical_item = Dataset()
        
        optical_item.OpticalPathIdentifier = "1"
        
        # Illumination color: full spectrum
        illum_color_seq = DicomSequence()
        color_item = Dataset()
        color_item.CodeValue = "414298005"
        color_item.CodingSchemeDesignator = "SCT"
        color_item.CodeMeaning = "Full Spectrum"
        illum_color_seq.append(color_item)
        optical_item.IlluminationColorCodeSequence = illum_color_seq
        
        # Illumination type: brightfield
        illum_type_seq = DicomSequence()
        type_item = Dataset()
        type_item.CodeValue = "111744"
        type_item.CodingSchemeDesignator = "DCM"
        type_item.CodeMeaning = "Brightfield illumination"
        illum_type_seq.append(type_item)
        optical_item.IlluminationTypeCodeSequence = illum_type_seq
        
        optical_seq.append(optical_item)
        ds.OpticalPathSequence = optical_seq


if __name__ == "__main__":
    # Test with sample5 data
    import sys
    sys.path.insert(0, '/Users/af61/Desktop/PW44/wsi-conversion/copilot-solution')
    
    from ccdi_loader import CCDIMetadataLoader
    from uid_registry import UIDRegistry
    from tiff_datetime import extract_scan_datetime
    from pathlib import Path
    
    # Load domain metadata
    loader = CCDIMetadataLoader(
        pathology_csv="/Users/af61/Desktop/PW44/wsi-conversion/idc-wsi-conversion/phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6_pathology_file.csv",
        sample_csv="/Users/af61/Desktop/PW44/wsi-conversion/idc-wsi-conversion/phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6_sample.csv",
        participant_csv="/Users/af61/Desktop/PW44/wsi-conversion/idc-wsi-conversion/phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6_participant.csv",
        diagnosis_csv="/Users/af61/Desktop/PW44/wsi-conversion/idc-wsi-conversion/phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6_diagnosis.csv",
        codes_dir="/Users/af61/Desktop/PW44/wsi-conversion/copilot-solution/codes"
    )
    
    domain_metadata = loader.load_slide("0DWWQ6.svs")
    
    # Extract study datetime
    tiff_path = Path("/Users/af61/Desktop/PW44/wsi-conversion/test_data/sample5/src/0DWWQ6.svs")
    study_dt = extract_scan_datetime(tiff_path)
    print(f"Extracted scan datetime: {study_dt}")
    
    # Build metadata
    registry = UIDRegistry("test_uid_registry.db")
    builder = MetadataBuilder(registry)
    
    wsi_metadata, supplement = builder.build(domain_metadata, study_dt)
    
    print(f"\nWsiDicomizerMetadata:")
    print(f"  Patient: {wsi_metadata.patient.name} ({wsi_metadata.patient.sex.value})")
    print(f"  Study UID: {wsi_metadata.study.uid}")
    print(f"  Study Date/Time: {wsi_metadata.study.date} {wsi_metadata.study.time}")
    print(f"  Series: {wsi_metadata.series.number} - {wsi_metadata.series.description}")
    
    print(f"\nPydicom Supplement:")
    print(f"  PatientAge: {supplement.get('PatientAge', 'N/A')}")
    print(f"  EthnicGroup: {supplement.get('EthnicGroup', 'N/A')}")
    print(f"  ClinicalTrialProtocolID: {supplement.get('ClinicalTrialProtocolID')}")
    print(f"  ContainerIdentifier: {supplement.get('ContainerIdentifier')}")
    print(f"  Specimens: {len(supplement.SpecimenDescriptionSequence)}")
    
    for i, spec in enumerate(supplement.SpecimenDescriptionSequence):
        print(f"    Specimen {i+1}: {spec.SpecimenIdentifier}")
        print(f"      Short desc: {spec.SpecimenShortDescription}")
        print(f"      Prep steps: {len(spec.SpecimenPreparationSequence) if hasattr(spec, 'SpecimenPreparationSequence') else 0}")
    
    # Cleanup
    Path("test_uid_registry.db").unlink()
    print("\nMetadata builder test passed!")
