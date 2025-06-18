"""
tabuparse - A Python library for extracting, normalizing, and merging tabular data from PDF documents.

This package provides both a command-line interface and a programmatic API for:
- Extracting tables from PDF files using camelot
- Normalizing extracted data against predefined schemas
- Merging data from multiple sources
- Exporting to CSV or SQLite formats

Example usage:
    import asyncio
    from tabuparse import process_pdfs

    async def main():
        result = await process_pdfs(
            pdf_paths=['doc1.pdf', 'doc2.pdf'],
            config_path='settings.toml',
            output_format='csv'
        )
        print(f"Processed {len(result)} rows")

    asyncio.run(main())
"""

from .core import process_pdfs, TabuparseConfig
from .pdf_extractor import extract_tables_from_pdf
from .data_processor import normalize_schema, merge_dataframes
from .output_writer import write_csv, write_sqlite
from .config_parser import parse_config

__version__ = "0.1.0"
__author__ = "Daniel Dias"
__email__ = "daniel@lupeke.dev"

__all__ = [
    "process_pdfs",
    "TabuparseConfig",
    "extract_tables_from_pdf",
    "normalize_schema",
    "merge_dataframes",
    "write_csv",
    "write_sqlite",
    "parse_config",
]
