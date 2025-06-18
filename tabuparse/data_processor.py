"""
Data processing module for tabuparse.

This module handles schema normalization and data merging operations:
- Normalizing extracted DataFrames against expected column schemas
- Merging multiple DataFrames into a single consolidated dataset
- Column matching, renaming, and ordering operations
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
import re

import pandas as pd
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class SchemaNormalizationError(Exception):
    """Custom exception for schema normalization errors."""
    pass


def normalize_schema(
    df: pd.DataFrame,
    expected_columns: List[str],
    strict_mode: bool = False,
    fuzzy_threshold: float = 0.8
) -> pd.DataFrame:
    """
    Normalize a DataFrame schema against expected columns.

    This function:
    1. Matches extracted columns to expected columns (case-insensitive, fuzzy matching)
    2. Renames matched columns to expected names
    3. Drops columns not in expected_columns
    4. Adds missing expected columns with NaN values
    5. Reorders columns to match expected_columns sequence

    Args:
        df: Input DataFrame to normalize
        expected_columns: List of expected column names
        strict_mode: If True, raises errors on schema mismatches
        fuzzy_threshold: Threshold for fuzzy string matching (0.0-1.0)

    Returns:
        Normalized DataFrame with expected schema

    Raises:
        SchemaNormalizationError: If strict_mode is True and schema issues occur
    """
    if df.empty:
        logger.warning("Attempting to normalize empty DataFrame")
        return _create_empty_dataframe_with_schema(expected_columns)

    if not expected_columns:
        logger.warning("No expected columns provided - returning original DataFrame")
        return df.copy()

    logger.debug(f"Normalizing DataFrame with shape {df.shape} against {len(expected_columns)} expected columns")

    # Step 1: Create column mapping
    column_mapping = _create_column_mapping(
        df.columns.tolist(),
        expected_columns,
        fuzzy_threshold
    )

    # Step 2: Log column mapping results
    _log_column_mapping_results(column_mapping, df.columns.tolist(), expected_columns)

    # Step 3: Handle strict mode validation
    if strict_mode:
        _validate_strict_schema(column_mapping, df.columns.tolist(), expected_columns)

    # Step 4: Apply column mapping and normalization
    normalized_df = _apply_column_normalization(df, column_mapping, expected_columns)

    logger.info(f"Schema normalization complete: {df.shape} -> {normalized_df.shape}")
    return normalized_df


def _create_column_mapping(
    actual_columns: List[str],
    expected_columns: List[str],
    fuzzy_threshold: float
) -> Dict[str, Optional[str]]:
    """
    Create a mapping from actual columns to expected columns.

    Returns a dictionary where:
    - Keys are actual column names
    - Values are expected column names (or None if no match)
    """
    mapping = {}
    used_expected = set()

    # First pass: exact matches (case-insensitive)
    for actual_col in actual_columns:
        exact_match = None
        for expected_col in expected_columns:
            if expected_col not in used_expected and actual_col.lower() == expected_col.lower():
                exact_match = expected_col
                break

        if exact_match:
            mapping[actual_col] = exact_match
            used_expected.add(exact_match)
        else:
            mapping[actual_col] = None

    # Second pass: fuzzy matching for unmapped columns
    unmapped_actual = [col for col, match in mapping.items() if match is None]
    available_expected = [col for col in expected_columns if col not in used_expected]

    for actual_col in unmapped_actual:
        best_match = None
        best_score = 0

        for expected_col in available_expected:
            score = _calculate_similarity(actual_col, expected_col)
            if score >= fuzzy_threshold and score > best_score:
                best_match = expected_col
                best_score = score

        if best_match:
            mapping[actual_col] = best_match
            available_expected.remove(best_match)

    return mapping


def _calculate_similarity(str1: str, str2: str) -> float:
    """
    Calculate similarity between two strings using multiple methods.

    Combines:
    - Sequence matching
    - Normalized edit distance
    - Token-based matching (for multi-word columns)
    """
    str1_clean = _normalize_string_for_matching(str1)
    str2_clean = _normalize_string_for_matching(str2)

    # Basic sequence matching
    seq_ratio = SequenceMatcher(None, str1_clean, str2_clean).ratio()

    # Token-based matching for multi-word strings
    tokens1 = set(str1_clean.split())
    tokens2 = set(str2_clean.split())

    if tokens1 and tokens2:
        token_intersection = len(tokens1.intersection(tokens2))
        token_union = len(tokens1.union(tokens2))
        token_ratio = token_intersection / token_union if token_union > 0 else 0
    else:
        token_ratio = 0

    # Combine scores with weights
    combined_score = (seq_ratio * 0.7) + (token_ratio * 0.3)

    return combined_score


def _normalize_string_for_matching(s: str) -> str:
    """Normalize string for better matching (remove special chars, lowercase, etc.)."""
    # Convert to lowercase and remove extra whitespace
    s = s.lower().strip()

    # Replace common separators with spaces
    s = re.sub(r'[_\-\.\(\)\[\]]+', ' ', s)

    # Remove multiple spaces
    s = re.sub(r'\s+', ' ', s)

    return s


def _log_column_mapping_results(
    mapping: Dict[str, Optional[str]],
    actual_columns: List[str],
    expected_columns: List[str]
) -> None:
    """Log the results of column mapping for debugging."""
    matched = {k: v for k, v in mapping.items() if v is not None}
    unmatched_actual = [k for k, v in mapping.items() if v is None]
    matched_expected = set(matched.values())
    missing_expected = [col for col in expected_columns if col not in matched_expected]

    logger.info(f"Column mapping results:")
    logger.info(f"  Matched: {len(matched)}/{len(actual_columns)} actual columns")
    logger.info(f"  Unmatched actual: {unmatched_actual}")
    logger.info(f"  Missing expected: {missing_expected}")

    if matched:
        logger.debug("Column mappings:")
        for actual, expected in matched.items():
            logger.debug(f"  '{actual}' -> '{expected}'")


def _validate_strict_schema(
    mapping: Dict[str, Optional[str]],
    actual_columns: List[str],
    expected_columns: List[str]
) -> None:
    """Validate schema in strict mode - raise errors for mismatches."""
    unmatched_actual = [k for k, v in mapping.items() if v is None]
    matched_expected = {v for v in mapping.values() if v is not None}
    missing_expected = [col for col in expected_columns if col not in matched_expected]

    errors = []

    if unmatched_actual:
        errors.append(f"Unmatched actual columns: {unmatched_actual}")

    if missing_expected:
        errors.append(f"Missing expected columns: {missing_expected}")

    if errors:
        raise SchemaNormalizationError(
            f"Schema validation failed in strict mode: {'; '.join(errors)}"
        )


def _apply_column_normalization(
    df: pd.DataFrame,
    mapping: Dict[str, Optional[str]],
    expected_columns: List[str]
) -> pd.DataFrame:
    """Apply the column mapping and create normalized DataFrame."""

    result_df = df.copy() # Start with a copy of the original DF

    # Rename matched columns
    rename_dict = {k: v for k, v in mapping.items() if v is not None}
    if rename_dict:
        result_df = result_df.rename(columns=rename_dict)
        logger.debug(f"Renamed columns: {list(rename_dict.keys())} -> {list(rename_dict.values())}")

    # Drop unmatched columns
    matched_expected = set(rename_dict.values())
    columns_to_drop = [col for col in result_df.columns if col not in expected_columns]
    if columns_to_drop:
        result_df = result_df.drop(columns=columns_to_drop)
        logger.debug(f"Dropped columns: {columns_to_drop}")

    # Add missing expected columns
    missing_columns = [col for col in expected_columns if col not in result_df.columns]
    for col in missing_columns:
        result_df[col] = pd.NA
        logger.debug(f"Added missing column '{col}' with NaN values")

    # Reorder columns to match expected sequence
    result_df = result_df[expected_columns]

    return result_df


def _create_empty_dataframe_with_schema(expected_columns: List[str]) -> pd.DataFrame:
    """Create an empty DataFrame with the expected schema."""
    return pd.DataFrame(columns=expected_columns)


def merge_dataframes(
    dataframes: List[pd.DataFrame],
    ignore_index: bool = True,
    sort: bool = False
) -> pd.DataFrame:
    """
    Merge multiple DataFrames into a single consolidated DataFrame.

    Args:
        dataframes: List of DataFrames to merge
        ignore_index: Whether to ignore the index when concatenating
        sort: Whether to sort the result by columns

    Returns:
        Merged DataFrame

    Raises:
        ValueError: If no DataFrames provided or all are empty
    """
    if not dataframes:
        raise ValueError("No DataFrames provided for merging")

    # Filter out empty DataFrames
    non_empty_dfs = [df for df in dataframes if not df.empty]

    if not non_empty_dfs:
        logger.warning("All DataFrames are empty - returning empty DataFrame")
        # If we have at least one DataFrame, use its schema
        if dataframes:
            return pd.DataFrame(columns=dataframes[0].columns)
        else:
            return pd.DataFrame()

    logger.info(f"Merging {len(non_empty_dfs)} non-empty DataFrames")

    # Check schema consistency
    _validate_schema_consistency(non_empty_dfs)

    try:
        # Concatenate DataFrames
        merged_df = pd.concat(
            non_empty_dfs,
            ignore_index=ignore_index,
            sort=sort
        )

        logger.info(f"Merge complete: {len(non_empty_dfs)} DataFrames -> {merged_df.shape}")
        return merged_df

    except Exception as e:
        raise ValueError(f"Failed to merge DataFrames: {e}") from e


def _validate_schema_consistency(dataframes: List[pd.DataFrame]) -> None:
    """Validate that all DataFrames have consistent schemas."""
    if not dataframes:
        return

    reference_columns = set(dataframes[0].columns)

    for i, df in enumerate(dataframes[1:], 1):
        current_columns = set(df.columns)

        if current_columns != reference_columns:
            missing = reference_columns - current_columns
            extra = current_columns - reference_columns

            warning_parts = []
            if missing:
                warning_parts.append(f"missing columns: {list(missing)}")
            if extra:
                warning_parts.append(f"extra columns: {list(extra)}")

            logger.warning(
                f"DataFrame {i} has schema differences: {', '.join(warning_parts)}"
            )


def normalize_and_merge_dataframes(
    dataframes_with_sources: List[Tuple[pd.DataFrame, str]],
    expected_columns: List[str],
    strict_mode: bool = False,
    add_source_column: bool = False,
    source_column_name: str = "source_file"
) -> pd.DataFrame:
    """
    Normalize multiple DataFrames against a schema and merge them.

    This is a convenience function that combines schema normalization and merging.

    Args:
        dataframes_with_sources: List of (DataFrame, source_identifier) tuples
        expected_columns: List of expected column names
        strict_mode: Whether to use strict schema validation
        add_source_column: Whether to add a column identifying the source
        source_column_name: Name of the source identification column

    Returns:
        Merged and normalized DataFrame
    """
    if not dataframes_with_sources:
        return _create_empty_dataframe_with_schema(expected_columns)

    normalized_dfs = []

    for df, source in dataframes_with_sources:
        try:
            normalized_df = normalize_schema(df, expected_columns, strict_mode)

            # Add source column if requested
            if add_source_column and not normalized_df.empty:
                normalized_df[source_column_name] = source

            normalized_dfs.append(normalized_df)

        except Exception as e:
            logger.error(f"Failed to normalize DataFrame from {source}: {e}")
            if strict_mode:
                raise
            # In non-strict mode, skip problematic DataFrames
            continue

    if not normalized_dfs:
        logger.warning("No DataFrames successfully normalized")
        result_columns = expected_columns.copy()
        if add_source_column:
            result_columns.append(source_column_name)
        return pd.DataFrame(columns=result_columns)

    # Merge all normalized DataFrames
    return merge_dataframes(normalized_dfs)


def clean_merged_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean the merged DataFrame by removing duplicate rows and handling data types.

    Args:
        df: DataFrame to clean

    Returns:
        Cleaned DataFrame
    """
    if df.empty:
        return df

    original_shape = df.shape

    df = df.drop_duplicates() # Drop duplicate rows

    # Basic data type inference for numeric columns
    for col in df.columns:
        if df[col].dtype == 'object':
            # Try to convert to numeric if possible
            try:
                # First, try to convert to numeric
                numeric_series = pd.to_numeric(df[col], errors='coerce')

                # If more than 50% of values are numeric, convert the column
                non_null_count = df[col].notna().sum()
                numeric_count = numeric_series.notna().sum()

                if non_null_count > 0 and (numeric_count / non_null_count) > 0.5:
                    df[col] = numeric_series
                    logger.debug(f"Converted column '{col}' to numeric")

            except Exception:
                # Keep as object type if conversion fails
                pass

    logger.info(f"DataFrame cleaning: {original_shape} -> {df.shape}")
    return df
