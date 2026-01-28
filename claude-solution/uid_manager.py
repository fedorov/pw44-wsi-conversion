"""
UID Mapping Manager Module

Manages persistent UID mappings for specimen and study identifiers
to ensure consistency across conversion runs and multiple series per study.
"""

from pathlib import Path
from typing import Dict, Optional
import csv
import uuid
from datetime import datetime


class UIDMappingManager:
    """
    Manages persistent UID mappings for specimen and study identifiers.

    Maintains CSV files mapping identifiers to UIDs to ensure
    consistency across conversion runs. This follows the same pattern
    as the shell scripts (e.g., MCIspecimenIDToUIDMap.csv).

    The UID format follows DICOM standard using UUID-derived OIDs:
    2.25.{uuid_as_integer}

    Attributes
    ----------
    specimen_map_file : Path
        CSV file for specimen_id -> UID mapping
    study_uid_map_file : Path
        CSV file for study_id -> StudyInstanceUID mapping
    study_datetime_map_file : Path, optional
        CSV file for study_id -> datetime mapping
    """

    UID_PREFIX = "2.25"  # UUID-derived OID prefix per ISO/IEC 9834-8

    def __init__(
        self,
        specimen_map_file: Path,
        study_uid_map_file: Path,
        study_datetime_map_file: Optional[Path] = None
    ):
        """
        Initialize the UID mapping manager.

        Parameters
        ----------
        specimen_map_file : Path
            CSV file for specimen_id -> UID mapping
        study_uid_map_file : Path
            CSV file for study_id -> StudyInstanceUID mapping
        study_datetime_map_file : Path, optional
            CSV file for study_id -> datetime mapping
        """
        self.specimen_map_file = Path(specimen_map_file)
        self.study_uid_map_file = Path(study_uid_map_file)
        self.study_datetime_map_file = Path(study_datetime_map_file) if study_datetime_map_file else None

        # In-memory caches
        self._specimen_cache: Dict[str, str] = {}
        self._study_uid_cache: Dict[str, str] = {}
        self._study_datetime_cache: Dict[str, str] = {}

        # Load existing mappings
        self._load_mappings()

    def _load_mappings(self) -> None:
        """Load existing mappings from CSV files into memory caches."""
        self._specimen_cache = self._load_csv_map(self.specimen_map_file)
        self._study_uid_cache = self._load_csv_map(self.study_uid_map_file)
        if self.study_datetime_map_file:
            self._study_datetime_cache = self._load_csv_map(self.study_datetime_map_file)

    def _load_csv_map(self, filepath: Path) -> Dict[str, str]:
        """
        Load a two-column CSV into a dictionary.

        Parameters
        ----------
        filepath : Path
            Path to the CSV file

        Returns
        -------
        Dict[str, str]
            Dictionary mapping first column to second column
        """
        mapping = {}
        if filepath.exists():
            with open(filepath, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 2 and row[0].strip():
                        mapping[row[0].strip()] = row[1].strip()
        return mapping

    def _save_to_csv(self, filepath: Path, key: str, value: str) -> None:
        """
        Append a key-value pair to a CSV file.

        Creates parent directories if they don't exist.

        Parameters
        ----------
        filepath : Path
            Path to the CSV file
        key : str
            Key (first column)
        value : str
            Value (second column)
        """
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, 'a', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([key, value])

    def generate_new_uid(self) -> str:
        """
        Generate a new UUID-based DICOM UID.

        Uses the UUID-derived OID format (2.25.{uuid_as_integer})
        which is the standard approach for generating globally unique
        DICOM UIDs without requiring an organizational root.

        Returns
        -------
        str
            New UID in format "2.25.{uuid_as_integer}"
        """
        uuid_int = uuid.uuid4().int
        return f"{self.UID_PREFIX}.{uuid_int}"

    def get_or_create_specimen_uid(self, specimen_id: str) -> str:
        """
        Get existing or create new UID for specimen identifier.

        If the specimen_id already has a mapped UID, returns it.
        Otherwise, generates a new UID, stores it, and returns it.

        Parameters
        ----------
        specimen_id : str
            Specimen/sample identifier

        Returns
        -------
        str
            DICOM UID for the specimen
        """
        specimen_id = specimen_id.strip()

        if specimen_id in self._specimen_cache:
            return self._specimen_cache[specimen_id]

        uid = self.generate_new_uid()
        self._specimen_cache[specimen_id] = uid
        self._save_to_csv(self.specimen_map_file, specimen_id, uid)

        return uid

    def get_or_create_study_uid(self, study_id: str) -> str:
        """
        Get existing or create new StudyInstanceUID for study identifier.

        The study_id is typically the patient_id, ensuring all slides
        from the same patient belong to the same DICOM Study.

        Parameters
        ----------
        study_id : str
            Study identifier (typically patient_id)

        Returns
        -------
        str
            DICOM StudyInstanceUID
        """
        study_id = study_id.strip()

        if study_id in self._study_uid_cache:
            return self._study_uid_cache[study_id]

        uid = self.generate_new_uid()
        self._study_uid_cache[study_id] = uid
        self._save_to_csv(self.study_uid_map_file, study_id, uid)

        return uid

    def get_or_set_study_datetime(
        self,
        study_id: str,
        datetime_str: Optional[str] = None
    ) -> Optional[str]:
        """
        Get existing or set new study datetime.

        Ensures all series in a study have the same StudyDate/StudyTime.
        If no datetime is provided and none exists, generates current datetime.

        Parameters
        ----------
        study_id : str
            Study identifier
        datetime_str : str, optional
            Datetime string to set if not exists (format: YYYYMMDDHHMMSS)

        Returns
        -------
        str or None
            Study datetime string in DICOM format
        """
        if not self.study_datetime_map_file:
            return datetime_str

        study_id = study_id.strip()

        if study_id in self._study_datetime_cache:
            return self._study_datetime_cache[study_id]

        # If no datetime provided, use current datetime
        if not datetime_str:
            datetime_str = datetime.now().strftime("%Y%m%d%H%M%S")

        self._study_datetime_cache[study_id] = datetime_str
        self._save_to_csv(self.study_datetime_map_file, study_id, datetime_str)

        return datetime_str

    def has_specimen_uid(self, specimen_id: str) -> bool:
        """
        Check if specimen already has a UID mapping.

        Parameters
        ----------
        specimen_id : str
            Specimen/sample identifier

        Returns
        -------
        bool
            True if mapping exists
        """
        return specimen_id.strip() in self._specimen_cache

    def has_study_uid(self, study_id: str) -> bool:
        """
        Check if study already has a UID mapping.

        Parameters
        ----------
        study_id : str
            Study identifier

        Returns
        -------
        bool
            True if mapping exists
        """
        return study_id.strip() in self._study_uid_cache

    def get_specimen_uid(self, specimen_id: str) -> Optional[str]:
        """
        Get existing specimen UID without creating new one.

        Parameters
        ----------
        specimen_id : str
            Specimen/sample identifier

        Returns
        -------
        str or None
            Existing UID or None if not found
        """
        return self._specimen_cache.get(specimen_id.strip())

    def get_study_uid(self, study_id: str) -> Optional[str]:
        """
        Get existing study UID without creating new one.

        Parameters
        ----------
        study_id : str
            Study identifier

        Returns
        -------
        str or None
            Existing UID or None if not found
        """
        return self._study_uid_cache.get(study_id.strip())

    def reload(self) -> None:
        """Reload mappings from CSV files."""
        self._load_mappings()

    @property
    def specimen_count(self) -> int:
        """Number of specimen mappings."""
        return len(self._specimen_cache)

    @property
    def study_count(self) -> int:
        """Number of study mappings."""
        return len(self._study_uid_cache)
