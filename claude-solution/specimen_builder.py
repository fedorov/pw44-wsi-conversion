"""
Specimen Metadata Builder Module

Constructs wsidicom Specimen and preparation step objects
from CSV metadata.
"""

from typing import Optional, List
from pydicom.sr.coding import Code

try:
    from .code_mapper import DicomCodeMapper, CodedConcept
except ImportError:
    from code_mapper import DicomCodeMapper, CodedConcept


class SpecimenMetadataBuilder:
    """
    Builds specimen preparation metadata for wsidicom.

    Constructs the specimen hierarchy with fixation, embedding,
    and staining preparation steps based on CSV metadata values.

    This builder creates the preparation step objects that can be
    used with wsidicom's Specimen and SlideSample classes.
    """

    def __init__(self, code_mapper: DicomCodeMapper):
        """
        Initialize builder.

        Parameters
        ----------
        code_mapper : DicomCodeMapper
            Code mapper for translating metadata values to DICOM codes
        """
        self.code_mapper = code_mapper

    def build_fixation_code(self, fixation_method: Optional[str]) -> Optional[Code]:
        """
        Build fixation code from fixation method.

        Parameters
        ----------
        fixation_method : str, optional
            Fixation method (e.g., "FFPE", "OCT", "Formalin")

        Returns
        -------
        Code or None
            pydicom Code for the fixative
        """
        if not fixation_method:
            return None

        fixative_code, _ = self.code_mapper.map_fixation_to_codes(fixation_method)
        if fixative_code:
            return Code(
                value=fixative_code.value,
                scheme_designator=fixative_code.scheme,
                meaning=fixative_code.meaning
            )
        return None

    def build_embedding_code(self, fixation_method: Optional[str]) -> Optional[Code]:
        """
        Build embedding code from fixation method.

        Parameters
        ----------
        fixation_method : str, optional
            Fixation/embedding method (e.g., "FFPE" includes paraffin embedding)

        Returns
        -------
        Code or None
            pydicom Code for the embedding medium
        """
        if not fixation_method:
            return None

        _, embedding_code = self.code_mapper.map_fixation_to_codes(fixation_method)
        if embedding_code:
            return Code(
                value=embedding_code.value,
                scheme_designator=embedding_code.scheme,
                meaning=embedding_code.meaning
            )
        return None

    def build_staining_codes(self, staining_method: Optional[str]) -> List[Code]:
        """
        Build staining codes from staining method.

        Parameters
        ----------
        staining_method : str, optional
            Staining method (e.g., "H&E", "IHC")

        Returns
        -------
        List[Code]
            List of pydicom Codes for the staining substances
        """
        if not staining_method:
            return []

        stain_codes = self.code_mapper.map_staining_to_codes(staining_method)
        return [
            Code(
                value=code.value,
                scheme_designator=code.scheme,
                meaning=code.meaning
            )
            for code in stain_codes
        ]

    def build_anatomy_code(self, anatomic_site: Optional[str]) -> Optional[Code]:
        """
        Build anatomy SNOMED code from anatomic site.

        Parameters
        ----------
        anatomic_site : str, optional
            Anatomic site (e.g., "C71.7 : Brain stem")

        Returns
        -------
        Code or None
            pydicom Code for the anatomy
        """
        if not anatomic_site:
            return None

        anatomy_code = self.code_mapper.map_anatomy_to_snomed(anatomic_site)
        if anatomy_code:
            return Code(
                value=anatomy_code.value,
                scheme_designator=anatomy_code.scheme,
                meaning=anatomy_code.meaning
            )
        return None

    def build_short_description(
        self,
        fixation_method: Optional[str],
        staining_method: Optional[str],
        tumor_status: Optional[str]
    ) -> str:
        """
        Build specimen short description from preparation info.

        Creates an abbreviated description like "FF PE HE T" for
        Formalin Fixed, Paraffin Embedded, H&E stained, Tumor.

        Parameters
        ----------
        fixation_method : str, optional
            Fixation method
        staining_method : str, optional
            Staining method
        tumor_status : str, optional
            Tumor status (e.g., "Tumor", "Normal")

        Returns
        -------
        str
            Short description (max 64 characters per DICOM spec)
        """
        parts = []

        # Fixation abbreviation
        fix_abbrev = self.code_mapper.get_fixation_abbreviation(fixation_method)
        if fix_abbrev:
            parts.append(fix_abbrev)

        # Embedding abbreviation (for FFPE, add PE)
        embed_abbrev = self.code_mapper.get_embedding_abbreviation(fixation_method)
        if embed_abbrev:
            parts.append(embed_abbrev)

        # Staining abbreviation
        stain_abbrev = self.code_mapper.get_staining_abbreviation(staining_method)
        if stain_abbrev:
            parts.append(stain_abbrev)

        # Tumor status abbreviation
        tumor_abbrev = self.code_mapper.get_tissue_type_abbreviation(tumor_status)
        if tumor_abbrev:
            parts.append(tumor_abbrev)

        description = " ".join(parts)

        # Ensure max 64 characters
        return description[:64] if description else ""

    def get_fixation_type_for_wsidicom(self, fixation_method: Optional[str]) -> Optional[str]:
        """
        Get fixation type string that wsidicom recognizes.

        wsidicom's SpecimenFixativesCode uses CID 8114 meanings.
        This method returns the appropriate meaning string.

        Parameters
        ----------
        fixation_method : str, optional
            Fixation method from CSV

        Returns
        -------
        str or None
            Fixation type meaning for SpecimenFixativesCode
        """
        if not fixation_method:
            return None

        # Map to CID 8114 meanings
        fixation_mappings = {
            "FFPE": "Neutral Buffered Formalin",
            "Formalin fixed paraffin embedded (FFPE)": "Neutral Buffered Formalin",
            "Formalin-Fixed Paraffin-Embedded": "Neutral Buffered Formalin",
            "Formalin": "Formalin",
            "10% Neutral Buffered Formalin": "Neutral Buffered Formalin",
            "OCT": None,  # OCT is a freezing medium, not a fixative
            "Optimal Cutting Temperature": None,
            "Frozen": None,
        }

        return fixation_mappings.get(fixation_method)

    def get_embedding_type_for_wsidicom(self, fixation_method: Optional[str]) -> Optional[str]:
        """
        Get embedding type string that wsidicom recognizes.

        wsidicom's SpecimenEmbeddingMediaCode uses CID 8115 meanings.
        This method returns the appropriate meaning string.

        Parameters
        ----------
        fixation_method : str, optional
            Fixation/embedding method from CSV

        Returns
        -------
        str or None
            Embedding type meaning for SpecimenEmbeddingMediaCode
        """
        if not fixation_method:
            return None

        # Map to CID 8115 meanings
        embedding_mappings = {
            "FFPE": "Paraffin wax",
            "Formalin fixed paraffin embedded (FFPE)": "Paraffin wax",
            "Formalin-Fixed Paraffin-Embedded": "Paraffin wax",
            "Paraffin": "Paraffin wax",
            "OCT": "OCT medium",
            "Optimal Cutting Temperature": "OCT medium",
        }

        return embedding_mappings.get(fixation_method)

    def get_staining_substances_for_wsidicom(
        self,
        staining_method: Optional[str]
    ) -> Optional[List[str]]:
        """
        Get staining substance strings that wsidicom recognizes.

        wsidicom's SpecimenStainsCode uses CID 8112 meanings.
        This method returns the appropriate meaning strings.

        Parameters
        ----------
        staining_method : str, optional
            Staining method from CSV

        Returns
        -------
        List[str] or None
            Staining substance meanings for SpecimenStainsCode
        """
        if not staining_method:
            return None

        # Map to CID 8112 meanings
        staining_mappings = {
            "H&E": ["hematoxylin stain", "water soluble eosin stain"],
            "Hematoxylin and Eosin Staining Method": ["hematoxylin stain", "water soluble eosin stain"],
            "HE": ["hematoxylin stain", "water soluble eosin stain"],
        }

        return staining_mappings.get(staining_method)

    def coded_concept_to_code(self, concept: CodedConcept) -> Code:
        """
        Convert CodedConcept to pydicom Code.

        Parameters
        ----------
        concept : CodedConcept
            Coded concept from code_mapper

        Returns
        -------
        Code
            pydicom Code object
        """
        return Code(
            value=concept.value,
            scheme_designator=concept.scheme,
            meaning=concept.meaning
        )
