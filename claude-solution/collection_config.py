"""
Collection Configuration Module

Contains collection-specific configuration for DICOM attributes including
clinical trial information, sponsor details, and protocol identifiers.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class CollectionConfig:
    """
    Collection-specific configuration for DICOM attributes.

    Contains clinical trial and institutional information that
    varies by collection (e.g., MCI/CCDI, GTEx, CMB).

    Attributes
    ----------
    sponsor_name : str
        Clinical Trial Sponsor Name (max 64 chars)
    protocol_id : str
        Clinical Trial Protocol ID (e.g., phs002790)
    protocol_name : str
        Clinical Trial Protocol Name (max 64 chars)
    coordinating_center : str
        Clinical Trial Coordinating Center Name
    doi_protocol_id : str, optional
        DOI for the protocol (goes in OtherClinicalTrialProtocolIDsSequence)
    site_id : str
        Clinical Trial Site ID (often empty)
    site_name : str
        Clinical Trial Site Name (often empty)
    """
    sponsor_name: str
    protocol_id: str
    protocol_name: str
    coordinating_center: str
    doi_protocol_id: Optional[str] = None
    site_id: str = ""
    site_name: str = ""


# Pre-configured collection: MCI/CCDI (Childhood Cancer Data Initiative)
MCI_CCDI_CONFIG = CollectionConfig(
    sponsor_name="National Cancer Institute (NCI) Childhood Cancer Data Initiative",
    protocol_id="phs002790",
    protocol_name="CCDI Molecular Characterization Initiative",
    coordinating_center="Nationwide Children's Hospital",
    doi_protocol_id="doi:10.5281/zenodo.11099087"
)

# Pre-configured collection: GTEx (Genotype-Tissue Expression)
GTEX_CONFIG = CollectionConfig(
    sponsor_name="NIH Common Fund",
    protocol_id="phs000424",
    protocol_name="Genotype-Tissue Expression (GTEx)",
    coordinating_center="Broad Institute",
)

# Pre-configured collection: CMB (Cancer Model Biobank)
CMB_CONFIG = CollectionConfig(
    sponsor_name="Foundation Medicine",
    protocol_id="CMB",
    protocol_name="Cancer Model Biobank",
    coordinating_center="Foundation Medicine",
)

# Pre-configured collection: CPTAC (Clinical Proteomic Tumor Analysis Consortium)
CPTAC_CONFIG = CollectionConfig(
    sponsor_name="National Cancer Institute (NCI)",
    protocol_id="CPTAC",
    protocol_name="Clinical Proteomic Tumor Analysis Consortium",
    coordinating_center="National Cancer Institute",
)

# Pre-configured collection: TCGA (The Cancer Genome Atlas)
TCGA_CONFIG = CollectionConfig(
    sponsor_name="National Cancer Institute (NCI)",
    protocol_id="TCGA",
    protocol_name="The Cancer Genome Atlas",
    coordinating_center="National Cancer Institute",
)

# Pre-configured collection: HTAN (Human Tumor Atlas Network)
HTAN_CONFIG = CollectionConfig(
    sponsor_name="National Cancer Institute (NCI)",
    protocol_id="HTAN",
    protocol_name="Human Tumor Atlas Network",
    coordinating_center="National Cancer Institute",
)
