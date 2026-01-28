"""
UID registry for persistent DICOM UID management.

Uses SQLite to store and reuse StudyInstanceUID, SpecimenUID, and study datetime
across conversion runs. Generates DICOM-compliant 2.25 UIDs via pydicom.
"""

import sqlite3
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime
import threading
from pydicom.uid import generate_uid


class UIDRegistry:
    """SQLite-backed registry for DICOM UIDs and study datetimes."""
    
    def __init__(self, db_path: str = "uid_registry.db"):
        """
        Initialize UID registry.
        
        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._init_db()
    
    def _init_db(self):
        """Create database schema if not exists."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS studies (
                    dataset TEXT NOT NULL,
                    patient_id TEXT NOT NULL,
                    study_instance_uid TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (dataset, patient_id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS specimens (
                    dataset TEXT NOT NULL,
                    specimen_id TEXT NOT NULL,
                    specimen_uid TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (dataset, specimen_id)
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS study_datetimes (
                    dataset TEXT NOT NULL,
                    study_id TEXT NOT NULL,
                    study_datetime TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (dataset, study_id)
                )
            """)
            
            conn.commit()
    
    def get_or_create_study_uid(
        self,
        patient_id: str,
        dataset: str = "CCDI"
    ) -> str:
        """
        Get existing StudyInstanceUID or generate new one.
        
        Args:
            patient_id: Patient identifier (e.g., PBCPZR)
            dataset: Dataset identifier for namespacing
            
        Returns:
            DICOM StudyInstanceUID (2.25 format)
        """
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT study_instance_uid FROM studies WHERE dataset = ? AND patient_id = ?",
                    (dataset, patient_id)
                )
                row = cursor.fetchone()
                
                if row:
                    return row[0]
                
                # Generate new UID using pydicom (2.25 format)
                study_uid = generate_uid()
                
                conn.execute(
                    "INSERT INTO studies (dataset, patient_id, study_instance_uid, created_at) VALUES (?, ?, ?, ?)",
                    (dataset, patient_id, study_uid, datetime.utcnow().isoformat())
                )
                conn.commit()
                
                return study_uid
    
    def get_or_create_specimen_uid(
        self,
        specimen_id: str,
        dataset: str = "CCDI"
    ) -> str:
        """
        Get existing SpecimenUID or generate new one.
        
        Args:
            specimen_id: Specimen identifier (e.g., 0DX2D2)
            dataset: Dataset identifier for namespacing
            
        Returns:
            DICOM SpecimenUID (2.25 format)
        """
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT specimen_uid FROM specimens WHERE dataset = ? AND specimen_id = ?",
                    (dataset, specimen_id)
                )
                row = cursor.fetchone()
                
                if row:
                    return row[0]
                
                # Generate new UID using pydicom (2.25 format)
                specimen_uid = generate_uid()
                
                conn.execute(
                    "INSERT INTO specimens (dataset, specimen_id, specimen_uid, created_at) VALUES (?, ?, ?, ?)",
                    (dataset, specimen_id, specimen_uid, datetime.utcnow().isoformat())
                )
                conn.commit()
                
                return specimen_uid
    
    def get_or_create_study_datetime(
        self,
        study_id: str,
        study_datetime: Optional[datetime] = None,
        dataset: str = "CCDI"
    ) -> datetime:
        """
        Get existing study datetime or store new one.
        
        Ensures consistent study datetime across all series in a study.
        
        Args:
            study_id: Study identifier (typically patient_id for CCDI)
            study_datetime: Datetime to store (from TIFF header or fallback)
            dataset: Dataset identifier for namespacing
            
        Returns:
            Study datetime (existing or newly stored)
        """
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT study_datetime FROM study_datetimes WHERE dataset = ? AND study_id = ?",
                    (dataset, study_id)
                )
                row = cursor.fetchone()
                
                if row:
                    return datetime.fromisoformat(row[0])
                
                # Use provided datetime or fallback to now
                if study_datetime is None:
                    study_datetime = datetime.now()
                
                conn.execute(
                    "INSERT INTO study_datetimes (dataset, study_id, study_datetime, created_at) VALUES (?, ?, ?, ?)",
                    (dataset, study_id, study_datetime.isoformat(), datetime.utcnow().isoformat())
                )
                conn.commit()
                
                return study_datetime
    
    def list_studies(self, dataset: Optional[str] = None) -> list:
        """List all registered studies."""
        with sqlite3.connect(self.db_path) as conn:
            if dataset:
                cursor = conn.execute(
                    "SELECT dataset, patient_id, study_instance_uid, created_at FROM studies WHERE dataset = ?",
                    (dataset,)
                )
            else:
                cursor = conn.execute(
                    "SELECT dataset, patient_id, study_instance_uid, created_at FROM studies"
                )
            
            return cursor.fetchall()
    
    def list_specimens(self, dataset: Optional[str] = None) -> list:
        """List all registered specimens."""
        with sqlite3.connect(self.db_path) as conn:
            if dataset:
                cursor = conn.execute(
                    "SELECT dataset, specimen_id, specimen_uid, created_at FROM specimens WHERE dataset = ?",
                    (dataset,)
                )
            else:
                cursor = conn.execute(
                    "SELECT dataset, specimen_id, specimen_uid, created_at FROM specimens"
                )
            
            return cursor.fetchall()


if __name__ == "__main__":
    # Test UID generation
    registry = UIDRegistry("test_uid_registry.db")
    
    # Test study UID persistence
    uid1 = registry.get_or_create_study_uid("PBCPZR", "CCDI")
    uid2 = registry.get_or_create_study_uid("PBCPZR", "CCDI")
    assert uid1 == uid2, "Study UID should be reused"
    print(f"StudyInstanceUID for PBCPZR: {uid1}")
    
    # Test specimen UID persistence
    spec_uid1 = registry.get_or_create_specimen_uid("0DX2D2", "CCDI")
    spec_uid2 = registry.get_or_create_specimen_uid("0DX2D2", "CCDI")
    assert spec_uid1 == spec_uid2, "Specimen UID should be reused"
    print(f"SpecimenUID for 0DX2D2: {spec_uid1}")
    
    # Test study datetime
    dt1 = registry.get_or_create_study_datetime("PBCPZR", datetime(2024, 1, 15, 10, 30), "CCDI")
    dt2 = registry.get_or_create_study_datetime("PBCPZR", None, "CCDI")
    assert dt1 == dt2, "Study datetime should be reused"
    print(f"Study datetime for PBCPZR: {dt1}")
    
    # List all
    print(f"\nAll studies: {registry.list_studies()}")
    print(f"All specimens: {registry.list_specimens()}")
    
    # Cleanup test
    Path("test_uid_registry.db").unlink()
    print("\nUID registry tests passed!")
