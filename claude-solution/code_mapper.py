"""
DICOM Code Mapper Module

Maps CSV values to DICOM coded concepts including SNOMED CT codes
for anatomy, fixation, staining, and diagnosis codes.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import csv


@dataclass
class CodedConcept:
    """
    Represents a DICOM coded concept (code value, scheme, meaning).

    Attributes
    ----------
    value : str
        Code value (e.g., "15926001")
    scheme : str
        Coding scheme designator (e.g., "SCT" for SNOMED CT)
    meaning : str
        Code meaning (e.g., "Brain stem")
    """
    value: str
    scheme: str
    meaning: str


class DicomCodeMapper:
    """
    Maps CSV values to DICOM coded concepts.

    Provides mappings for:
    - Anatomic sites (ICD-O topography to SNOMED CT)
    - Diagnoses (ICD-O morphology codes)
    - Fixation methods (to SNOMED CT)
    - Embedding media (to SNOMED CT)
    - Staining methods (to SNOMED CT)
    - Sex (to DICOM PatientSex values)

    The mappings are derived from the shell scripts in idc-wsi-conversion
    (e.g., mcitodcm.sh, gtextodcm.sh).
    """

    # Coding scheme designators
    SCT = "SCT"      # SNOMED CT
    ICDO3 = "ICDO3"  # ICD-O-3
    DCM = "DCM"      # DICOM
    NCIT = "NCIt"    # NCI Thesaurus

    def __init__(self, icd_o_file: Optional[Path] = None):
        """
        Initialize code mapper.

        Parameters
        ----------
        icd_o_file : Path, optional
            Path to ICD-O-3 morphology code CSV file for extended lookups
        """
        self.icd_o_codes: Dict[str, str] = {}
        if icd_o_file and Path(icd_o_file).exists():
            self._load_icd_o_codes(Path(icd_o_file))

        self._init_anatomy_mappings()
        self._init_fixation_mappings()
        self._init_embedding_mappings()
        self._init_staining_mappings()
        self._init_tissue_type_mappings()

    def _load_icd_o_codes(self, filepath: Path) -> None:
        """Load ICD-O-3 morphology codes from CSV."""
        try:
            with open(filepath, 'r', encoding='latin-1') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 3 and row[1] == 'Preferred':
                        # Format: code, type, meaning
                        self.icd_o_codes[row[0]] = row[2]
        except Exception:
            pass  # Silently fail if file can't be read

    def _init_anatomy_mappings(self) -> None:
        """
        Initialize ICD-O topography to SNOMED CT mappings.

        Derived from mcitodcm.sh and other conversion scripts.
        Format: "ICD-O code : Description" -> SNOMED CT code
        """
        self._anatomy_map: Dict[str, CodedConcept] = {
            # Brain and CNS
            "C71.0 : Cerebrum": CodedConcept("83678007", self.SCT, "Cerebrum"),
            "C71.1 : Frontal lobe": CodedConcept("83251001", self.SCT, "Frontal lobe"),
            "C71.2 : Temporal lobe": CodedConcept("78277001", self.SCT, "Temporal lobe"),
            "C71.3 : Parietal lobe": CodedConcept("16630005", self.SCT, "Parietal lobe"),
            "C71.4 : Occipital lobe": CodedConcept("31065004", self.SCT, "Occipital lobe"),
            "C71.5 : Ventricle, NOS": CodedConcept("35764002", self.SCT, "Cerebral ventricle"),
            "C71.6 : Cerebellum, NOS": CodedConcept("113305005", self.SCT, "Cerebellar structure"),
            "C71.7 : Brain stem": CodedConcept("15926001", self.SCT, "Brain stem"),
            "C71.8 : Overlapping lesion of brain": CodedConcept("12738006", self.SCT, "Brain"),
            "C71.9 : Brain, NOS": CodedConcept("12738006", self.SCT, "Brain"),
            "C72.0 : Spinal cord": CodedConcept("2748008", self.SCT, "Spinal cord"),
            "C72.1 : Cauda equina": CodedConcept("7173007", self.SCT, "Cauda equina"),
            "C72.9 : Central nervous system": CodedConcept("21483005", self.SCT, "Central nervous system"),

            # Endocrine
            "C74.0 : Adrenal cortex": CodedConcept("68594002", self.SCT, "Adrenal cortex"),
            "C74.1 : Adrenal medulla": CodedConcept("23451007", self.SCT, "Adrenal medulla"),
            "C74.9 : Adrenal gland, NOS": CodedConcept("23451007", self.SCT, "Adrenal gland"),
            "C75.1 : Pituitary gland": CodedConcept("56329008", self.SCT, "Pituitary gland"),
            "C75.2 : Craniopharyngeal duct": CodedConcept("55926006", self.SCT, "Craniopharyngeal duct"),
            "C75.3 : Pineal gland": CodedConcept("45793000", self.SCT, "Pineal gland"),

            # Hematopoietic
            "C42.0 : Blood": CodedConcept("87612001", self.SCT, "Blood"),
            "C42.1 : Bone marrow": CodedConcept("14016003", self.SCT, "Bone marrow"),

            # Thorax
            "C34.0 : Main bronchus": CodedConcept("102297006", self.SCT, "Main bronchus"),
            "C34.1 : Upper lobe, lung": CodedConcept("45653009", self.SCT, "Upper lobe of lung"),
            "C34.2 : Middle lobe, lung": CodedConcept("72481006", self.SCT, "Middle lobe of right lung"),
            "C34.3 : Lower lobe, lung": CodedConcept("90572001", self.SCT, "Lower lobe of lung"),
            "C34.9 : Lung, NOS": CodedConcept("39607008", self.SCT, "Lung"),
            "C37.9 : Thymus": CodedConcept("9875009", self.SCT, "Thymus"),
            "C38.0 : Heart": CodedConcept("80891009", self.SCT, "Heart"),

            # Abdomen
            "C22.0 : Liver": CodedConcept("10200004", self.SCT, "Liver"),
            "C22.1 : Intrahepatic bile duct": CodedConcept("58716001", self.SCT, "Intrahepatic bile duct"),
            "C23.9 : Gallbladder": CodedConcept("28231008", self.SCT, "Gallbladder"),
            "C25.0 : Head of pancreas": CodedConcept("64163001", self.SCT, "Head of pancreas"),
            "C25.9 : Pancreas, NOS": CodedConcept("15776009", self.SCT, "Pancreas"),

            # Retroperitoneum
            "C48.0 : Retroperitoneum": CodedConcept("82849001", self.SCT, "Retroperitoneum"),
            "C48.1 : Specified parts of peritoneum": CodedConcept("15425007", self.SCT, "Peritoneum"),
            "C48.2 : Peritoneum, NOS": CodedConcept("15425007", self.SCT, "Peritoneum"),

            # Urinary
            "C64.9 : Kidney, NOS": CodedConcept("64033007", self.SCT, "Kidney"),
            "C65.9 : Renal pelvis": CodedConcept("25990002", self.SCT, "Renal pelvis"),
            "C66.9 : Ureter": CodedConcept("87953007", self.SCT, "Ureter"),
            "C67.9 : Bladder, NOS": CodedConcept("89837001", self.SCT, "Urinary bladder"),
            "C68.0 : Urethra": CodedConcept("13648007", self.SCT, "Urethra"),

            # Male genital
            "C61.9 : Prostate gland": CodedConcept("41216001", self.SCT, "Prostate"),
            "C62.9 : Testis, NOS": CodedConcept("40689003", self.SCT, "Testis"),

            # Female genital
            "C53.9 : Cervix uteri": CodedConcept("71252005", self.SCT, "Cervix"),
            "C54.1 : Endometrium": CodedConcept("2739003", self.SCT, "Endometrium"),
            "C54.9 : Corpus uteri": CodedConcept("35039007", self.SCT, "Uterus"),
            "C55.9 : Uterus, NOS": CodedConcept("35039007", self.SCT, "Uterus"),
            "C56.9 : Ovary": CodedConcept("15497006", self.SCT, "Ovary"),
            "C57.0 : Fallopian tube": CodedConcept("31435000", self.SCT, "Fallopian tube"),

            # Breast
            "C50.9 : Breast, NOS": CodedConcept("76752008", self.SCT, "Breast"),

            # Skin
            "C44.9 : Skin, NOS": CodedConcept("39937001", self.SCT, "Skin"),

            # Bones
            "C40.0 : Long bones of upper limb": CodedConcept("410030009", self.SCT, "Bone structure of upper extremity"),
            "C40.2 : Long bones of lower limb": CodedConcept("410029004", self.SCT, "Bone structure of lower extremity"),
            "C41.0 : Bones of skull and face and associated joints": CodedConcept("272679001", self.SCT, "Cranial and/or facial bone"),
            "C41.2 : Vertebral column": CodedConcept("421060004", self.SCT, "Vertebral column"),
            "C41.4 : Pelvic bones": CodedConcept("12921003", self.SCT, "Pelvic bone"),
            "C41.9 : Bone, NOS": CodedConcept("272673000", self.SCT, "Bone"),

            # Soft tissue
            "C47.9 : Peripheral nerves and autonomic nervous system": CodedConcept("84782009", self.SCT, "Peripheral nerve"),
            "C49.0 : Connective tissue of head, face and neck": CodedConcept("71836000", self.SCT, "Soft tissue"),
            "C49.9 : Connective, subcutaneous and other soft tissues, NOS": CodedConcept("71836000", self.SCT, "Soft tissue"),

            # Eye
            "C69.0 : Conjunctiva": CodedConcept("29445007", self.SCT, "Conjunctiva"),
            "C69.2 : Retina": CodedConcept("5665001", self.SCT, "Retina"),
            "C69.4 : Ciliary body": CodedConcept("29534007", self.SCT, "Ciliary body"),
            "C69.6 : Orbit, NOS": CodedConcept("363654007", self.SCT, "Orbit"),
            "C69.9 : Eye, NOS": CodedConcept("81745001", self.SCT, "Eye"),

            # Lymph nodes
            "C77.0 : Lymph nodes of head, face and neck": CodedConcept("59441001", self.SCT, "Lymph node"),
            "C77.9 : Lymph node, NOS": CodedConcept("59441001", self.SCT, "Lymph node"),

            # GI tract
            "C15.9 : Esophagus, NOS": CodedConcept("32849002", self.SCT, "Esophagus"),
            "C16.9 : Stomach, NOS": CodedConcept("69695003", self.SCT, "Stomach"),
            "C17.0 : Duodenum": CodedConcept("38848004", self.SCT, "Duodenum"),
            "C17.9 : Small intestine, NOS": CodedConcept("30315005", self.SCT, "Small intestine"),
            "C18.9 : Colon, NOS": CodedConcept("71854001", self.SCT, "Colon"),
            "C19.9 : Rectosigmoid junction": CodedConcept("49832006", self.SCT, "Rectosigmoid junction"),
            "C20.9 : Rectum, NOS": CodedConcept("34402009", self.SCT, "Rectum"),

            # Head and neck
            "C00.9 : Lip, NOS": CodedConcept("81083006", self.SCT, "Lip"),
            "C01.9 : Base of tongue": CodedConcept("47975008", self.SCT, "Base of tongue"),
            "C02.9 : Tongue, NOS": CodedConcept("21974007", self.SCT, "Tongue"),
            "C07.9 : Parotid gland": CodedConcept("45289007", self.SCT, "Parotid gland"),
            "C08.9 : Major salivary gland, NOS": CodedConcept("385296007", self.SCT, "Salivary gland"),
            "C09.9 : Tonsil, NOS": CodedConcept("75573002", self.SCT, "Tonsil"),
            "C10.9 : Oropharynx, NOS": CodedConcept("31389004", self.SCT, "Oropharynx"),
            "C11.9 : Nasopharynx, NOS": CodedConcept("71836000", self.SCT, "Nasopharynx"),
            "C13.9 : Hypopharynx, NOS": CodedConcept("81502006", self.SCT, "Hypopharynx"),
            "C30.0 : Nasal cavity": CodedConcept("279549004", self.SCT, "Nasal cavity"),
            "C31.0 : Maxillary sinus": CodedConcept("15924003", self.SCT, "Maxillary sinus"),
            "C32.9 : Larynx, NOS": CodedConcept("4596009", self.SCT, "Larynx"),
            "C73.9 : Thyroid gland": CodedConcept("69748006", self.SCT, "Thyroid gland"),

            # Unknown
            "C76.0 : Head, face or neck, NOS": CodedConcept("774007", self.SCT, "Head and/or neck structure"),
            "C76.7 : Other ill-defined sites": CodedConcept("39801007", self.SCT, "Body structure"),
            "C80.9 : Unknown primary site": CodedConcept("39801007", self.SCT, "Body structure"),
        }

    def _init_fixation_mappings(self) -> None:
        """Initialize fixation method mappings."""
        self._fixation_map: Dict[str, CodedConcept] = {
            # Formalin-based fixation
            "FFPE": CodedConcept("431510009", self.SCT, "Formalin fixed and target antigen retrieved"),
            "Formalin fixed paraffin embedded (FFPE)": CodedConcept("431510009", self.SCT, "Formalin fixed and target antigen retrieved"),
            "Formalin-Fixed Paraffin-Embedded": CodedConcept("431510009", self.SCT, "Formalin fixed and target antigen retrieved"),
            "Formalin": CodedConcept("431510009", self.SCT, "Formalin fixed and target antigen retrieved"),
            "10% Neutral Buffered Formalin": CodedConcept("434162003", self.SCT, "Neutral Buffered Formalin"),
            "PAXgene": CodedConcept("C185113", self.NCIT, "PAXgene Tissue System"),

            # Frozen/OCT
            "OCT": CodedConcept("433469005", self.SCT, "Tissue freezing medium"),
            "Optimal Cutting Temperature": CodedConcept("433469005", self.SCT, "Tissue freezing medium"),
            "Frozen": CodedConcept("433469005", self.SCT, "Tissue freezing medium"),
        }

        self._fixation_abbreviations: Dict[str, str] = {
            "FFPE": "FF",
            "Formalin fixed paraffin embedded (FFPE)": "FF",
            "Formalin-Fixed Paraffin-Embedded": "FF",
            "Formalin": "FF",
            "10% Neutral Buffered Formalin": "FF",
            "PAXgene": "PG",
            "OCT": "OCT",
            "Optimal Cutting Temperature": "OCT",
            "Frozen": "FR",
        }

    def _init_embedding_mappings(self) -> None:
        """Initialize embedding media mappings."""
        self._embedding_map: Dict[str, CodedConcept] = {
            # Paraffin embedding
            "FFPE": CodedConcept("311731000", self.SCT, "Paraffin wax"),
            "Formalin fixed paraffin embedded (FFPE)": CodedConcept("311731000", self.SCT, "Paraffin wax"),
            "Formalin-Fixed Paraffin-Embedded": CodedConcept("311731000", self.SCT, "Paraffin wax"),
            "Paraffin": CodedConcept("311731000", self.SCT, "Paraffin wax"),
            "Paraffin wax": CodedConcept("311731000", self.SCT, "Paraffin wax"),
            # OCT is the embedding medium itself (frozen sections)
        }

        self._embedding_abbreviations: Dict[str, str] = {
            "FFPE": "PE",
            "Formalin fixed paraffin embedded (FFPE)": "PE",
            "Formalin-Fixed Paraffin-Embedded": "PE",
            "Paraffin": "PE",
            "Paraffin wax": "PE",
        }

    def _init_staining_mappings(self) -> None:
        """Initialize staining method mappings."""
        # Each staining method maps to a list of (code, scheme, meaning) tuples
        self._staining_map: Dict[str, List[CodedConcept]] = {
            # H&E - two stains
            "H&E": [
                CodedConcept("12710003", self.SCT, "hematoxylin stain"),
                CodedConcept("36879007", self.SCT, "water soluble eosin stain")
            ],
            "Hematoxylin and Eosin Staining Method": [
                CodedConcept("12710003", self.SCT, "hematoxylin stain"),
                CodedConcept("36879007", self.SCT, "water soluble eosin stain")
            ],
            "HE": [
                CodedConcept("12710003", self.SCT, "hematoxylin stain"),
                CodedConcept("36879007", self.SCT, "water soluble eosin stain")
            ],

            # Immunohistochemistry
            "IHC": [
                CodedConcept("127790008", self.SCT, "immunohistochemical stain")
            ],
            "Immunohistochemistry": [
                CodedConcept("127790008", self.SCT, "immunohistochemical stain")
            ],

            # Other common stains
            "PAS": [
                CodedConcept("104210008", self.SCT, "periodic acid Schiff stain")
            ],
            "Masson trichrome": [
                CodedConcept("76574004", self.SCT, "Masson trichrome stain")
            ],
            "Silver stain": [
                CodedConcept("86243006", self.SCT, "silver stain")
            ],
            "Giemsa": [
                CodedConcept("62778005", self.SCT, "Giemsa stain")
            ],
        }

        self._staining_abbreviations: Dict[str, str] = {
            "H&E": "HE",
            "Hematoxylin and Eosin Staining Method": "HE",
            "HE": "HE",
            "IHC": "IHC",
            "Immunohistochemistry": "IHC",
            "PAS": "PAS",
            "Masson trichrome": "MT",
            "Silver stain": "SS",
            "Giemsa": "GI",
        }

    def _init_tissue_type_mappings(self) -> None:
        """Initialize tissue type (tumor status) mappings."""
        self._tissue_type_map: Dict[str, CodedConcept] = {
            "Normal": CodedConcept("17621005", self.SCT, "Normal"),
            "Tumor": CodedConcept("108369006", self.SCT, "Tumor"),
            "Neoplastic": CodedConcept("108369006", self.SCT, "Neoplastic"),
        }

        self._tissue_type_abbreviations: Dict[str, str] = {
            "Normal": "N",
            "Tumor": "T",
            "Neoplastic": "T",
        }

    def map_anatomy_to_snomed(self, anatomic_site: str) -> Optional[CodedConcept]:
        """
        Map anatomic site string to SNOMED CT code.

        Handles ICD-O topography format (e.g., "C71.7 : Brain stem")
        as well as partial matches.

        Parameters
        ----------
        anatomic_site : str
            Anatomic site from CSV (e.g., "C71.7 : Brain stem")

        Returns
        -------
        CodedConcept or None
            SNOMED CT code for the anatomy
        """
        if not anatomic_site or anatomic_site in ("Not Reported", "Invalid value", ""):
            return None

        # Direct lookup
        anatomy = self._anatomy_map.get(anatomic_site)
        if anatomy:
            return anatomy

        # Try partial match (anatomic_site might have extra whitespace or variations)
        for key, anat in self._anatomy_map.items():
            # Check if the ICD-O code portion matches
            if anatomic_site.startswith(key.split(":")[0].strip()):
                return anat
            # Check if key is contained in anatomic_site
            if key in anatomic_site:
                return anat

        return None

    def resolve_diagnosis_code(
        self,
        diagnosis_data: Dict[str, str]
    ) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """
        Resolve diagnosis to ICD-O-3 code.

        Parses diagnosis strings in format "9470/3 : Medulloblastoma, NOS"
        into code components.

        Parameters
        ----------
        diagnosis_data : dict
            Diagnosis data with 'diagnosis', 'diagnosis_classification_system', etc.

        Returns
        -------
        tuple
            (code_value, coding_scheme, code_meaning) or (None, None, None)
        """
        diagnosis = diagnosis_data.get('diagnosis', '')
        if not diagnosis or diagnosis == "see diagnosis_comment":
            # Use diagnosis_comment as description only
            comment = diagnosis_data.get('diagnosis_comment', '')
            if comment:
                return None, None, comment
            return None, None, None

        # Extract ICD-O code from format like "9470/3 : Medulloblastoma, NOS"
        parts = diagnosis.split(' : ', 1)
        if len(parts) >= 2:
            code = parts[0].strip()
            meaning = parts[1].strip()

            # Skip unknown codes (999x/x)
            if code.startswith('999'):
                return None, None, meaning

            return code, self.ICDO3, meaning

        # Try looking up in ICD-O file
        if diagnosis in self.icd_o_codes:
            return diagnosis, self.ICDO3, self.icd_o_codes[diagnosis]

        # Return the diagnosis as meaning only
        return None, None, diagnosis

    def map_fixation_to_codes(
        self,
        fixation_method: str
    ) -> Tuple[Optional[CodedConcept], Optional[CodedConcept]]:
        """
        Map fixation method to fixative and embedding codes.

        Parameters
        ----------
        fixation_method : str
            Fixation/embedding method from CSV (e.g., "FFPE", "OCT")

        Returns
        -------
        tuple
            (fixative_code, embedding_code) where either may be None
        """
        if not fixation_method:
            return None, None

        fixative_code = self._fixation_map.get(fixation_method)
        embedding_code = self._embedding_map.get(fixation_method)

        return fixative_code, embedding_code

    def map_staining_to_codes(self, staining_method: str) -> List[CodedConcept]:
        """
        Map staining method to SNOMED CT stain codes.

        Parameters
        ----------
        staining_method : str
            Staining method from CSV (e.g., "H&E", "IHC")

        Returns
        -------
        list
            List of CodedConcept objects for the stains
        """
        if not staining_method:
            return []

        return self._staining_map.get(staining_method, [])

    def get_fixation_abbreviation(self, fixation_method: str) -> Optional[str]:
        """
        Get short abbreviation for fixation method.

        Parameters
        ----------
        fixation_method : str
            Fixation method

        Returns
        -------
        str or None
            Short abbreviation (e.g., "FF" for formalin fixed)
        """
        if not fixation_method:
            return None
        return self._fixation_abbreviations.get(fixation_method)

    def get_embedding_abbreviation(self, embedding_method: str) -> Optional[str]:
        """
        Get short abbreviation for embedding method.

        Parameters
        ----------
        embedding_method : str
            Embedding method

        Returns
        -------
        str or None
            Short abbreviation (e.g., "PE" for paraffin embedded)
        """
        if not embedding_method:
            return None
        return self._embedding_abbreviations.get(embedding_method)

    def get_staining_abbreviation(self, staining_method: str) -> Optional[str]:
        """
        Get short abbreviation for staining method.

        Parameters
        ----------
        staining_method : str
            Staining method

        Returns
        -------
        str or None
            Short abbreviation (e.g., "HE" for H&E)
        """
        if not staining_method:
            return None
        return self._staining_abbreviations.get(staining_method)

    def get_tissue_type_code(self, tumor_status: str) -> Optional[CodedConcept]:
        """
        Get tissue type SNOMED code.

        Parameters
        ----------
        tumor_status : str
            Tumor status (e.g., "Tumor", "Normal")

        Returns
        -------
        CodedConcept or None
            SNOMED code for the tissue type
        """
        if not tumor_status:
            return None
        return self._tissue_type_map.get(tumor_status)

    def get_tissue_type_abbreviation(self, tumor_status: str) -> Optional[str]:
        """
        Get tissue type abbreviation.

        Parameters
        ----------
        tumor_status : str
            Tumor status

        Returns
        -------
        str or None
            Abbreviation (e.g., "T" for tumor, "N" for normal)
        """
        if not tumor_status:
            return None
        return self._tissue_type_abbreviations.get(tumor_status)

    def map_sex(self, sex_at_birth: Optional[str]) -> Optional[str]:
        """
        Map sex value to DICOM PatientSex code.

        Parameters
        ----------
        sex_at_birth : str or None
            Sex value from CSV (e.g., "Male", "Female")

        Returns
        -------
        str or None
            DICOM PatientSex code ("M", "F", or "O")
        """
        if not sex_at_birth:
            return None

        sex_lower = sex_at_birth.lower().strip()

        if sex_lower in ("male", "m"):
            return "M"
        elif sex_lower in ("female", "f"):
            return "F"
        elif sex_lower in ("other", "o"):
            return "O"

        return None
