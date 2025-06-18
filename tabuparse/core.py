"""
Core orchestration module.

This module provides the main processing functions for:
- PDF extraction (pdf_extractor)
- Schema normalization (data_processor)
- Output generation (output_writer)
- Configuration handling (config_parser)

This serves as the primary API for both CLI and library usage.
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Union, Dict, Any

import pandas as pd

from .config_parser import TabuparseConfig, parse_config, create_default_config, get_extraction_params_for_pdf
from .pdf_extractor import extract_tables_from_multiple_pdfs, validate_pdf_file
from .data_processor import normalize_and_merge_dataframes, clean_merged_dataframe
from .output_writer import write_output, export_summary_statistics

logger = logging.getLogger(__name__)


class TabuparseError(Exception):
    """Base exception for tabuparse processing errors."""
    pass


async def process_pdfs(
    pdf_paths: List[str],
    config_path: Optional[str] = None,
    output_path: Optional[str] = None,
    output_format: str = "csv",
    max_concurrent: int = 5,
    export_summary: bool = False,
    clean_data: bool = True
) -> pd.DataFrame:
    """
    Main function to process PDF files and extract tabular data.

    This function coordinates the entire pipeline:
    1. Load configuration
    2. Validate PDF files
    3. Extract tables from PDFs concurrently
    4. Normalize schemas and merge data
    5. Export to specified format

    Args:
        pdf_paths: List of PDF file paths to process
        config_path: Path to TOML configuration file (optional)
        output_path: Path for output file (auto-generated if None)
        output_format: Output format ('csv' or 'sqlite')
        max_concurrent: Maximum concurrent PDF extractions
        export_summary: Whether to export summary statistics
        clean_data: Whether to clean the merged data

    Returns:
        Merged DataFrame containing all extracted data

    Raises:
        TabuparseError: If processing fails
    """
    logger.info(f"Starting tabuparse processing of {len(pdf_paths)} PDF files")

    try:
        config = await _load_configuration(config_path, output_format, output_path)

        valid_pdf_paths = await _validate_pdf_files(pdf_paths)

        if not valid_pdf_paths:
            raise TabuparseError("No valid PDF files found")

        extraction_results = await _extract_tables_from_pdfs(
            valid_pdf_paths, config, max_concurrent
        )

        merged_df = await _normalize_and_merge_data(extraction_results, config)

        if clean_data and not merged_df.empty:
            merged_df = clean_merged_dataframe(merged_df)

        if output_path or config.output_path:
            final_output_path = output_path or config.output_path
            actual_output_path = write_output(
                merged_df,
                final_output_path,
                config.output_format
            )
            logger.info(f"Results exported to: {actual_output_path}")

            if export_summary:
                summary_path = Path(actual_output_path).with_suffix('.summary.txt')
                export_summary_statistics(merged_df, summary_path)

        logger.info(f"Processing complete: {merged_df.shape[0]} rows, {merged_df.shape[1]} columns")
        return merged_df

    except Exception as e:
        logger.error(f"Processing failed: {e}")
        raise TabuparseError(f"Failed to process PDFs: {e}") from e


async def _load_configuration(
    config_path: Optional[str],
    output_format: str,
    output_path: Optional[str]
) -> TabuparseConfig:
    """Load and validate configuration."""
    if config_path:
        logger.info(f"Loading configuration from: {config_path}")
        config = parse_config(config_path)
    else:
        logger.info("Using default configuration")
        config = create_default_config()

    # Override config with explicit parameters
    if output_format != "csv":  # csv is default
        config.output_format = output_format

    if output_path:
        config.output_path = output_path

    logger.debug(f"Configuration loaded: {len(config.expected_columns)} expected columns")
    return config


async def _validate_pdf_files(pdf_paths: List[str]) -> List[str]:
    """Validate PDF files and return list of valid paths."""
    logger.info(f"Validating {len(pdf_paths)} PDF files")

    valid_paths = []
    validation_tasks = []

    # Create validation tasks
    for pdf_path in pdf_paths:
        task = asyncio.to_thread(validate_pdf_file, pdf_path)
        validation_tasks.append((pdf_path, task))

    # Execute validations concurrently
    for pdf_path, task in validation_tasks:
        try:
            is_valid = await task
            if is_valid:
                valid_paths.append(pdf_path)
            else:
                logger.warning(f"Skipping invalid PDF: {pdf_path}")
        except Exception as e:
            logger.error(f"Validation failed for {pdf_path}: {e}")
            continue

    logger.info(f"Validated {len(valid_paths)}/{len(pdf_paths)} PDF files")
    return valid_paths


async def _extract_tables_from_pdfs(
    pdf_paths: List[str],
    config: TabuparseConfig,
    max_concurrent: int
) -> Dict[str, List[pd.DataFrame]]:
    """Extract tables from PDF files using configuration."""

    logger.info(f"Extracting tables from {len(pdf_paths)} PDFs")

    # Build extraction parameters map
    extraction_params_map = {}
    for pdf_path in pdf_paths:
        params = get_extraction_params_for_pdf(config, pdf_path)
        extraction_params_map[pdf_path] = params

    extraction_results = await extract_tables_from_multiple_pdfs(
        pdf_paths,
        extraction_params_map,
        config.default_extraction,
        max_concurrent
    )

    total_tables = sum(len(tables) for tables in extraction_results.values())
    logger.info(f"Extraction complete: {total_tables} tables extracted")

    return extraction_results


async def _normalize_and_merge_data(
    extraction_results: Dict[str, List[pd.DataFrame]],
    config: TabuparseConfig
) -> pd.DataFrame:
    """Normalize schemas and merge all extracted data."""

    logger.info("Starting schema normalization and data merging")

    dataframes_with_sources = []

    for pdf_path, dataframes in extraction_results.items():
        pdf_name = Path(pdf_path).name

        for i, df in enumerate(dataframes):
            if not df.empty:
                source_id = f"{pdf_name}_table_{i+1}" if len(dataframes) > 1 else pdf_name
                dataframes_with_sources.append((df, source_id))

    logger.info(f"Normalizing {len(dataframes_with_sources)} DataFrames")

    # Normalize and merge
    if config.expected_columns:
        merged_df = normalize_and_merge_dataframes(
            dataframes_with_sources,
            config.expected_columns,
            config.strict_schema,
            add_source_column=True
        )
    else:
        # No schema normalization - just merge as-is
        logger.warning("No expected columns configured - merging without schema normalization")
        dfs_only = [df for df, _ in dataframes_with_sources]

        if dfs_only:
            # Add source column manually
            for i, (df, source) in enumerate(dataframes_with_sources):
                dfs_only[i] = df.copy()
                dfs_only[i]['source_file'] = source

            merged_df = pd.concat(dfs_only, ignore_index=True)
        else:
            merged_df = pd.DataFrame()

    logger.info(f"Merge complete: {merged_df.shape}")

    return merged_df


async def extract_from_single_pdf(
    pdf_path: str,
    config_path: Optional[str] = None,
    expected_columns: Optional[List[str]] = None
) -> List[pd.DataFrame]:
    """
    Extract and normalize tables from a single PDF file.

    This is a convenience function for processing individual PDFs.

    Args:
        pdf_path: Path to the PDF file
        config_path: Path to configuration file (optional)
        expected_columns: List of expected column names (optional)

    Returns:
        List of normalized DataFrames

    Raises:
        TabuparseError: If extraction fails
    """
    try:

        if config_path:
            config = parse_config(config_path)
        else:
            config = create_default_config()
            if expected_columns:
                config.expected_columns = expected_columns

        extraction_params = get_extraction_params_for_pdf(config, pdf_path)
        from .pdf_extractor import extract_tables_from_pdf
        tables = await extract_tables_from_pdf(pdf_path, extraction_params)

        if config.expected_columns:
            from .data_processor import normalize_schema
            normalized_tables = []

            for table in tables:
                normalized_table = normalize_schema(
                    table,
                    config.expected_columns,
                    config.strict_schema
                )
                normalized_tables.append(normalized_table)

            return normalized_tables

        return tables

    except Exception as e:
        raise TabuparseError(f"Failed to extract from {pdf_path}: {e}") from e


def configure_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    include_timestamp: bool = True
) -> None:
    """
    Configure logging.

    Args:
        level: Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        log_file: Path to log file (optional, logs to console if None)
        include_timestamp: Whether to include timestamps in log messages
    """

    if include_timestamp:
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    else:
        formatter = logging.Formatter(
            '%(name)s - %(levelname)s - %(message)s'
        )

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    root_logger = logging.getLogger('tabuparse')
    root_logger.setLevel(numeric_level)

    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    logger.info(f"Logging configured: level={level}, file={log_file}")


async def get_processing_statistics(
    pdf_paths: List[str],
    config_path: Optional[str] = None
) -> Dict[str, Any]:
    """
    Get statistics about what would be processed without actually processing.

    This is useful for previewing processing operations.

    Args:
        pdf_paths: List of PDF file paths
        config_path: Path to configuration file

    Returns:
        Dictionary with processing statistics
    """
    try:
        config = await _load_configuration(config_path, "csv", None)
        valid_pdfs = await _validate_pdf_files(pdf_paths)

        pdf_info = {}
        for pdf_path in valid_pdfs[:5]:  # Limit to first 5 for performance
            try:
                from .pdf_extractor import get_pdf_info
                info = await asyncio.to_thread(get_pdf_info, pdf_path)
                pdf_info[pdf_path] = info
            except Exception as e:
                pdf_info[pdf_path] = {'error': str(e)}

        stats = {
            'total_pdfs': len(pdf_paths),
            'valid_pdfs': len(valid_pdfs),
            'invalid_pdfs': len(pdf_paths) - len(valid_pdfs),
            'expected_columns': config.expected_columns,
            'expected_column_count': len(config.expected_columns),
            'extraction_parameters_count': len(config.extraction_parameters),
            'output_format': config.output_format,
            'strict_schema': config.strict_schema,
            'sample_pdf_info': pdf_info,
        }

        return stats

    except Exception as e:
        return {'error': str(e)}
