<div align="center">
    <img src="https://storage.googleapis.com/lupeke.dev/_tabuparse.png" alt="tabuparse" width="250" /><br />
    <p><b>extract, transform and export PDF tabular data</b></p>
    <p>
        <img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+" />
        <img src="https://img.shields.io/badge/asyncio-ready-blueviolet" alt="asyncio support" />
        <img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT" />
    </p>
</div>

## About
```tabuparse``` is a Python CLI tool and library for extracting, normalizing, and merging tabular data from PDF documents.

## Installation

> [!WARNING]
> This project is still in alpha mode and might go sideways.


### From source

```bash
git clone https://github.com/lupeke/tabuparse.git && \
cd tabuparse && \
python3 -m venv .venv && source .venv/bin/activate && \
pip install -e .
```

#### Run a health check
```bash
python tests/check_install.py
```

## Quick start

### CLI usage

```bash
# Process single PDF with default settings
tabuparse process example.pdf

# Process multiple PDFs with configuration
tabuparse process *.pdf --config settings.toml --output data.csv

# Export to SQLite with summary statistics
tabuparse process documents/*.pdf --format sqlite --summary

# Preview processing without extraction
tabuparse preview *.pdf --config settings.toml

# Extract from single PDF for testing
tabuparse extract document.pdf --pages "1-3" --flavor stream
```

### Library usage

```python
import asyncio
from tabuparse import process_pdfs

async def main():
    # Process PDFs and get merged DataFrame
    result_df = await process_pdfs(
        pdf_paths=['invoice1.pdf', 'invoice2.pdf'],
        config_path='schema.toml',
        output_format='csv'
    )

    print(f"Extracted {len(result_df)} rows")
    print(result_df.head())

asyncio.run(main())
```

## Configuration

```tabuparse``` uses TOML configuration files to define extraction parameters and expected schemas.

### generate sample configuration

```bash
tabuparse init-config settings.toml --columns "Invoice ID,Date,Amount,Description"
```

### configuration structure

```toml
# settings.toml
[table_structure]
expected_columns = [
    "Invoice ID",
    "Date",
    "Item Description",
    "Quantity",
    "Unit Price",
    "Total Amount"
]

[settings]
output_format = "csv"
strict_schema = false

[default_extraction]
flavor = "lattice"
pages = "all"

# PDF-specific extraction parameters
[[extraction_parameters]]
pdf_path = "invoice_batch_1.pdf"
pages = "1-5"
flavor = "lattice"

[[extraction_parameters]]
pdf_path = "statements.pdf"
pages = "all"
flavor = "stream"
table_areas = ["72,72,432,648"]  # left,bottom,right,top in points
```

### Configuration Options

#### table structure
- `expected_columns`: List of column names for schema normalization

#### settings
- `output_format`: "csv" or "sqlite"
- `strict_schema`: Enable strict schema validation (fail on mismatches)

#### extraction parameters
- `pages`: Page selection ("all", "1", "1,3,5", "1-3")
- `flavor`: Camelot extraction method ("lattice" or "stream")
- `table_areas`: Specific table regions to extract
- `pdf_path`: Apply parameters to specific PDF files

## CLI Commands

### `process`
Extract and merge tables from multiple PDF files.

```bash
tabuparse process file1.pdf file2.pdf [OPTIONS]

Options:
  -c, --config PATH       TOML configuration file
  -o, --output PATH       Output file path
  --format [csv|sqlite]   Output format (default: csv)
  --max-concurrent INT    Max concurrent extractions (default: 5)
  --summary              Export summary statistics
  --no-clean             Disable data cleaning
  --strict               Enable strict schema validation
```

### `extract`
Extract tables from a single PDF (for testing).

```bash
tabuparse extract document.pdf [OPTIONS]

Options:
  -c, --config PATH              Configuration file
  --pages TEXT                   Pages to extract
  --flavor [lattice|stream]      Extraction method
  --show-info                    Show detailed table information
```

### `preview`
Preview processing statistics without extraction.

```bash
tabuparse preview file1.pdf file2.pdf [OPTIONS]

Options:
  -c, --config PATH       Configuration file
```

### `init-config`
Generate sample configuration file.

```bash
tabuparse init-config config.toml [OPTIONS]

Options:
  --columns TEXT                 Expected column names (comma-separated)
  --format [csv|sqlite]          Default output format
  --flavor [lattice|stream]      Default extraction flavor
```

### `validate`
Validate PDF file compatibility.

```bash
tabuparse validate document.pdf
```

## Library API

### core functions

```python
from tabuparse import process_pdfs, extract_from_single_pdf

# Process multiple PDFs
result_df = await process_pdfs(
    pdf_paths=['file1.pdf', 'file2.pdf'],
    config_path='settings.toml',
    output_path='output.csv',
    output_format='csv',
    max_concurrent=5
)

# Extract from single PDF
tables = await extract_from_single_pdf(
    'document.pdf',
    config_path='settings.toml'
)
```

### configuration management

```python
from tabuparse.config_parser import parse_config, TabuparseConfig

# Load configuration
config = parse_config('settings.toml')

# Create programmatic configuration
config = TabuparseConfig(
    expected_columns=['ID', 'Name', 'Amount'],
    output_format='sqlite'
)
```

### data processing

```python
from tabuparse.data_processor import normalize_schema, merge_dataframes

# Normalize DataFrame schema
normalized_df = normalize_schema(
    df,
    expected_columns=['ID', 'Name', 'Amount'],
    strict_mode=False
)

# Merge multiple DataFrames
merged_df = merge_dataframes([df1, df2, df3])
```

## Examples

### basic invoice processing

```bash
# Process invoice PDFs with predefined schema
tabuparse process invoices/*.pdf --config invoice_schema.toml --output invoices.csv
```

### multi-format export

```python
import asyncio
from tabuparse import process_pdfs

async def process_financial_data():
    # Extract data
    df = await process_pdfs(
        pdf_paths=['q1_report.pdf', 'q2_report.pdf'],
        config_path='financial_schema.toml'
    )

    # Export to multiple formats
    df.to_csv('financial_data.csv', index=False)
    df.to_excel('financial_data.xlsx', index=False)

    return df

asyncio.run(process_financial_data())
```

### custom processing pipeline

```python
from tabuparse.pdf_extractor import extract_tables_from_pdf
from tabuparse.data_processor import normalize_schema
from tabuparse.output_writer import write_sqlite

async def custom_pipeline():
    # Extract tables
    tables = await extract_tables_from_pdf('document.pdf')

    # Process each table
    processed_tables = []
    for table in tables:
        normalized = normalize_schema(
            table,
            expected_columns=['ID', 'Date', 'Amount']
        )
        processed_tables.append(normalized)

    # Merge and export
    import pandas as pd
    merged = pd.concat(processed_tables, ignore_index=True)
    write_sqlite(merged, 'output.sqlite', table_name='extracted_data')

asyncio.run(custom_pipeline())
```



<br /><hr />
<a href="https://www.flaticon.com/free-icons/samplings" title="samplings icons">Samplings icons by Afian Rochmah Afif - Flaticon</a>
