"""
CCDI metadata loader.

Joins CCDI CSV tables (pathology_file, sample, participant, diagnosis) and maps
codes via lookup tables to populate domain metadata for wsidicomizer conversion.
"""

import csv
from pathlib import Path
from typing import List, Optional, Dict, Tuple

try:
    from .metadata_schema import (
        DomainMetadata, PatientInfo, SlideInfo, SpecimenInfo,
        DiagnosisInfo, ClinicalTrialInfo
    )
except ImportError:
    from metadata_schema import (
        DomainMetadata, PatientInfo, SlideInfo, SpecimenInfo,
        DiagnosisInfo, ClinicalTrialInfo
    )


class CCDIMetadataLoader:
    """Load and join CCDI CSV metadata for slides."""
    
    def __init__(
        self,
        pathology_csv: str,
        sample_csv: str,
        participant_csv: str,
        diagnosis_csv: str,
        codes_dir: str = "codes"
    ):
        """
        Initialize CCDI loader with CSV paths.
        
        Args:
            pathology_csv: Path to pathology_file CSV
            sample_csv: Path to sample CSV
            participant_csv: Path to participant CSV
            diagnosis_csv: Path to diagnosis CSV
            codes_dir: Directory containing code mapping CSVs
        """
        self.pathology_csv = Path(pathology_csv)
        self.sample_csv = Path(sample_csv)
        self.participant_csv = Path(participant_csv)
        self.diagnosis_csv = Path(diagnosis_csv)
        self.codes_dir = Path(codes_dir)
        
        # Load code tables
        self._anatomy_map = self._load_anatomy_map()
        self._race_map = self._load_race_map()
        self._fixation_map = self._load_fixation_map()
        self._staining_map = self._load_staining_map()
        self._tissue_type_map = self._load_tissue_type_map()
    
    def _load_anatomy_map(self) -> Dict[str, Tuple[str, str, str]]:
        """Load ICD-O-3 topography → SNOMED anatomy mapping."""
        anatomy_map = {}
        csv_path = self.codes_dir / "ccdi_anatomy_map.csv"
        if not csv_path.exists():
            return anatomy_map
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Normalize ICD-O-3 key (e.g., "C72.9 : Central nervous system")
                icdo3 = row['icdo3_topography'].strip()
                anatomy_map[icdo3] = (
                    row['snomed_code'],
                    row['snomed_scheme'],
                    row['snomed_meaning']
                )
        return anatomy_map
    
    def _load_race_map(self) -> Dict[str, Dict]:
        """Load race → SNOMED/NCIt codes mapping."""
        race_map = {}
        csv_path = self.codes_dir / "ccdi_race_map.csv"
        if not csv_path.exists():
            return race_map
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                race_key = row['race'].strip()
                codes = []
                
                for i in range(1, 4):  # Up to 3 codes
                    code = row.get(f'code_{i}', '').strip()
                    scheme = row.get(f'scheme_{i}', '').strip()
                    meaning = row.get(f'meaning_{i}', '').strip()
                    if code and scheme and meaning:
                        codes.append((code, scheme, meaning))
                
                race_map[race_key] = {
                    'dicom_ethnic_group': row['dicom_ethnic_group'].strip(),
                    'codes': codes
                }
        return race_map
    
    def _load_fixation_map(self) -> Dict[str, Dict]:
        """Load fixation/embedding method → SNOMED codes."""
        fixation_map = {}
        csv_path = self.codes_dir / "ccdi_fixation_embedding.csv"
        if not csv_path.exists():
            return fixation_map
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                method = row['fixation_method'].strip()
                fixation_map[method] = {
                    'fixation_code': row['fixation_code'].strip(),
                    'fixation_scheme': row['fixation_scheme'].strip(),
                    'fixation_meaning': row['fixation_meaning'].strip(),
                    'embedding_code': row.get('embedding_code', '').strip(),
                    'embedding_scheme': row.get('embedding_scheme', '').strip(),
                    'embedding_meaning': row.get('embedding_meaning', '').strip()
                }
        return fixation_map
    
    def _load_staining_map(self) -> Dict[str, List[Tuple]]:
        """Load staining method → SNOMED stain codes."""
        staining_map = {}
        csv_path = self.codes_dir / "ccdi_staining.csv"
        if not csv_path.exists():
            return staining_map
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                method = row['staining_method'].strip()
                stains = []
                
                for i in range(1, 3):  # Up to 2 stain codes (e.g., hematoxylin + eosin)
                    code = row.get(f'stain_code_{i}', '').strip()
                    scheme = row.get(f'stain_scheme_{i}', '').strip()
                    meaning = row.get(f'stain_meaning_{i}', '').strip()
                    if code and scheme and meaning:
                        stains.append((code, scheme, meaning))
                
                staining_map[method] = stains
        return staining_map
    
    def _load_tissue_type_map(self) -> Dict[str, Tuple]:
        """Load sample_tumor_status → SNOMED tissue type modifier."""
        tissue_map = {}
        csv_path = self.codes_dir / "ccdi_tissue_type.csv"
        if not csv_path.exists():
            return tissue_map
        
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                status = row['sample_tumor_status'].strip()
                tissue_map[status] = (
                    row['snomed_code'],
                    row['snomed_scheme'],
                    row['snomed_meaning']
                )
        return tissue_map
    
    def load_slide(self, filename: str) -> DomainMetadata:
        """
        Load metadata for a slide by filename.
        
        Performs CSV joins: pathology_file → sample → participant, diagnosis
        
        Args:
            filename: Slide filename (e.g., "0DWWQ6.svs")
            
        Returns:
            DomainMetadata with all specimens, patient, diagnosis
        """
        # Step 1: Find pathology_file rows for this filename
        pathology_rows = self._find_pathology_rows(filename)
        if not pathology_rows:
            raise ValueError(f"No pathology_file entries found for {filename}")
        
        # Extract sample_ids from pathology rows (multiple samples per slide)
        sample_ids = [row['sample.sample_id'] for row in pathology_rows]
        
        # Step 2: Join with sample CSV to get participant_id and specimen details
        sample_rows = []
        participant_id = None
        for sample_id in sample_ids:
            sample_row = self._find_sample_row(sample_id)
            if sample_row:
                sample_rows.append(sample_row)
                if not participant_id:
                    participant_id = sample_row['participant.participant_id']
        
        if not participant_id:
            raise ValueError(f"Could not find participant_id for {filename}")
        
        # Step 3: Load participant demographics
        participant_row = self._find_participant_row(participant_id)
        if not participant_row:
            raise ValueError(f"Participant {participant_id} not found")
        
        # Step 4: Load diagnosis (optional, may be missing)
        diagnosis_row = self._find_diagnosis_row(participant_id)
        
        # Build domain entities
        patient = self._build_patient_info(participant_row)
        slide = self._build_slide_info(pathology_rows[0], filename)
        specimens = self._build_specimen_info_list(pathology_rows, sample_rows, diagnosis_row)
        diagnosis = self._build_diagnosis_info(diagnosis_row) if diagnosis_row else None
        clinical_trial = self._build_clinical_trial_info(participant_id)
        
        return DomainMetadata(
            patient=patient,
            slide=slide,
            specimens=specimens,
            diagnosis=diagnosis,
            clinical_trial=clinical_trial
        )
    
    def _find_pathology_rows(self, filename: str) -> List[Dict]:
        """Find all pathology_file rows for filename (multiple samples per slide)."""
        rows = []
        with open(self.pathology_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['file_name'] == filename:
                    rows.append(row)
        return rows
    
    def _find_sample_row(self, sample_id: str) -> Optional[Dict]:
        """Find sample row by sample_id."""
        with open(self.sample_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['sample_id'] == sample_id:
                    return row
        return None
    
    def _find_participant_row(self, participant_id: str) -> Optional[Dict]:
        """Find participant row by participant_id."""
        with open(self.participant_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['participant_id'] == participant_id:
                    return row
        return None
    
    def _find_diagnosis_row(self, participant_id: str) -> Optional[Dict]:
        """Find diagnosis row by participant_id (exclude CNS_category, CNS5 variants)."""
        with open(self.diagnosis_csv, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('participant.participant_id') == participant_id:
                    diagnosis_id = row.get('diagnosis_id', '')
                    # Skip CNS variant diagnoses per mcitodcm.sh filtering
                    if '_CNS_category' in diagnosis_id or '_CNS5_diagnosis' in diagnosis_id:
                        continue
                    return row
        return None
    
    def _build_patient_info(self, participant_row: Dict) -> PatientInfo:
        """Build PatientInfo from participant CSV row."""
        race = participant_row['race']
        race_mapping = self._race_map.get(race, {'dicom_ethnic_group': '', 'codes': []})
        
        return PatientInfo(
            participant_id=participant_row['participant_id'],
            study_id=participant_row['study.study_id'],
            sex_at_birth=participant_row.get('sex_at_birth'),
            race=race,
            race_codes=race_mapping['codes']
        )
    
    def _build_slide_info(self, pathology_row: Dict, filename: str) -> SlideInfo:
        """Build SlideInfo from pathology_file CSV row."""
        # Extract slide_id from pathology_file_id or filename
        # For 0DWWQ6.svs, slide_id is 0DWWQ6
        slide_id = filename.replace('.svs', '').split('_')[0]
        
        return SlideInfo(
            slide_id=slide_id,
            file_name=filename,
            magnification=pathology_row.get('magnification'),
            image_modality=pathology_row.get('image_modality')
        )
    
    def _build_specimen_info_list(
        self,
        pathology_rows: List[Dict],
        sample_rows: List[Dict],
        diagnosis_row: Optional[Dict]
    ) -> List[SpecimenInfo]:
        """Build SpecimenInfo for each sample (multiple per slide)."""
        specimens = []
        
        for pathology_row, sample_row in zip(pathology_rows, sample_rows):
            specimen_id = sample_row['sample_id']
            
            # Anatomy: prefer diagnosis anatomic_site, fallback to sample
            anatomic_site = None
            anatomic_code = None
            anatomic_scheme = None
            anatomic_meaning = None
            
            if diagnosis_row and diagnosis_row.get('anatomic_site'):
                anatomic_site = diagnosis_row['anatomic_site']
                if anatomic_site in self._anatomy_map:
                    anatomic_code, anatomic_scheme, anatomic_meaning = self._anatomy_map[anatomic_site]
            
            if not anatomic_site and sample_row.get('anatomic_site'):
                anatomic_site = sample_row['anatomic_site']
                if anatomic_site in self._anatomy_map:
                    anatomic_code, anatomic_scheme, anatomic_meaning = self._anatomy_map[anatomic_site]
            
            # Tissue type modifier
            tumor_status = sample_row.get('sample_tumor_status', '')
            tissue_code, tissue_scheme, tissue_meaning = None, None, None
            if tumor_status in self._tissue_type_map:
                tissue_code, tissue_scheme, tissue_meaning = self._tissue_type_map[tumor_status]
            
            # Fixation/embedding
            fixation_method = pathology_row.get('fixation_embedding_method', '')
            fixation_info = self._fixation_map.get(fixation_method, {})
            
            # Staining
            staining_method = pathology_row.get('staining_method', '')
            staining_codes = self._staining_map.get(staining_method, [])
            
            # Percentages
            percent_tumor = pathology_row.get('percent_tumor')
            percent_tumor = int(percent_tumor) if percent_tumor and percent_tumor != '' else None
            percent_necrosis = pathology_row.get('percent_necrosis')
            percent_necrosis = int(percent_necrosis) if percent_necrosis and percent_necrosis != '' else None
            
            specimen = SpecimenInfo(
                specimen_id=specimen_id,
                anatomic_site=anatomic_site,
                anatomic_site_snomed_code=anatomic_code,
                anatomic_site_snomed_meaning=anatomic_meaning,
                sample_tumor_status=tumor_status,
                tumor_classification=sample_row.get('tumor_classification'),
                tissue_type_code=tissue_code,
                tissue_type_meaning=tissue_meaning,
                fixation_method=fixation_method,
                fixation_code=fixation_info.get('fixation_code'),
                fixation_meaning=fixation_info.get('fixation_meaning'),
                embedding_code=fixation_info.get('embedding_code'),
                embedding_meaning=fixation_info.get('embedding_meaning'),
                staining_method=staining_method,
                staining_codes=staining_codes,
                percent_tumor=percent_tumor,
                percent_necrosis=percent_necrosis
            )
            specimens.append(specimen)
        
        return specimens
    
    def _build_diagnosis_info(self, diagnosis_row: Dict) -> DiagnosisInfo:
        """Build DiagnosisInfo from diagnosis CSV row."""
        diagnosis_str = diagnosis_row.get('diagnosis', '')
        
        # Extract ICD-O-3 morphology code (e.g., "9470/3 : Medulloblastoma, NOS")
        diagnosis_code = None
        diagnosis_description = None
        if ' : ' in diagnosis_str:
            parts = diagnosis_str.split(' : ', 1)
            diagnosis_code = parts[0].strip()
            diagnosis_description = parts[1].strip()
        else:
            diagnosis_description = diagnosis_str
        
        # Anatomy from diagnosis
        anatomic_site = diagnosis_row.get('anatomic_site', '')
        anatomic_code, anatomic_scheme, anatomic_meaning = None, None, None
        if anatomic_site in self._anatomy_map:
            anatomic_code, anatomic_scheme, anatomic_meaning = self._anatomy_map[anatomic_site]
        
        # Age at diagnosis (days)
        age_at_diagnosis = diagnosis_row.get('age_at_diagnosis')
        age_at_diagnosis = int(age_at_diagnosis) if age_at_diagnosis and age_at_diagnosis not in ['', '-999'] else None
        
        return DiagnosisInfo(
            diagnosis_id=diagnosis_row.get('diagnosis_id', ''),
            diagnosis_code=diagnosis_code,
            diagnosis_description=diagnosis_description,
            diagnosis_classification_system=diagnosis_row.get('diagnosis_classification_system'),
            diagnosis_basis=diagnosis_row.get('diagnosis_basis'),
            anatomic_site=anatomic_site,
            anatomic_site_snomed_code=anatomic_code,
            anatomic_site_snomed_meaning=anatomic_meaning,
            age_at_diagnosis=age_at_diagnosis,
            year_of_diagnosis=diagnosis_row.get('year_of_diagnosis'),
            laterality=diagnosis_row.get('laterality')
        )
    
    def _build_clinical_trial_info(self, participant_id: str) -> ClinicalTrialInfo:
        """Build ClinicalTrialInfo with CCDI constants."""
        trial = ClinicalTrialInfo(
            subject_id=participant_id
        )
        # Add Zenodo DOI as other protocol ID
        trial.other_protocol_ids = [("DOI", "10.5281/zenodo.11099087")]
        return trial


if __name__ == "__main__":
    # Test with sample5
    loader = CCDIMetadataLoader(
        pathology_csv="/Users/af61/Desktop/PW44/wsi-conversion/idc-wsi-conversion/phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6_pathology_file.csv",
        sample_csv="/Users/af61/Desktop/PW44/wsi-conversion/idc-wsi-conversion/phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6_sample.csv",
        participant_csv="/Users/af61/Desktop/PW44/wsi-conversion/idc-wsi-conversion/phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6_participant.csv",
        diagnosis_csv="/Users/af61/Desktop/PW44/wsi-conversion/idc-wsi-conversion/phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6_diagnosis.csv",
        codes_dir="/Users/af61/Desktop/PW44/wsi-conversion/copilot-solution/codes"
    )
    
    metadata = loader.load_slide("0DWWQ6.svs")
    
    print(f"Patient: {metadata.patient.participant_id} ({metadata.patient.sex_at_birth})")
    print(f"Race: {metadata.patient.race} → codes: {metadata.patient.race_codes}")
    print(f"Study: {metadata.patient.study_id}")
    print(f"\nSlide: {metadata.slide.slide_id} ({metadata.slide.file_name})")
    print(f"Magnification: {metadata.slide.magnification}")
    print(f"\nSpecimens ({len(metadata.specimens)}):")
    for spec in metadata.specimens:
        print(f"  - {spec.specimen_id}: {spec.anatomic_site} [{spec.anatomic_site_snomed_code}]")
        print(f"    Tumor status: {spec.sample_tumor_status} → {spec.tissue_type_code}")
        print(f"    Fixation: {spec.fixation_method} → {spec.fixation_code}")
        print(f"    Staining: {spec.staining_method} → {spec.staining_codes}")
    
    if metadata.diagnosis:
        print(f"\nDiagnosis: {metadata.diagnosis.diagnosis_description} ({metadata.diagnosis.diagnosis_code})")
        print(f"  Site: {metadata.diagnosis.anatomic_site} → {metadata.diagnosis.anatomic_site_snomed_code}")
        print(f"  Age at diagnosis: {metadata.diagnosis.age_at_diagnosis} days")
    
    print(f"\nClinical Trial: {metadata.clinical_trial.protocol_name}")
    print(f"  Protocol ID: {metadata.clinical_trial.protocol_id}")
    print(f"  Subject ID: {metadata.clinical_trial.subject_id}")
