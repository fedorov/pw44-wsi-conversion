"""
WSI Metadata Handler Module

Main orchestrator class that coordinates CSV loading, UID mapping,
code translation, and WsiDicomizerMetadata object construction.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
from datetime import datetime

import pydicom
from pydicom.uid import UID
from pydicom.sr.coding import Code

from wsidicom.metadata import (
    Patient,
    PatientSex,
    Study,
    Series,
    Slide,
    Image,
    SlideSample,
    Staining,
    Specimen,
    Fixation,
    Embedding,
)
from wsidicom.conceptcode import (
    SpecimenStainsCode,
    SpecimenFixativesCode,
    SpecimenEmbeddingMediaCode,
)
from wsidicomizer.metadata import WsiDicomizerMetadata

try:
    from .csv_loaders import CSVLoaderBase, SampleData
    from .uid_manager import UIDMappingManager
    from .code_mapper import DicomCodeMapper
    from .collection_config import CollectionConfig
    from .specimen_builder import SpecimenMetadataBuilder
except ImportError:
    from csv_loaders import CSVLoaderBase, SampleData
    from uid_manager import UIDMappingManager
    from code_mapper import DicomCodeMapper
    from collection_config import CollectionConfig
    from specimen_builder import SpecimenMetadataBuilder


@dataclass
class PatientData:
    """
    Resolved patient-level data from CSV sources.

    Attributes
    ----------
    patient_id : str
        Patient/participant identifier
    sex : str, optional
        Sex at birth (e.g., "Male", "Female")
    race : str, optional
        Race
    age_at_diagnosis_days : int, optional
        Age at diagnosis in days
    diagnosis_code : str, optional
        Diagnosis code (e.g., ICD-O-3)
    diagnosis_coding_scheme : str, optional
        Coding scheme for diagnosis (e.g., "ICDO3")
    diagnosis_meaning : str, optional
        Diagnosis meaning/description
    """
    patient_id: str
    sex: Optional[str] = None
    race: Optional[str] = None
    age_at_diagnosis_days: Optional[int] = None
    diagnosis_code: Optional[str] = None
    diagnosis_coding_scheme: Optional[str] = None
    diagnosis_meaning: Optional[str] = None


@dataclass
class SlideData:
    """
    Aggregated slide-level data.

    Attributes
    ----------
    slide_id : str
        Slide/container identifier
    filename : str
        Original filename
    samples : List[SampleData]
        List of samples on the slide
    acquisition_datetime : datetime, optional
        When the image was acquired
    """
    slide_id: str
    filename: str
    samples: List[SampleData]
    acquisition_datetime: Optional[datetime] = None


class WSIMetadataHandler:
    """
    Main orchestrator for metadata loading and DICOM metadata generation.

    This class coordinates CSV loading, UID mapping, code translation,
    and WsiDicomizerMetadata object construction for wsidicomizer-based
    WSI to DICOM conversion.

    Example
    -------
    >>> from claude_solution import (
    ...     WSIMetadataHandler, MCICCDILoader, UIDMappingManager,
    ...     DicomCodeMapper, MCI_CCDI_CONFIG
    ... )
    >>> csv_loader = MCICCDILoader("phs002790_MCI_Release38...")
    >>> csv_loader.load(Path("./csv_dir"))
    >>> uid_manager = UIDMappingManager(
    ...     Path("specimen_map.csv"), Path("study_map.csv")
    ... )
    >>> handler = WSIMetadataHandler(
    ...     csv_loader, uid_manager, DicomCodeMapper(), MCI_CCDI_CONFIG
    ... )
    >>> slide_data = handler.load_metadata_for_file(Path("input.svs"))
    >>> patient_data = handler.get_patient_data(slide_data)
    >>> metadata = handler.build_wsidicomizer_metadata(slide_data, patient_data)
    """

    def __init__(
        self,
        csv_loader: CSVLoaderBase,
        uid_manager: UIDMappingManager,
        code_mapper: DicomCodeMapper,
        collection_config: CollectionConfig
    ):
        """
        Initialize the metadata handler.

        Parameters
        ----------
        csv_loader : CSVLoaderBase
            Format-specific CSV loader instance
        uid_manager : UIDMappingManager
            Manager for persistent UID mappings
        code_mapper : DicomCodeMapper
            Mapper for SNOMED/ICD-O code translations
        collection_config : CollectionConfig
            Collection-specific configuration (sponsor, protocol, etc.)
        """
        self.csv_loader = csv_loader
        self.uid_manager = uid_manager
        self.code_mapper = code_mapper
        self.config = collection_config
        self.specimen_builder = SpecimenMetadataBuilder(code_mapper)

    def load_metadata_for_file(self, input_file: Path) -> SlideData:
        """
        Load all relevant metadata for a WSI file from CSV sources.

        Performs relational lookups across multiple CSV files to gather
        sample, participant, and diagnosis information.

        Parameters
        ----------
        input_file : Path
            Path to the WSI file (e.g., .svs)

        Returns
        -------
        SlideData
            Aggregated slide and sample metadata
        """
        filename = input_file.name
        slide_id = self._extract_slide_id(filename)

        # Get samples associated with this file
        sample_ids = self.csv_loader.get_samples_for_file(filename)

        samples = []
        for sample_id in sample_ids:
            sample_data = self.csv_loader.get_sample_data(sample_id)
            if sample_data:
                # Enrich with imaging-specific data
                imaging_data = self.csv_loader.get_imaging_data(filename, sample_id)
                if imaging_data:
                    sample_data.fixation_method = imaging_data.get('fixation_embedding_method')
                    sample_data.staining_method = imaging_data.get('staining_method')
                    sample_data.magnification = imaging_data.get('magnification')
                    sample_data.percent_tumor = imaging_data.get('percent_tumor')
                    sample_data.percent_necrosis = imaging_data.get('percent_necrosis')
                samples.append(sample_data)

        return SlideData(
            slide_id=slide_id,
            filename=filename,
            samples=samples,
            acquisition_datetime=None  # Could be extracted from file metadata
        )

    def get_patient_data(self, slide_data: SlideData) -> PatientData:
        """
        Resolve patient data from slide samples through relational lookups.

        Parameters
        ----------
        slide_data : SlideData
            Aggregated slide/sample metadata

        Returns
        -------
        PatientData
            Resolved patient-level data

        Raises
        ------
        ValueError
            If no samples found for the slide
        """
        if not slide_data.samples:
            raise ValueError(f"No samples found for slide {slide_data.slide_id}")

        # Get participant ID from first sample
        first_sample = slide_data.samples[0]
        participant_id = first_sample.participant_id

        # Get participant data
        participant_data = self.csv_loader.get_participant_data(participant_id)

        # Get diagnosis data
        diagnosis = self.csv_loader.get_diagnosis_data(
            participant_id, first_sample.sample_id
        )

        # Map diagnosis to code
        diagnosis_code = None
        diagnosis_scheme = None
        diagnosis_meaning = None

        if diagnosis:
            diagnosis_code, diagnosis_scheme, diagnosis_meaning = \
                self.code_mapper.resolve_diagnosis_code(diagnosis)

            # Enrich sample anatomic site from diagnosis if missing
            diagnosis_anatomy = diagnosis.get('anatomic_site')
            if diagnosis_anatomy:
                for sample in slide_data.samples:
                    if not sample.anatomic_site or sample.anatomic_site in ("Not Reported", "Invalid value"):
                        sample.anatomic_site = diagnosis_anatomy

        return PatientData(
            patient_id=participant_id,
            sex=participant_data.get('sex_at_birth') if participant_data else None,
            race=participant_data.get('race') if participant_data else None,
            age_at_diagnosis_days=diagnosis.get('age_at_diagnosis') if diagnosis else None,
            diagnosis_code=diagnosis_code,
            diagnosis_coding_scheme=diagnosis_scheme,
            diagnosis_meaning=diagnosis_meaning
        )

    def build_wsidicomizer_metadata(
        self,
        slide_data: SlideData,
        patient_data: PatientData
    ) -> WsiDicomizerMetadata:
        """
        Build WsiDicomizerMetadata object compatible with wsidicomizer.convert().

        Parameters
        ----------
        slide_data : SlideData
            Aggregated slide/sample metadata
        patient_data : PatientData
            Resolved patient-level metadata

        Returns
        -------
        WsiDicomizerMetadata
            Metadata object for wsidicomizer
        """
        # Build Patient
        patient = Patient(
            identifier=patient_data.patient_id,
            name=patient_data.patient_id,
            sex=self._map_sex(patient_data.sex)
        )

        # Build Study with persistent UID
        study_uid = self.uid_manager.get_or_create_study_uid(patient_data.patient_id)
        study = Study(
            uid=UID(study_uid),
            identifier=patient_data.patient_id,
            accession_number=patient_data.patient_id,
            description="Histopathology"
        )

        # Build Series (description will be added via post-processor if needed)
        series = Series()

        # Build Slide with samples and stainings
        slide_samples = self._build_slide_samples(slide_data, patient_data)
        stainings = self._build_stainings(slide_data.samples)

        slide = Slide(
            identifier=slide_data.slide_id,
            stainings=stainings,
            samples=slide_samples
        )

        # Build Image
        image = Image(acquisition_datetime=slide_data.acquisition_datetime)

        # Generate frame of reference UID
        frame_of_reference_uid = UID(self.uid_manager.generate_new_uid())

        return WsiDicomizerMetadata(
            study=study,
            series=series,
            patient=patient,
            slide=slide,
            image=image,
            frame_of_reference_uid=frame_of_reference_uid
        )

    def build_additional_metadata(
        self,
        patient_data: PatientData,
        slide_data: SlideData
    ) -> pydicom.Dataset:
        """
        Build additional DICOM attributes not handled by WsiDicomizerMetadata.

        This creates a Dataset to be used with metadata_post_processor callback.
        Includes Clinical Trial module attributes, diagnosis codes, etc.

        Parameters
        ----------
        patient_data : PatientData
            Resolved patient-level metadata
        slide_data : SlideData
            Aggregated slide/sample metadata

        Returns
        -------
        pydicom.Dataset
            Additional DICOM attributes
        """
        ds = pydicom.Dataset()

        # Clinical Trial Module
        ds.ClinicalTrialSponsorName = self.config.sponsor_name[:64]
        ds.ClinicalTrialProtocolID = self.config.protocol_id
        ds.ClinicalTrialProtocolName = self.config.protocol_name[:64]
        ds.ClinicalTrialCoordinatingCenterName = self.config.coordinating_center
        ds.ClinicalTrialSubjectID = patient_data.patient_id
        ds.ClinicalTrialSiteID = self.config.site_id
        ds.ClinicalTrialSiteName = self.config.site_name

        # Admitting Diagnosis (if available)
        if patient_data.diagnosis_meaning:
            ds.AdmittingDiagnosesDescription = patient_data.diagnosis_meaning[:64]

            if patient_data.diagnosis_code:
                diag_item = pydicom.Dataset()
                diag_item.CodeValue = patient_data.diagnosis_code
                diag_item.CodingSchemeDesignator = patient_data.diagnosis_coding_scheme or "ICDO3"
                diag_item.CodeMeaning = patient_data.diagnosis_meaning[:64]
                ds.AdmittingDiagnosesCodeSequence = [diag_item]

        # Patient Age (convert from days)
        if patient_data.age_at_diagnosis_days and patient_data.age_at_diagnosis_days > 0:
            age_str = self._format_dicom_age(patient_data.age_at_diagnosis_days)
            if age_str:
                ds.PatientAge = age_str

        # Other Clinical Trial Protocol IDs (DOI)
        if self.config.doi_protocol_id:
            other_protocol = pydicom.Dataset()
            other_protocol.ClinicalTrialProtocolID = self.config.doi_protocol_id
            other_protocol.IssuerOfClinicalTrialProtocolID = "DOI"
            ds.OtherClinicalTrialProtocolIDsSequence = [other_protocol]

        return ds

    def _build_slide_samples(
        self,
        slide_data: SlideData,
        patient_data: PatientData
    ) -> List[SlideSample]:
        """Build SlideSample objects for each sample on the slide."""
        slide_samples = []

        for sample_data in slide_data.samples:
            # Get or create specimen UID
            specimen_uid = self.uid_manager.get_or_create_specimen_uid(sample_data.sample_id)

            # Map anatomy to SNOMED code
            anatomy_codes = []
            if sample_data.anatomic_site and sample_data.anatomic_site not in ("Not Reported", "Invalid value"):
                anatomy_code = self.specimen_builder.build_anatomy_code(sample_data.anatomic_site)
                if anatomy_code:
                    anatomy_codes.append(anatomy_code)

            # Build specimen with preparation steps
            specimen = self._build_specimen(sample_data)

            # Build short description
            short_desc = self.specimen_builder.build_short_description(
                sample_data.fixation_method,
                sample_data.staining_method,
                sample_data.tumor_status
            )

            # Create SlideSample
            slide_sample = SlideSample(
                identifier=sample_data.sample_id,
                anatomical_sites=anatomy_codes if anatomy_codes else None,
                sampled_from=specimen.sample() if specimen else None,
                uid=UID(specimen_uid),
                short_description=short_desc[:64] if short_desc else None
            )

            slide_samples.append(slide_sample)

        return slide_samples

    def _build_specimen(self, sample_data: SampleData) -> Optional[Specimen]:
        """Build a Specimen object with fixation and embedding steps."""
        steps = []

        # Add fixation step if applicable
        fixation_type = self.specimen_builder.get_fixation_type_for_wsidicom(
            sample_data.fixation_method
        )
        if fixation_type:
            try:
                fixation = Fixation(fixative=SpecimenFixativesCode(fixation_type))
                steps.append(fixation)
            except (ValueError, KeyError):
                pass  # Fixation type not in CID 8114

        # Add embedding step if applicable
        embedding_type = self.specimen_builder.get_embedding_type_for_wsidicom(
            sample_data.fixation_method
        )
        if embedding_type:
            try:
                embedding = Embedding(medium=SpecimenEmbeddingMediaCode(embedding_type))
                steps.append(embedding)
            except (ValueError, KeyError):
                pass  # Embedding type not in CID 8115

        if steps:
            return Specimen(
                identifier=sample_data.sample_id,
                steps=steps
            )

        return Specimen(identifier=sample_data.sample_id)

    def _build_stainings(self, samples: List[SampleData]) -> Optional[List[Staining]]:
        """Build Staining objects from sample staining methods."""
        stainings = []
        seen_methods = set()

        for sample in samples:
            if sample.staining_method and sample.staining_method not in seen_methods:
                seen_methods.add(sample.staining_method)

                substances = self.specimen_builder.get_staining_substances_for_wsidicom(
                    sample.staining_method
                )
                if substances:
                    try:
                        stain_codes = [SpecimenStainsCode(s) for s in substances]
                        stainings.append(Staining(substances=stain_codes))
                    except (ValueError, KeyError):
                        # Fall back to string description
                        stainings.append(Staining(substances=sample.staining_method))

        return stainings if stainings else None

    def _build_series_description(self, slide_data: SlideData) -> str:
        """Build series description from slide data."""
        parts = []

        if slide_data.samples:
            first_sample = slide_data.samples[0]
            if first_sample.staining_method:
                parts.append(first_sample.staining_method)
            if first_sample.tumor_status:
                parts.append(first_sample.tumor_status)

        return " ".join(parts) if parts else "Histopathology"

    def _map_sex(self, sex_at_birth: Optional[str]) -> Optional[PatientSex]:
        """Map CSV sex value to DICOM PatientSex enum."""
        if not sex_at_birth:
            return None

        sex_lower = sex_at_birth.lower().strip()

        if sex_lower in ("male", "m"):
            return PatientSex.M
        elif sex_lower in ("female", "f"):
            return PatientSex.F
        elif sex_lower in ("other", "o"):
            return PatientSex.O

        return None

    def _format_dicom_age(self, age_in_days: int) -> Optional[str]:
        """
        Format age in days to DICOM age string (nnnD, nnnM, or nnnY).

        Parameters
        ----------
        age_in_days : int
            Age in days

        Returns
        -------
        str or None
            DICOM-formatted age string
        """
        if age_in_days < 0:
            return None

        # Use days for infants
        if age_in_days < 999:
            return f"{age_in_days:03d}D"

        # Use months for young children
        age_in_months = age_in_days // 30
        if age_in_months < 999:
            return f"{age_in_months:03d}M"

        # Use years for older
        age_in_years = age_in_days // 365
        if age_in_years < 100:
            return f"0{age_in_years:02d}Y"
        elif age_in_years < 1000:
            return f"{age_in_years:03d}Y"

        return None

    def _extract_slide_id(self, filename: str) -> str:
        """
        Extract slide ID from filename.

        Parameters
        ----------
        filename : str
            Input filename (e.g., "0DWWQ6.svs")

        Returns
        -------
        str
            Slide ID (e.g., "0DWWQ6")
        """
        # Remove common extensions
        base = filename
        for ext in ['.svs', '.dcm', '.tiff', '.tif', '.ndpi', '.scn', '.mrxs']:
            if base.lower().endswith(ext):
                base = base[:-len(ext)]
                break

        return base
