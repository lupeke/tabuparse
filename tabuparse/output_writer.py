"""
Output writer module.

Export processed DataFrame data to various formats:
- CSV files with customizable options
- SQLite databases with table creation and data insertion
- Automatic file naming and path handling
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional, Union, Dict, Any
import pandas as pd

logger = logging.getLogger(__name__)


class OutputWriterError(Exception):
    """Custom exception for output writing errors."""
    pass


def write_csv(
    df: pd.DataFrame,
    output_path: Union[str, Path],
    encoding: str = "utf-8",
    index: bool = False,
    **kwargs
) -> str:
    """
    Write DataFrame to CSV file.

    Args:
        df: DataFrame to export
        output_path: Path where CSV file should be saved
        encoding: File encoding (default: utf-8)
        index: Whether to include row index in output
        **kwargs: Additional arguments passed to pandas.to_csv()

    Returns:
        Absolute path of the created CSV file

    Raises:
        OutputWriterError: If writing fails
    """
    try:
        output_path = Path(output_path)

        output_path.parent.mkdir(parents=True, exist_ok=True) # Ensure directory exists

        # Add .csv extension if not present
        if output_path.suffix.lower() != '.csv':
            output_path = output_path.with_suffix('.csv')

        logger.info(f"Writing {df.shape[0]} rows to CSV: {output_path}")

        csv_options = {
            'encoding': encoding,
            'index': index,
            'na_rep': '',  # How to represent NaN values
            'float_format': None,  # Keep default float formatting
        }

        csv_options.update(kwargs) # Override with user-provided options
        df.to_csv(output_path, **csv_options)

        if not output_path.exists():
            raise OutputWriterError(f"CSV file was not created: {output_path}")

        file_size = output_path.stat().st_size
        logger.info(f"CSV export complete: {output_path} ({file_size} bytes)")

        return str(output_path.absolute())

    except Exception as e:
        raise OutputWriterError(f"Failed to write CSV file: {e}") from e


def write_sqlite(
    df: pd.DataFrame,
    output_path: Union[str, Path],
    table_name: str = "extracted_data",
    if_exists: str = "replace",
    create_index: bool = True,
    **kwargs
) -> str:
    """
    Write DataFrame to SQLite database.

    Args:
        df: DataFrame to export
        output_path: Path where SQLite file should be saved
        table_name: Name of the table to create/update
        if_exists: How to behave if table exists ('fail', 'replace', 'append')
        create_index: Whether to create an index on the first column
        **kwargs: Additional arguments passed to pandas.to_sql()

    Returns:
        Absolute path of the created SQLite file

    Raises:
        OutputWriterError: If writing fails
    """
    try:
        output_path = Path(output_path)

        # Ensure directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Add .sqlite extension if not present
        if output_path.suffix.lower() not in ['.sqlite', '.db', '.sqlite3']:
            output_path = output_path.with_suffix('.sqlite')

        logger.info(f"Writing {df.shape[0]} rows to SQLite: {output_path}")

        sqlite_options = {
            'name': table_name,
            'if_exists': if_exists,
            'index': False,  # Don't include pandas index as a column
            'method': None,  # Use default insertion method
        }
        sqlite_options.update(kwargs)

        with sqlite3.connect(output_path) as conn:
            # Write DataFrame to SQLite
            df.to_sql(con=conn, **sqlite_options)

            # Create index if requested and table was created/replaced
            if create_index and if_exists in ['replace'] and not df.empty:
                _create_sqlite_index(conn, table_name, df.columns[0])

            # Get table info for verification
            table_info = _get_sqlite_table_info(conn, table_name)
            logger.debug(f"SQLite table '{table_name}' info: {table_info}")

        if not output_path.exists():
            raise OutputWriterError(f"SQLite file was not created: {output_path}")

        file_size = output_path.stat().st_size
        logger.info(f"SQLite export complete: {output_path} ({file_size} bytes)")

        return str(output_path.absolute())

    except Exception as e:
        raise OutputWriterError(f"Failed to write SQLite file: {e}") from e


def _create_sqlite_index(conn: sqlite3.Connection, table_name: str, column_name: str) -> None:
    """Create an index on the specified column."""
    try:
        index_name = f"idx_{table_name}_{column_name}".replace(' ', '_').replace('-', '_')

        # Sanitize names to prevent SQL injection
        safe_table_name = _sanitize_sql_identifier(table_name)
        safe_column_name = _sanitize_sql_identifier(column_name)
        safe_index_name = _sanitize_sql_identifier(index_name)

        query = f'CREATE INDEX IF NOT EXISTS "{safe_index_name}" ON "{safe_table_name}" ("{safe_column_name}")'
        conn.execute(query)

        logger.debug(f"Created index '{safe_index_name}' on column '{safe_column_name}'")

    except Exception as e:
        logger.warning(f"Failed to create index: {e}")


def _sanitize_sql_identifier(identifier: str) -> str:
    """Sanitize SQL identifier to prevent injection."""
    # Remove or replace potentially dangerous characters
    import re
    sanitized = re.sub(r'[^\w\s-]', '', identifier)
    return sanitized.strip()


def _get_sqlite_table_info(conn: sqlite3.Connection, table_name: str) -> Dict[str, Any]:
    """Get information about the SQLite table."""
    try:
        cursor = conn.cursor()

        # Get table schema and row count
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        columns = cursor.fetchall()

        cursor.execute(f'SELECT COUNT(*) FROM "{table_name}"')
        row_count = cursor.fetchone()[0]

        return {
            'columns': [col[1] for col in columns],  # Column names
            'column_count': len(columns),
            'row_count': row_count,
        }

    except Exception as e:
        logger.warning(f"Failed to get table info: {e}")
        return {'error': str(e)}


def generate_default_output_path(
    format_type: str,
    base_name: str = "tabuparse_output",
    output_dir: Optional[Union[str, Path]] = None
) -> Path:
    """
    Generate a default output file path.

    Args:
        format_type: Output format ('csv' or 'sqlite')
        base_name: Base filename without extension
        output_dir: Directory for output file (default: current directory)

    Returns:
        Path object for the output file
    """
    if output_dir is None:
        output_dir = Path.cwd()
    else:
        output_dir = Path(output_dir)

    # Map format to extension
    extension_map = {
        'csv': '.csv',
        'sqlite': '.sqlite',
        'db': '.db',
        'database': '.sqlite',
    }

    extension = extension_map.get(format_type.lower(), '.csv')
    return output_dir / f"{base_name}{extension}"


def write_output(
    df: pd.DataFrame,
    output_path: Optional[Union[str, Path]] = None,
    output_format: str = "csv",
    **kwargs
) -> str:
    """
    Write DataFrame to output file with automatic format detection.

    This is a convenience function that chooses the appropriate writer
    based on the output format or file extension.

    Args:
        df: DataFrame to export
        output_path: Path for output file (auto-generated if None)
        output_format: Output format ('csv' or 'sqlite')
        **kwargs: Additional arguments passed to specific writer functions

    Returns:
        Absolute path of the created output file

    Raises:
        OutputWriterError: If format is unsupported or writing fails
    """
    if output_path:
        output_path = Path(output_path)
        # Infer format from extension if not explicitly provided
        if output_format == "csv":  # Default format
            extension = output_path.suffix.lower()
            if extension in ['.sqlite', '.db', '.sqlite3']:
                output_format = 'sqlite'
    else:
        output_path = generate_default_output_path(output_format)

    logger.info(f"Writing output in {output_format.upper()} format to: {output_path}")

    # Point to appropriate writer
    if output_format.lower() == 'csv':
        return write_csv(df, output_path, **kwargs)
    elif output_format.lower() in ['sqlite', 'db', 'database']:
        return write_sqlite(df, output_path, **kwargs)
    else:
        raise OutputWriterError(f"Unsupported output format: {output_format}")


def export_summary_statistics(
    df: pd.DataFrame,
    output_path: Union[str, Path],
    include_data_types: bool = True,
    include_null_counts: bool = True,
    include_value_counts: bool = False,
    top_n_values: int = 5
) -> str:
    """
    Export summary statistics about the DataFrame to a text file.

    Args:
        df: DataFrame to analyze
        output_path: Path for the summary file
        include_data_types: Whether to include column data types
        include_null_counts: Whether to include null value counts
        include_value_counts: Whether to include top values for each column
        top_n_values: Number of top values to show per column

    Returns:
        Absolute path of the created summary file
    """
    try:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.suffix.lower() != '.txt':
            output_path = output_path.with_suffix('.txt')

        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("TABUPARSE OUTPUT SUMMARY\n")
            f.write("=" * 50 + "\n\n")

            f.write(f"Dataset Shape: {df.shape[0]} rows × {df.shape[1]} columns\n")
            f.write(f"Total Data Points: {df.size}\n")
            f.write(f"Memory Usage: {df.memory_usage(deep=True).sum()} bytes\n\n")

            f.write("COLUMN INFORMATION\n")
            f.write("-" * 30 + "\n")

            for col in df.columns:
                f.write(f"\nColumn: {col}\n")

                if include_data_types:
                    f.write(f"  Data Type: {df[col].dtype}\n")

                f.write(f"  Non-null Count: {df[col].notna().sum()}\n")

                if include_null_counts:
                    null_count = df[col].isna().sum()
                    null_pct = (null_count / len(df)) * 100
                    f.write(f"  Null Count: {null_count} ({null_pct:.1f}%)\n")

                if include_value_counts and not df[col].empty:
                    try:
                        value_counts = df[col].value_counts().head(top_n_values)
                        if not value_counts.empty:
                            f.write(f"  Top {len(value_counts)} Values:\n")
                            for value, count in value_counts.items():
                                f.write(f"    {value}: {count}\n")
                    except Exception:
                        f.write("  Value counts: Unable to calculate\n")

            # Overall statistics for numeric columns
            numeric_cols = df.select_dtypes(include=['number']).columns
            if not numeric_cols.empty:
                f.write(f"\nNUMERIC STATISTICS\n")
                f.write("-" * 30 + "\n")
                f.write(str(df[numeric_cols].describe()))

        logger.info(f"Summary statistics exported to: {output_path}")
        return str(output_path.absolute())

    except Exception as e:
        raise OutputWriterError(f"Failed to export summary statistics: {e}") from e
