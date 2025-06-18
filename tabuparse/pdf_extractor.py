"""
PDF table extraction.

This module handles extracting tabular data from PDF files using camelot-py.
It also provides asynchronous processing capabilities and error handling.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional, Dict, Any

import pandas as pd

try:
    import camelot
except ImportError:
    raise ImportError(
        "camelot-py is required for PDF extraction. "
        "Install it with: pip install camelot-py[base]"
    )

from .config_parser import ExtractionParameters

logger = logging.getLogger(__name__)


class PDFExtractionError(Exception):
    """Custom exception for PDF extraction errors."""
    pass


async def extract_tables_from_pdf(
    pdf_path: str,
    extraction_params: Optional[ExtractionParameters] = None
) -> List[pd.DataFrame]:
    """
    Extract tables from a PDF file asynchronously.

    Args:
        pdf_path: Path to the PDF file
        extraction_params: Parameters for table extraction

    Returns:
        List of pandas DataFrames containing extracted tables

    Raises:
        PDFExtractionError: If extraction fails
        FileNotFoundError: If PDF file doesn't exist
    """
    if extraction_params is None:
        extraction_params = ExtractionParameters()

    # Check PDF file exists
    pdf_file_path = Path(pdf_path)
    if not pdf_file_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    logger.info(f"Starting extraction from {pdf_path}")

    # Run extraction in thread pool to avoid blocking event loop
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        try:
            tables = await loop.run_in_executor(
                executor,
                _extract_tables_sync,
                str(pdf_file_path),
                extraction_params
            )
        except Exception as e:
            raise PDFExtractionError(f"Failed to extract tables from {pdf_path}: {e}") from e

    logger.info(f"Extracted {len(tables)} tables from {pdf_path}")
    return tables


def _extract_tables_sync(pdf_path: str, params: ExtractionParameters) -> List[pd.DataFrame]:
    """
    Synchronous table extraction.

    This function is designed to be run in a thread pool executor.
    """
    try:
        camelot_kwargs = _build_camelot_kwargs(params)
        tables = camelot.read_pdf(pdf_path, **camelot_kwargs)
        logger.debug(f"Camelot parameters for {pdf_path}: {camelot_kwargs}")

        if not tables:
            logger.warning(f"No tables found in {pdf_path}")
            return []

        # Convert tables to DataFrames
        dataframes = []
        for i, table in enumerate(tables):
            try:
                df = table.df

                # Drop completely empty rows and columns
                df = _clean_dataframe(df)

                if not df.empty:
                    logger.debug(f"Table {i+1} from {pdf_path}: shape {df.shape}")
                    dataframes.append(df)
                else:
                    logger.debug(f"Table {i+1} from {pdf_path} is empty after cleanup")

            except Exception as e:
                logger.warning(f"Failed to process table {i+1} from {pdf_path}: {e}")
                continue

        return dataframes

    except Exception as e:
        logger.error(f"Camelot extraction failed for {pdf_path}: {e}")
        raise


def _build_camelot_kwargs(params: ExtractionParameters) -> Dict[str, Any]:
    """Build keyword arguments for camelot.read_pdf from ExtractionParameters."""
    kwargs = {
        "pages": params.pages,
        "flavor": params.flavor,
    }

    # Add optional parameters if they're set
    if params.table_areas:
        kwargs["table_areas"] = params.table_areas

    if params.columns:
        kwargs["columns"] = params.columns

    # Flavor-specific parameters
    if params.flavor == "lattice":
        if hasattr(params, 'process_background') and params.process_background is not None:
            kwargs["process_background"] = params.process_background
        if hasattr(params, 'line_scale') and params.line_scale is not None:
            kwargs["line_scale"] = params.line_scale

    elif params.flavor == "stream":
        kwargs["row_tol"] = params.row_tol
        kwargs["column_tol"] = params.column_tol

        if params.split_text:
            kwargs["split_text"] = params.split_text
        if params.flag_size:
            kwargs["flag_size"] = params.flag_size
        if params.strip_text:
            kwargs["strip_text"] = params.strip_text

    return kwargs


def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean extracted DataFrame by removing empty rows and columns.

    Args:
        df: Raw DataFrame from table extraction

    Returns:
        Cleaned DataFrame
    """
    if df.empty:
        return df

    # Remove rows that are completely empty or contain only whitespace
    df = df.dropna(how='all')
    df = df[~df.apply(lambda row: row.astype(str).str.strip().eq('').all(), axis=1)]

    # Same with columns
    df = df.dropna(axis=1, how='all')
    for col in df.columns:
        if df[col].astype(str).str.strip().eq('').all():
            df = df.drop(columns=[col])

    # Strip whitespace from all string values
    for col in df.columns:
        if df[col].dtype == 'object':
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace('', pd.NA) # Replace empty strings with NaN

    return df


async def extract_tables_from_multiple_pdfs(
    pdf_paths: List[str],
    extraction_params_map: Optional[Dict[str, ExtractionParameters]] = None,
    default_params: Optional[ExtractionParameters] = None,
    max_concurrent: int = 5
) -> Dict[str, List[pd.DataFrame]]:
    """
    Extract tables from multiple PDF files concurrently.

    Args:
        pdf_paths: List of PDF file paths
        extraction_params_map: Mapping of PDF paths to their extraction parameters
        default_params: Default extraction parameters for PDFs not in the map
        max_concurrent: Maximum number of concurrent extractions

    Returns:
        Dictionary mapping PDF paths to lists of extracted DataFrames

    Raises:
        PDFExtractionError: If any extraction fails critically
    """
    if extraction_params_map is None:
        extraction_params_map = {}

    if default_params is None:
        default_params = ExtractionParameters()

    # Create semaphore to limit concurrent extractions
    semaphore = asyncio.Semaphore(max_concurrent)

    async def extract_with_semaphore(pdf_path: str) -> tuple[str, List[pd.DataFrame]]:
        async with semaphore:
            params = extraction_params_map.get(pdf_path, default_params)
            try:
                tables = await extract_tables_from_pdf(pdf_path, params)
                return pdf_path, tables
            except Exception as e:
                logger.error(f"Failed to extract from {pdf_path}: {e}")
                return pdf_path, [] # Fail gracefully by returning an empty list

    logger.info(f"Starting concurrent extraction from {len(pdf_paths)} PDF files")

    # Execute extractions concurrently
    tasks = [extract_with_semaphore(pdf_path) for pdf_path in pdf_paths]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    extraction_results = {}
    failed_extractions = []

    for result in results:
        if isinstance(result, Exception):
            logger.error(f"Extraction task failed: {result}")
            failed_extractions.append(str(result))
            continue

        pdf_path, tables = result
        extraction_results[pdf_path] = tables

    total_tables = sum(len(tables) for tables in extraction_results.values())
    logger.info(f"Completed extraction: {total_tables} tables from {len(extraction_results)} PDFs")

    if failed_extractions:
        logger.warning(f"{len(failed_extractions)} extractions had errors")

    return extraction_results


def validate_pdf_file(pdf_path: str) -> bool:
    """
    Validate that a file exists and appears to be a PDF.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        True if file appears to be a valid PDF, False otherwise
    """
    try:
        pdf_file = Path(pdf_path)

        if not pdf_file.exists():
            logger.error(f"PDF file does not exist: {pdf_path}")
            return False

        if not pdf_file.is_file():
            logger.error(f"Path is not a file: {pdf_path}")
            return False

        if pdf_file.suffix.lower() != '.pdf':
            logger.warning(f"File does not have .pdf extension: {pdf_path}")

        # PDF header check
        try:
            with open(pdf_file, 'rb') as f:
                header = f.read(5)
                if not header.startswith(b'%PDF-'):
                    logger.warning(f"File does not appear to be a PDF: {pdf_path}")
                    return False
        except Exception as e:
            logger.error(f"Cannot read PDF file {pdf_path}: {e}")
            return False

        return True

    except Exception as e:
        logger.error(f"Error validating PDF file {pdf_path}: {e}")
        return False


def get_pdf_info(pdf_path: str) -> Dict[str, Any]:
    """
    Get basic PDF file information.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Dictionary with PDF information
    """
    try:
        # This is a simple approach - camelot doesn't expose much PDF metadata
        # but we can try to extract from the first page to get basic info
        tables = camelot.read_pdf(pdf_path, pages='1', flavor='lattice')

        info = {
            'path': pdf_path,
            'exists': True,
            'readable': True,
            'tables_found_on_first_page': len(tables),
        }

        if tables:
            first_table = tables[0]
            info.update({
                'first_table_shape': first_table.df.shape,
                'first_table_accuracy': getattr(first_table, 'accuracy', 'unknown'),
                'first_table_whitespace': getattr(first_table, 'whitespace', 'unknown'),
            })

        return info

    except Exception as e:
        return {
            'path': pdf_path,
            'exists': Path(pdf_path).exists(),
            'readable': False,
            'error': str(e),
        }
