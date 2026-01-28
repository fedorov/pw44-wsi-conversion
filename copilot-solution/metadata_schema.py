"""
Domain metadata schema for CCDI WSI conversion.

Dataclasses representing normalized metadata from CCDI CSVs before mapping to DICOM.
"""

from dataclasses import dataclass, field
from typing import Optional, List
from datetime import datetime


@dataclass
class SpecimenInfo:
    """Per-specimen metadata for CCDI samples."""
    
    specimen_id: str  # sample_id from CSV
    specimen_uid: Optional[str] = None  # DICOM UID from registry
    
    # Anatomy
    anatomic_site: Optional[str] = None  # ICD-O-3 topography (e.g., "C72.9 : Central nervous system")
    anatomic_site_snomed_code: Optional[str] = None  # SNOMED CT code (e.g., "21483005")
    anatomic_site_snomed_meaning: Optional[str] = None  # SNOMED meaning
    
    # Tissue classification
    sample_tumor_status: Optional[str] = None  # "Tumor", "Normal"
    tumor_classification: Optional[str] = None  # "Not Reported", "Primary", etc.
    tissue_type_code: Optional[str] = None  # SNOMED code for tissue modifier
    tissue_type_meaning: Optional[str] = None
    
    # Specimen processing
    fixation_method: Optional[str] = None  # "OCT", "FFPE"
    fixation_code: Optional[str] = None  # SNOMED code for fixative
    fixation_meaning: Optional[str] = None
    embedding_code: Optional[str] = None  # SNOMED code for embedding medium
    embedding_meaning: Optional[str] = None
    staining_method: Optional[str] = None  # "H&E"
    staining_codes: List[tuple] = field(default_factory=list)  # [(code, scheme, meaning), ...]
    
    # Quantitative
    percent_tumor: Optional[int] = None
    percent_necrosis: Optional[int] = None


@dataclass
class DiagnosisInfo:
    """Diagnosis metadata from CCDI."""
    
    diagnosis_id: str
    diagnosis_code: Optional[str] = None  # ICD-O-3 morphology (e.g., "9470/3")
    diagnosis_description: Optional[str] = None  # "Medulloblastoma, NOS"
    diagnosis_classification_system: Optional[str] = None  # "ICD-O-3.2"
    diagnosis_basis: Optional[str] = None  # "Clinical", "Histology"
    
    # Anatomic site from diagnosis (priority over sample)
    anatomic_site: Optional[str] = None  # ICD-O-3 topography
    anatomic_site_snomed_code: Optional[str] = None
    anatomic_site_snomed_meaning: Optional[str] = None
    
    age_at_diagnosis: Optional[int] = None  # days
    year_of_diagnosis: Optional[int] = None
    tumor_stage: Optional[str] = None
    tumor_grade: Optional[str] = None
    laterality: Optional[str] = None


@dataclass
class PatientInfo:
    """Patient demographics from CCDI participant."""
    
    participant_id: str
    study_id: str  # phs002790
    
    sex_at_birth: Optional[str] = None  # "Male", "Female"
    race: Optional[str] = None  # "White", "Unknown;White"
    ethnicity: Optional[str] = None
    
    # Race/ethnicity codes for DICOM
    race_codes: List[tuple] = field(default_factory=list)  # [(code, scheme, meaning), ...]


@dataclass
class ClinicalTrialInfo:
    """Clinical trial metadata for CCDI."""
    
    sponsor_name: str = "National Cancer Institute (NCI) Childhood Cancer Data Initiative"
    protocol_id: str = "phs002790"
    protocol_id_issuer: str = "dbGaP"
    protocol_name: str = "CCDI Molecular Characterization Initiative"
    coordinating_center: str = "Nationwide Children's Hospital"
    
    # Per-participant
    subject_id: Optional[str] = None  # participant_id
    
    # Optional protocol identifiers
    other_protocol_ids: List[tuple] = field(default_factory=list)  # [(issuer, id), ...]


@dataclass
class SlideInfo:
    """Slide-level metadata."""
    
    slide_id: str  # Container identifier
    file_name: str
    file_path: Optional[str] = None
    
    # Acquisition
    magnification: Optional[str] = None  # "40X"
    image_modality: Optional[str] = None  # "Slide Microscopy"
    
    # Timestamps
    study_datetime: Optional[datetime] = None  # Extracted from TIFF or registry
    acquisition_datetime: Optional[datetime] = None


@dataclass
class DomainMetadata:
    """Complete normalized metadata for CCDI slide."""
    
    # Core entities
    patient: PatientInfo
    slide: SlideInfo
    specimens: List[SpecimenInfo]  # Multiple samples per slide
    diagnosis: Optional[DiagnosisInfo] = None
    clinical_trial: Optional[ClinicalTrialInfo] = None
    
    # DICOM UIDs (from registry)
    study_instance_uid: Optional[str] = None
    series_instance_uid: Optional[str] = None
    
    def get_primary_specimen(self) -> Optional[SpecimenInfo]:
        """Return first specimen for primary wsidicom metadata."""
        return self.specimens[0] if self.specimens else None
    
    def get_series_description(self) -> str:
        """Generate series description from specimen processing."""
        primary = self.get_primary_specimen()
        if not primary:
            return "WSI"
        
        parts = []
        if primary.fixation_method:
            parts.append(primary.fixation_method)
        if primary.staining_method:
            parts.append(primary.staining_method)
        if primary.sample_tumor_status:
            # Abbreviate
            status_abbr = "T" if primary.sample_tumor_status == "Tumor" else "N"
            parts.append(status_abbr)
        
        return " ".join(parts) if parts else "WSI"
    
    def get_specimen_short_description(self, specimen: SpecimenInfo) -> str:
        """Generate short description per specimen."""
        parts = []
        if specimen.fixation_method:
            parts.append(specimen.fixation_method)
        if specimen.staining_method:
            parts.append(specimen.staining_method)
        if specimen.sample_tumor_status:
            status_abbr = "T" if specimen.sample_tumor_status == "Tumor" else "N"
            parts.append(status_abbr)
        
        return " ".join(parts) if parts else specimen.specimen_id
