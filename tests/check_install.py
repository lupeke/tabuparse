#!/usr/bin/env python3
"""
Installation test script.

This script verifies that tabuparse is properly installed and can be imported
and used. It creates sample data and tests basic functionality without
requiring actual PDF files.
"""

import sys
import tempfile
from pathlib import Path

def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")

    try:
        import tabuparse
        print(f"✓ tabuparse imported successfully (version: {tabuparse.__version__})")

        from tabuparse import process_pdfs, TabuparseConfig
        print("✓ Core functions imported")

        from tabuparse.config_parser import create_default_config, parse_config
        print("✓ Config parser imported")

        from tabuparse.data_processor import normalize_schema, merge_dataframes
        print("✓ Data processor imported")

        from tabuparse.output_writer import write_csv, write_sqlite
        print("✓ Output writer imported")

        return True

    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_dependencies():
    """Test that all dependencies are available."""
    print("\nTesting dependencies...")

    dependencies = [
        ('pandas', 'pandas'),
        ('click', 'click'),
        ('camelot', 'camelot'),
    ]

    all_ok = True

    for dep_name, import_name in dependencies:
        try:
            __import__(import_name)
            print(f"✓ {dep_name} available")
        except ImportError as e:
            print(f"✗ {dep_name} missing: {e}")
            all_ok = False

    # Test TOML support
    try:
        try:
            import tomllib
            print("✓ tomllib available (Python 3.11+)")
        except ImportError:
            import tomli
            print("✓ tomli available (fallback)")
    except ImportError:
        print("✗ TOML parsing not available")
        all_ok = False

    return all_ok


def test_config_functionality():
    """Test configuration functionality."""
    print("\nTesting configuration functionality...")

    try:
        from tabuparse.config_parser import create_default_config, TabuparseConfig

        # Test default config creation
        config = create_default_config()
        assert hasattr(config, 'expected_columns')
        assert hasattr(config, 'output_format')
        print("✓ Default configuration created")

        # Test programmatic config creation
        custom_config = TabuparseConfig(
            expected_columns=['ID', 'Name', 'Amount'],
            output_format='csv'
        )
        assert custom_config.expected_columns == ['ID', 'Name', 'Amount']
        print("✓ Custom configuration created")

        return True

    except Exception as e:
        print(f"✗ Configuration test failed: {e}")
        return False


def test_data_processing():
    """Test data processing functionality with sample data."""
    print("\nTesting data processing...")

    try:
        import pandas as pd
        from tabuparse.data_processor import normalize_schema, merge_dataframes

        # Create sample DataFrame
        df1 = pd.DataFrame({
            'id': [1, 2, 3],
            'customer_name': ['Alice', 'Bob', 'Charlie'],
            'extra_col': ['x', 'y', 'z']
        })

        df2 = pd.DataFrame({
            'ID': [4, 5],
            'Customer Name': ['David', 'Eve'],
            'Amount': [100, 200]
        })

        expected_columns = ['ID', 'Customer Name', 'Amount']

        # Test normalization
        norm_df1 = normalize_schema(df1, expected_columns)
        norm_df2 = normalize_schema(df2, expected_columns)

        assert list(norm_df1.columns) == expected_columns
        assert list(norm_df2.columns) == expected_columns
        print("✓ Schema normalization works")

        # Test merging
        merged = merge_dataframes([norm_df1, norm_df2])
        assert len(merged) == 5
        assert list(merged.columns) == expected_columns
        print("✓ DataFrame merging works")

        return True

    except Exception as e:
        print(f"✗ Data processing test failed: {e}")
        return False


def test_output_functionality():
    """Test output writing functionality."""
    print("\nTesting output functionality...")

    try:
        import pandas as pd
        from tabuparse.output_writer import write_csv, write_sqlite

        # Create sample data
        df = pd.DataFrame({
            'ID': [1, 2, 3],
            'Name': ['Alice', 'Bob', 'Charlie'],
            'Amount': [100.0, 200.0, 300.0]
        })

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Test CSV output
            csv_path = write_csv(df, temp_path / 'test.csv')
            assert Path(csv_path).exists()

            # Verify CSV content
            read_df = pd.read_csv(csv_path)
            assert len(read_df) == 3
            print("✓ CSV output works")

            # Test SQLite output
            sqlite_path = write_sqlite(df, temp_path / 'test.sqlite')
            assert Path(sqlite_path).exists()

            # Verify SQLite content
            import sqlite3
            with sqlite3.connect(sqlite_path) as conn:
                read_df = pd.read_sql('SELECT * FROM extracted_data', conn)
                assert len(read_df) == 3
            print("✓ SQLite output works")

        return True

    except Exception as e:
        print(f"✗ Output functionality test failed: {e}")
        return False


def test_cli_availability():
    """Test that CLI is available."""
    print("\nTesting CLI availability...")

    try:
        from tabuparse.cli import cli
        print("✓ CLI module imported successfully")

        # Test that the CLI can be invoked (without actually running it)
        import click.testing
        runner = click.testing.CliRunner()

        # Test --help flag
        result = runner.invoke(cli, ['--help'])
        if result.exit_code == 0:
            print("✓ CLI help command works")
            return True
        else:
            print(f"✗ CLI help failed: {result.output}")
            return False

    except Exception as e:
        print(f"✗ CLI test failed: {e}")
        return False


def main():
    """Run all installation tests."""
    print("=" * 60)
    print("TABUPARSE INSTALLATION TEST")
    print("=" * 60)

    tests = [
        test_imports,
        test_dependencies,
        test_config_functionality,
        test_data_processing,
        test_output_functionality,
        test_cli_availability,
    ]

    results = []

    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"✗ Test {test.__name__} crashed: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"Tests passed: {passed}/{total}")

    if passed == total:
        print("🎉 All tests passed! tabuparse is ready to use.")
        print("\nTry running:")
        print("  tabuparse --help")
        print("  tabuparse init-config example_config.toml")
        return 0
    else:
        print("❌ Some tests failed. Please check the installation.")
        print("\nTroubleshooting:")
        print("  - Make sure all dependencies are installed: pip install camelot-py[base] pandas click")
        print("  - For Python < 3.11, install tomli: pip install tomli")
        print("  - Reinstall tabuparse: pip install -e .")
        return 1


if __name__ == '__main__':
    sys.exit(main())
