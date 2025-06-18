"""
Basic tests.

This module contains fundamental tests to verify the package structure,
imports, and basic functionality.
"""

import pytest
import pandas as pd
from pathlib import Path
import tempfile
import os

def test_package_imports():
    """Test that all main package components can be imported."""
    try:
        import tabuparse
        from tabuparse import process_pdfs, TabuparseConfig
        from tabuparse.config_parser import parse_config, create_default_config
        from tabuparse.data_processor import normalize_schema, merge_dataframes
        from tabuparse.output_writer import write_csv, write_sqlite
        from tabuparse.pdf_extractor import extract_tables_from_pdf
        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import package components: {e}")


def test_package_version():
    """Test that package version is accessible."""
    import tabuparse
    assert hasattr(tabuparse, '__version__')
    assert isinstance(tabuparse.__version__, str)
    assert len(tabuparse.__version__) > 0


class TestConfigParser:
    """Test configuration parsing functionality."""

    def test_create_default_config(self):
        """Test creating default configuration."""
        from tabuparse.config_parser import create_default_config

        config = create_default_config()
        assert config is not None
        assert hasattr(config, 'expected_columns')
        assert hasattr(config, 'output_format')
        assert config.output_format == 'csv'
        assert config.strict_schema is False

    def test_config_with_toml_content(self):
        """Test parsing configuration from TOML content."""
        from tabuparse.config_parser import _build_config_from_dict

        config_data = {
            'table_structure': {
                'expected_columns': ['ID', 'Name', 'Amount']
            },
            'settings': {
                'output_format': 'sqlite',
                'strict_schema': True
            }
        }

        config = _build_config_from_dict(config_data)
        assert config.expected_columns == ['ID', 'Name', 'Amount']
        assert config.output_format == 'sqlite'
        assert config.strict_schema is True


class TestDataProcessor:
    """Test data processing functionality."""

    def test_normalize_schema_basic(self):
        """Test basic schema normalization."""
        from tabuparse.data_processor import normalize_schema

        df = pd.DataFrame({
            'ID': [1, 2, 3],
            'name': ['Alice', 'Laura', 'Carol'],
            'extra_col': ['foo', 'bar', 'baz']
        })

        expected_columns = ['ID', 'Name', 'Amount']

        normalized_df = normalize_schema(df, expected_columns)

        # Check that columns match expected
        assert list(normalized_df.columns) == expected_columns
        assert len(normalized_df) == 3

        # Check that 'name' was mapped to 'Name'
        assert normalized_df['Name'].tolist() == ['Alice', 'Laura', 'Carol']

        # Check that 'Amount' was added with NaN values
        assert normalized_df['Amount'].isna().all()

    def test_merge_dataframes_basic(self):
        """Test basic DataFrame merging."""
        from tabuparse.data_processor import merge_dataframes

        df1 = pd.DataFrame({'A': [1, 2], 'B': ['x', 'y']})
        df2 = pd.DataFrame({'A': [3, 4], 'B': ['z', 'w']})

        merged = merge_dataframes([df1, df2])

        assert len(merged) == 4
        assert list(merged.columns) == ['A', 'B']
        assert merged['A'].tolist() == [1, 2, 3, 4]

    def test_merge_empty_dataframes(self):
        """Test merging with empty DataFrames."""
        from tabuparse.data_processor import merge_dataframes

        df1 = pd.DataFrame({'A': [1, 2], 'B': ['x', 'y']})
        df2 = pd.DataFrame(columns=['A', 'B'])  # Empty DataFrame

        merged = merge_dataframes([df1, df2])

        assert len(merged) == 2
        assert merged['A'].tolist() == [1, 2]


class TestOutputWriter:
    """Test output writing functionality."""

    def test_write_csv_basic(self):
        """Test basic CSV writing."""
        from tabuparse.output_writer import write_csv

        df = pd.DataFrame({
            'ID': [1, 2, 3],
            'Name': ['Alice', 'Bob', 'Charlie'],
            'Amount': [100.0, 200.0, 300.0]
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / 'test_output.csv'

            result_path = write_csv(df, output_path)

            # Check file was created
            assert Path(result_path).exists()

            # Check content can be read back
            read_df = pd.read_csv(result_path)
            assert len(read_df) == 3
            assert list(read_df.columns) == ['ID', 'Name', 'Amount']

    def test_write_sqlite_basic(self):
        """Test basic SQLite writing."""
        from tabuparse.output_writer import write_sqlite

        df = pd.DataFrame({
            'ID': [1, 2, 3],
            'Name': ['Alice', 'Bob', 'Charlie'],
            'Amount': [100.0, 200.0, 300.0]
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / 'test_output.sqlite'

            result_path = write_sqlite(df, output_path)

            # Check file was created
            assert Path(result_path).exists()

            # Check content can be read back
            import sqlite3
            with sqlite3.connect(result_path) as conn:
                read_df = pd.read_sql('SELECT * FROM extracted_data', conn)
                assert len(read_df) == 3
                assert list(read_df.columns) == ['ID', 'Name', 'Amount']

    def test_generate_default_output_path(self):
        """Test default output path generation."""
        from tabuparse.output_writer import generate_default_output_path

        csv_path = generate_default_output_path('csv')
        assert csv_path.suffix == '.csv'
        assert 'tabuparse_output' in csv_path.name

        sqlite_path = generate_default_output_path('sqlite')
        assert sqlite_path.suffix == '.sqlite'
        assert 'tabuparse_output' in sqlite_path.name


class TestStringMatching:
    """Test string matching functionality used in column mapping."""

    def test_calculate_similarity(self):
        """Test string similarity calculation."""
        from tabuparse.data_processor import _calculate_similarity

        # Exact match
        assert _calculate_similarity('Invoice ID', 'Invoice ID') == 1.0

        # Case difference
        score = _calculate_similarity('invoice id', 'Invoice ID')
        assert score > 0.8

        # Similar strings
        score = _calculate_similarity('Total Amount', 'Total_Amount')
        assert score > 0.7

        # Different strings
        score = _calculate_similarity('Name', 'Amount')
        assert score < 0.5

    def test_normalize_string_for_matching(self):
        """Test string normalization for matching."""
        from tabuparse.data_processor import _normalize_string_for_matching

        assert _normalize_string_for_matching('Invoice_ID') == 'invoice id'
        assert _normalize_string_for_matching('Total-Amount') == 'total amount'
        assert _normalize_string_for_matching('Item (Description)') == 'item description'


class TestErrorHandling:
    """Test error handling scenarios."""

    def test_invalid_output_format(self):
        """Test handling of invalid output formats."""
        from tabuparse.output_writer import write_output, OutputWriterError

        df = pd.DataFrame({'A': [1, 2, 3]})

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / 'test_output'

            with pytest.raises(OutputWriterError):
                write_output(df, output_path, output_format='invalid_format')

    def test_empty_dataframe_handling(self):
        """Test handling of empty DataFrames."""
        from tabuparse.data_processor import normalize_schema

        empty_df = pd.DataFrame()
        expected_columns = ['A', 'B', 'C']

        result = normalize_schema(empty_df, expected_columns)

        assert list(result.columns) == expected_columns
        assert len(result) == 0


if __name__ == '__main__':
    pytest.main([__file__])
