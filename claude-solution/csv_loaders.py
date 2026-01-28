"""
CSV Loader Module

Provides abstract base class and collection-specific implementations
for loading metadata from CSV files.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any
import pandas as pd


@dataclass
class SampleData:
    """
    Resolved sample-level data from CSV sources.

    Attributes
    ----------
    sample_id : str
        Sample identifier
    participant_id : str
        Participant/patient identifier
    anatomic_site : str, optional
        Anatomic site (e.g., "C71.7 : Brain stem")
    tumor_status : str, optional
        Tumor status (e.g., "Tumor", "Normal")
    tumor_classification : str, optional
        Tumor classification
    fixation_method : str, optional
        Fixation/embedding method (e.g., "OCT", "FFPE")
    staining_method : str, optional
        Staining method (e.g., "H&E")
    magnification : str, optional
        Objective magnification (e.g., "40X")
    percent_tumor : str, optional
        Percentage of tumor tissue
    percent_necrosis : str, optional
        Percentage of necrotic tissue
    """
    sample_id: str
    participant_id: str
    anatomic_site: Optional[str] = None
    tumor_status: Optional[str] = None
    tumor_classification: Optional[str] = None
    fixation_method: Optional[str] = None
    staining_method: Optional[str] = None
    magnification: Optional[str] = None
    percent_tumor: Optional[str] = None
    percent_necrosis: Optional[str] = None


class CSVLoaderBase(ABC):
    """
    Abstract base class for collection-specific CSV loaders.

    Subclasses implement format-specific parsing logic while
    maintaining a consistent interface for the metadata handler.

    This pattern allows easy customization for different collections
    (MCI/CCDI, GTEx, CMB, etc.) by implementing the abstract methods.
    """

    @abstractmethod
    def load(self, csv_directory: Path) -> None:
        """
        Load CSV files from directory.

        Parameters
        ----------
        csv_directory : Path
            Directory containing CSV files
        """
        pass

    @abstractmethod
    def get_samples_for_file(self, filename: str) -> List[str]:
        """
        Get sample IDs associated with a file.

        Parameters
        ----------
        filename : str
            Input file name (e.g., "0DWWQ6.svs")

        Returns
        -------
        List[str]
            List of sample IDs associated with the file
        """
        pass

    @abstractmethod
    def get_sample_data(self, sample_id: str) -> Optional[SampleData]:
        """
        Get sample-level data by sample ID.

        Parameters
        ----------
        sample_id : str
            Sample identifier

        Returns
        -------
        SampleData or None
            Sample data if found
        """
        pass

    @abstractmethod
    def get_participant_data(self, participant_id: str) -> Optional[Dict[str, Any]]:
        """
        Get participant-level data by participant ID.

        Parameters
        ----------
        participant_id : str
            Participant/patient identifier

        Returns
        -------
        dict or None
            Participant data including sex_at_birth, race, etc.
        """
        pass

    @abstractmethod
    def get_diagnosis_data(
        self,
        participant_id: str,
        sample_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get diagnosis data, preferring participant-based lookup.

        Parameters
        ----------
        participant_id : str
            Participant identifier
        sample_id : str, optional
            Sample identifier for fallback lookup

        Returns
        -------
        dict or None
            Diagnosis data including diagnosis code, anatomic_site, etc.
        """
        pass

    @abstractmethod
    def get_imaging_data(
        self,
        filename: str,
        sample_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get imaging-specific data (fixation, staining, magnification).

        Parameters
        ----------
        filename : str
            Input file name
        sample_id : str
            Sample identifier

        Returns
        -------
        dict or None
            Imaging data including fixation_embedding_method, staining_method, etc.
        """
        pass


class MCICCDILoader(CSVLoaderBase):
    """
    CSV loader for MCI/CCDI format (CCDI Submission Template).

    Handles the four-file structure:
    - pathology_file.csv: file_name -> sample.sample_id, fixation, staining
    - sample.csv: sample_id -> participant.participant_id, anatomic_site
    - participant.csv: participant_id -> sex_at_birth, race
    - diagnosis.csv: participant_id/sample_id -> diagnosis codes

    This loader is designed for the MCI (Molecular Characterization Initiative)
    data following the CCDI (Childhood Cancer Data Initiative) data model.
    """

    def __init__(self, metadata_basename: str):
        """
        Initialize with metadata file basename.

        Parameters
        ----------
        metadata_basename : str
            Base name of CSV files (e.g., 'phs002790_MCI_Release38_CCDI_v2.1.0_IDC_Submission_6')
        """
        self.metadata_basename = metadata_basename
        self.pathology_df: Optional[pd.DataFrame] = None
        self.sample_df: Optional[pd.DataFrame] = None
        self.participant_df: Optional[pd.DataFrame] = None
        self.diagnosis_df: Optional[pd.DataFrame] = None
        self._loaded = False

    def load(self, csv_directory: Path) -> None:
        """
        Load all MCI/CCDI CSV files.

        Parameters
        ----------
        csv_directory : Path
            Directory containing the CSV files
        """
        csv_directory = Path(csv_directory)

        # Load pathology_file.csv
        pathology_path = csv_directory / f"{self.metadata_basename}_pathology_file.csv"
        if pathology_path.exists():
            self.pathology_df = pd.read_csv(
                pathology_path,
                dtype=str,
                na_values=[''],
                keep_default_na=False
            )
            self._clean_columns(self.pathology_df)

        # Load sample.csv
        sample_path = csv_directory / f"{self.metadata_basename}_sample.csv"
        if sample_path.exists():
            self.sample_df = pd.read_csv(
                sample_path,
                dtype=str,
                na_values=[''],
                keep_default_na=False
            )
            self._clean_columns(self.sample_df)

        # Load participant.csv
        participant_path = csv_directory / f"{self.metadata_basename}_participant.csv"
        if participant_path.exists():
            self.participant_df = pd.read_csv(
                participant_path,
                dtype=str,
                na_values=[''],
                keep_default_na=False
            )
            self._clean_columns(self.participant_df)

        # Load diagnosis.csv
        diagnosis_path = csv_directory / f"{self.metadata_basename}_diagnosis.csv"
        if diagnosis_path.exists():
            self.diagnosis_df = pd.read_csv(
                diagnosis_path,
                dtype=str,
                na_values=[''],
                keep_default_na=False
            )
            self._clean_columns(self.diagnosis_df)

        self._loaded = True

    def _clean_columns(self, df: pd.DataFrame) -> None:
        """Clean column names (remove BOM if present)."""
        df.columns = [c.lstrip('\ufeff').strip() for c in df.columns]

    def get_samples_for_file(self, filename: str) -> List[str]:
        """
        Get sample IDs from pathology_file.csv by filename.

        Parameters
        ----------
        filename : str
            Input file name (e.g., "0DWWQ6.svs")

        Returns
        -------
        List[str]
            List of sample IDs
        """
        if self.pathology_df is None:
            return []

        matches = self.pathology_df[
            self.pathology_df['file_name'] == filename
        ]

        # Column name may be 'sample.sample_id' or just 'sample_id'
        sample_col = 'sample.sample_id' if 'sample.sample_id' in matches.columns else 'sample_id'

        return matches[sample_col].dropna().unique().tolist()

    def get_sample_data(self, sample_id: str) -> Optional[SampleData]:
        """
        Get sample data from sample.csv.

        Parameters
        ----------
        sample_id : str
            Sample identifier

        Returns
        -------
        SampleData or None
            Sample data if found
        """
        if self.sample_df is None:
            return None

        matches = self.sample_df[
            self.sample_df['sample_id'] == sample_id
        ]

        if matches.empty:
            return None

        row = matches.iloc[0]

        # Handle column name variations
        participant_col = 'participant.participant_id' if 'participant.participant_id' in row.index else 'participant_id'

        return SampleData(
            sample_id=sample_id,
            participant_id=self._get_value(row, participant_col),
            anatomic_site=self._get_value(row, 'anatomic_site'),
            tumor_status=self._get_value(row, 'sample_tumor_status'),
            tumor_classification=self._get_value(row, 'tumor_classification')
        )

    def get_participant_data(self, participant_id: str) -> Optional[Dict[str, Any]]:
        """
        Get participant data from participant.csv.

        Parameters
        ----------
        participant_id : str
            Participant identifier

        Returns
        -------
        dict or None
            Participant data
        """
        if self.participant_df is None:
            return None

        matches = self.participant_df[
            self.participant_df['participant_id'] == participant_id
        ]

        if matches.empty:
            return None

        row = matches.iloc[0]
        return {
            'sex_at_birth': self._get_value(row, 'sex_at_birth'),
            'race': self._get_value(row, 'race'),
            'ethnicity': self._get_value(row, 'ethnicity'),
        }

    def get_diagnosis_data(
        self,
        participant_id: str,
        sample_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get diagnosis data from diagnosis.csv.

        Prioritizes primary diagnosis (excludes CNS_category and CNS5_diagnosis
        unless primary code is 999).

        Parameters
        ----------
        participant_id : str
            Participant identifier
        sample_id : str, optional
            Sample identifier for fallback lookup

        Returns
        -------
        dict or None
            Diagnosis data
        """
        if self.diagnosis_df is None:
            return None

        # Handle column name variations
        participant_col = 'participant.participant_id' if 'participant.participant_id' in self.diagnosis_df.columns else 'participant_id'

        # First try by participant_id
        matches = self.diagnosis_df[
            self.diagnosis_df[participant_col] == participant_id
        ]

        if matches.empty and sample_id:
            # Fall back to sample_id lookup
            sample_col = 'sample.sample_id' if 'sample.sample_id' in self.diagnosis_df.columns else 'sample_id'
            matches = self.diagnosis_df[
                self.diagnosis_df[sample_col] == sample_id
            ]

        if matches.empty:
            return None

        # Filter out CNS_category and CNS5_diagnosis entries initially
        # These are additional classification entries, not the primary diagnosis
        primary_matches = matches[
            ~matches['diagnosis_id'].str.contains('_CNS_category|_CNS5_diagnosis',
                                                   na=False, regex=True)
        ]

        if not primary_matches.empty:
            row = primary_matches.iloc[0]
            diagnosis_value = self._get_value(row, 'diagnosis')

            # If primary code is 999 (unknown), try CNS5_diagnosis as fallback
            if diagnosis_value and diagnosis_value.startswith('999'):
                cns5_matches = matches[
                    matches['diagnosis_id'].str.contains('_CNS5_diagnosis', na=False)
                ]
                if not cns5_matches.empty:
                    row = cns5_matches.iloc[0]
        else:
            row = matches.iloc[0]

        return {
            'diagnosis': self._get_value(row, 'diagnosis'),
            'diagnosis_classification_system': self._get_value(row, 'diagnosis_classification_system'),
            'diagnosis_comment': self._get_value(row, 'diagnosis_comment'),
            'anatomic_site': self._get_value(row, 'anatomic_site'),
            'age_at_diagnosis': self._parse_age(self._get_value(row, 'age_at_diagnosis')),
        }

    def get_imaging_data(
        self,
        filename: str,
        sample_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get imaging data from pathology_file.csv.

        Parameters
        ----------
        filename : str
            Input file name
        sample_id : str
            Sample identifier

        Returns
        -------
        dict or None
            Imaging data
        """
        if self.pathology_df is None:
            return None

        # Column name may be 'sample.sample_id' or just 'sample_id'
        sample_col = 'sample.sample_id' if 'sample.sample_id' in self.pathology_df.columns else 'sample_id'

        matches = self.pathology_df[
            (self.pathology_df['file_name'] == filename) &
            (self.pathology_df[sample_col] == sample_id)
        ]

        if matches.empty:
            # Try matching just by filename
            matches = self.pathology_df[
                self.pathology_df['file_name'] == filename
            ]

        if matches.empty:
            return None

        row = matches.iloc[0]
        return {
            'fixation_embedding_method': self._get_value(row, 'fixation_embedding_method'),
            'staining_method': self._get_value(row, 'staining_method'),
            'magnification': self._get_value(row, 'magnification'),
            'percent_tumor': self._get_value(row, 'percent_tumor'),
            'percent_necrosis': self._get_value(row, 'percent_necrosis'),
            'image_modality': self._get_value(row, 'image_modality'),
        }

    def _get_value(self, row: pd.Series, column: str) -> Optional[str]:
        """
        Safely get value from row, returning None for missing/empty values.

        Parameters
        ----------
        row : pd.Series
            DataFrame row
        column : str
            Column name

        Returns
        -------
        str or None
            Value or None
        """
        if column not in row.index:
            return None
        val = row.get(column)
        if pd.isna(val) or val == '' or val is None:
            return None
        return str(val).strip()

    def _parse_age(self, age_str: Optional[str]) -> Optional[int]:
        """
        Parse age string to integer.

        Parameters
        ----------
        age_str : str or None
            Age string (in days)

        Returns
        -------
        int or None
            Age in days, or None for invalid values
        """
        if not age_str:
            return None
        try:
            age = int(float(age_str))
            return age if age >= 0 else None
        except (ValueError, TypeError):
            return None


class GTExLoader(CSVLoaderBase):
    """
    CSV loader for GTEx collection format.

    GTEx uses a single CSV file with columns:
    Case ID, Age, Gender, Specimen ID, Tissue Type, Fixative, etc.

    This is a stub implementation - extend as needed for GTEx support.
    """

    def __init__(self, csv_filename: str = "GTEX_image_meta.final_plus_7_slides.csv"):
        """
        Initialize with CSV filename.

        Parameters
        ----------
        csv_filename : str
            Name of the GTEx CSV file
        """
        self.csv_filename = csv_filename
        self.df: Optional[pd.DataFrame] = None

    def load(self, csv_directory: Path) -> None:
        """Load GTEx CSV file."""
        csv_path = Path(csv_directory) / self.csv_filename
        if csv_path.exists():
            self.df = pd.read_csv(
                csv_path,
                dtype=str,
                na_values=[''],
                keep_default_na=False
            )

    def get_samples_for_file(self, filename: str) -> List[str]:
        """Get sample IDs - for GTEx, extract from filename."""
        # GTEx pattern: GTEX-N7MS-0325.svs -> GTEX-N7MS-0325
        slide_id = filename.replace('.svs', '').replace('.dcm', '')
        return [slide_id]

    def get_sample_data(self, sample_id: str) -> Optional[SampleData]:
        """Get sample data from GTEx CSV."""
        if self.df is None:
            return None

        matches = self.df[self.df['Specimen ID'] == sample_id]
        if matches.empty:
            return None

        row = matches.iloc[0]
        # Extract subject_id from specimen_id (GTEX-XXXX from GTEX-XXXX-YYYY)
        parts = sample_id.split('-')
        subject_id = '-'.join(parts[:2]) if len(parts) >= 2 else sample_id

        return SampleData(
            sample_id=sample_id,
            participant_id=subject_id,
            anatomic_site=row.get('Tissue Type'),
            fixation_method=row.get('Fixative'),
        )

    def get_participant_data(self, participant_id: str) -> Optional[Dict[str, Any]]:
        """Get participant data from GTEx CSV."""
        if self.df is None:
            return None

        # GTEx has participant info in the same row as sample
        matches = self.df[self.df['Case ID'] == participant_id]
        if matches.empty:
            return None

        row = matches.iloc[0]
        return {
            'sex_at_birth': row.get('Gender'),
            'age': row.get('Age'),
        }

    def get_diagnosis_data(
        self,
        participant_id: str,
        sample_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """GTEx doesn't have diagnosis data in the standard sense."""
        return None

    def get_imaging_data(
        self,
        filename: str,
        sample_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get imaging data from GTEx CSV."""
        if self.df is None:
            return None

        matches = self.df[self.df['Specimen ID'] == sample_id]
        if matches.empty:
            return None

        row = matches.iloc[0]
        return {
            'fixation_embedding_method': row.get('Fixative'),
            'staining_method': 'H&E',  # GTEx slides are typically H&E
        }
