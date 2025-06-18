"""
tabuparse CLI.

This module provides a Click-based CLI for the tabuparse tool, allowing users to:
- Process multiple PDF files from the command line
- Specify configuration files and output options
- Control processing parameters like concurrency and output format
- Enable debug logging and summary statistics export
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import List, Optional, Tuple

import click
import pandas as pd

from . import __version__
from .core import process_pdfs, extract_from_single_pdf, configure_logging, get_processing_statistics
from .config_parser import TabuparseConfig, create_default_config, save_config
from .pdf_extractor import validate_pdf_file


@click.group()
@click.version_option(version=__version__)
@click.option(
    '--log-level',
    type=click.Choice(['DEBUG', 'INFO', 'WARNING', 'ERROR'], case_sensitive=False),
    default='INFO',
    help='Set logging level'
)
@click.option(
    '--log-file',
    type=click.Path(),
    help='Log to file instead of console'
)
@click.pass_context
def cli(ctx, log_level, log_file):
    """
    tabuparse - Extract, normalize, and merge tabular data from PDF documents.

    This tool processes PDF files to extract tables, normalizes them against
    predefined schemas, and exports the consolidated data to CSV or SQLite formats.

    Examples:

        # Process single PDF with default settings
        tabuparse process invoice.pdf

        # Process multiple PDFs with configuration
        tabuparse process *.pdf --config config.toml --output results.csv

        # Export to SQLite with summary statistics
        tabuparse process docs/*.pdf --format sqlite --summary
    """

    ctx.ensure_object(dict)
    configure_logging(log_level, log_file)

    # Store global options in context
    ctx.obj['log_level'] = log_level
    ctx.obj['log_file'] = log_file


@cli.command()
@click.argument('pdf_files', nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    '--config', '-c',
    type=click.Path(exists=True),
    help='Path to TOML configuration file'
)
@click.option(
    '--output', '-o',
    type=click.Path(),
    help='Output file path (auto-generated if not specified)'
)
@click.option(
    '--format', 'output_format',
    type=click.Choice(['csv', 'sqlite'], case_sensitive=False),
    default='csv',
    help='Output format'
)
@click.option(
    '--max-concurrent',
    type=click.IntRange(1, 20),
    default=5,
    help='Maximum concurrent PDF extractions'
)
@click.option(
    '--summary',
    is_flag=True,
    help='Export summary statistics alongside main output'
)
@click.option(
    '--no-clean',
    is_flag=True,
    help='Disable data cleaning (keep duplicates, etc.)'
)
@click.option(
    '--strict',
    is_flag=True,
    help='Enable strict schema validation (fail on mismatches)'
)
@click.pass_context
def process(ctx, pdf_files, config, output, output_format, max_concurrent, summary, no_clean, strict):
    """
    Process PDF files and extract tabular data.

    This command extracts tables from the specified PDF files, normalizes them
    against the expected schema (if configured), and exports the merged results.

    Examples:

        tabuparse process invoice1.pdf invoice2.pdf
        tabuparse process *.pdf --config schema.toml --output results.sqlite
        tabuparse process docs/*.pdf --format sqlite --summary --max-concurrent 3
    """
    try:
        # Convert to list and validate paths
        pdf_paths = list(pdf_files)
        click.echo(f"Processing {len(pdf_paths)} PDF files...")

        # Run async processing
        result_df = asyncio.run(
            process_pdfs(
                pdf_paths=pdf_paths,
                config_path=config,
                output_path=output,
                output_format=output_format.lower(),
                max_concurrent=max_concurrent,
                export_summary=summary,
                clean_data=not no_clean
            )
        )

        # Display results summary
        if not result_df.empty:
            click.echo(f"✓ Processing complete: {result_df.shape[0]} rows, {result_df.shape[1]} columns")

            # Show column names if not too many
            if len(result_df.columns) <= 10:
                click.echo(f"Columns: {', '.join(result_df.columns)}")
            else:
                click.echo(f"Columns: {', '.join(result_df.columns[:7])}, ... (+{len(result_df.columns)-7} more)")
        else:
            click.echo("⚠ No data extracted from the provided PDF files")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('pdf_file', type=click.Path(exists=True))
@click.option(
    '--config', '-c',
    type=click.Path(exists=True),
    help='Path to TOML configuration file'
)
@click.option(
    '--pages',
    help='Pages to extract (e.g., "1", "1,3,5", "1-3", "all")'
)
@click.option(
    '--flavor',
    type=click.Choice(['lattice', 'stream'], case_sensitive=False),
    default='lattice',
    help='Camelot extraction flavor'
)
@click.option(
    '--show-info',
    is_flag=True,
    help='Show detailed information about extracted tables'
)
def extract(pdf_file, config, pages, flavor, show_info):
    """
    Extract tables from a single PDF file (for testing/debugging).

    This command is useful for testing extraction parameters on individual files
    before processing larger batches.

    Examples:

        tabuparse extract document.pdf --pages "1-3" --flavor stream
        tabuparse extract invoice.pdf --config schema.toml --show-info
    """
    try:
        click.echo(f"Extracting tables from: {pdf_file}")

        # Override extraction parameters if provided via CLI
        extraction_params = None
        if pages or flavor != 'lattice':
            from .config_parser import ExtractionParameters
            extraction_params = ExtractionParameters()
            if pages:
                extraction_params.pages = pages
            if flavor:
                extraction_params.flavor = flavor.lower()

        # Extract tables
        tables = asyncio.run(
            extract_from_single_pdf(
                pdf_file,
                config_path=config
            )
        )

        if tables:
            click.echo(f"✓ Extracted {len(tables)} table(s)")

            for i, table in enumerate(tables, 1):
                click.echo(f"\nTable {i}: {table.shape[0]} rows × {table.shape[1]} columns")

                if show_info:
                    click.echo(f"Columns: {', '.join(table.columns)}")
                    click.echo("Sample data:")

                    # Show first few rows
                    sample_rows = min(3, len(table))
                    if sample_rows > 0:
                        click.echo(str(table.head(sample_rows)))
                    else:
                        click.echo("(No data rows)")
        else:
            click.echo("⚠ No tables found in the PDF file")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('pdf_files', nargs=-1, required=True, type=click.Path(exists=True))
@click.option(
    '--config', '-c',
    type=click.Path(exists=True),
    help='Path to TOML configuration file'
)
def preview(pdf_files, config):
    """
    Preview what would be processed without actually extracting data.

    This command analyzes the PDF files and configuration to show processing
    statistics and potential issues before running the full extraction.

    Examples:

        tabuparse preview *.pdf
        tabuparse preview docs/*.pdf --config schema.toml
    """
    try:
        pdf_paths = list(pdf_files)
        click.echo(f"Analyzing {len(pdf_paths)} PDF files...\n")

        stats = asyncio.run(
            get_processing_statistics(pdf_paths, config)
        )

        if 'error' in stats:
            click.echo(f"✗ Error analyzing files: {stats['error']}", err=True)
            return

        click.echo("📊 PROCESSING PREVIEW")
        click.echo("=" * 50)

        click.echo(f"Total PDF files: {stats['total_pdfs']}")
        click.echo(f"Valid PDF files: {stats['valid_pdfs']}")

        if stats['invalid_pdfs'] > 0:
            click.echo(f"Invalid PDF files: {stats['invalid_pdfs']}", color='yellow')

        click.echo(f"Expected columns: {stats['expected_column_count']}")
        if stats['expected_columns']:
            if len(stats['expected_columns']) <= 8:
                click.echo(f"  {', '.join(stats['expected_columns'])}")
            else:
                shown = ', '.join(stats['expected_columns'][:5])
                remaining = len(stats['expected_columns']) - 5
                click.echo(f"  {shown}, ... (+{remaining} more)")

        click.echo(f"Output format: {stats['output_format'].upper()}")
        click.echo(f"Strict schema mode: {'Yes' if stats['strict_schema'] else 'No'}")

        if stats['extraction_parameters_count'] > 0:
            click.echo(f"PDF-specific extraction configs: {stats['extraction_parameters_count']}")

        if stats['sample_pdf_info']:
            click.echo("\n📋 SAMPLE PDF ANALYSIS")
            click.echo("-" * 30)

            for pdf_path, info in stats['sample_pdf_info'].items():
                pdf_name = Path(pdf_path).name
                click.echo(f"\n{pdf_name}:")

                if 'error' in info:
                    click.echo(f"  ✗ Error: {info['error']}", color='red')
                else:
                    click.echo(f"  ✓ Readable: {info.get('readable', 'Unknown')}")
                    if 'tables_found_on_first_page' in info:
                        click.echo(f"  Tables on first page: {info['tables_found_on_first_page']}")

        click.echo(f"\n💡 Run 'tabuparse process {' '.join(pdf_files)}' to start processing")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.argument('output_file', type=click.Path())
@click.option(
    '--columns',
    help='Comma-separated list of expected column names'
)
@click.option(
    '--format', 'output_format',
    type=click.Choice(['csv', 'sqlite'], case_sensitive=False),
    default='csv',
    help='Default output format'
)
@click.option(
    '--flavor',
    type=click.Choice(['lattice', 'stream'], case_sensitive=False),
    default='lattice',
    help='Default extraction flavor'
)
def init_config(output_file, columns, output_format, flavor):
    """
    Generate a sample configuration file.

    This command creates a TOML configuration file with example settings
    that can be customized for your specific use case.

    Examples:

        tabuparse init-config config.toml
        tabuparse init-config schema.toml --columns "ID,Date,Amount,Description"
        tabuparse init-config settings.toml --format sqlite --flavor stream
    """
    try:
        config = create_default_config()

        if columns:
            config.expected_columns = [col.strip() for col in columns.split(',')]

        config.output_format = output_format.lower()
        config.default_extraction.flavor = flavor.lower()

        # Add some example extraction parameters
        if not config.extraction_parameters:
            from .config_parser import ExtractionParameters

            example_params = ExtractionParameters()
            example_params.pdf_path = "example.pdf"
            example_params.pages = "1-5"
            example_params.flavor = flavor.lower()

            config.extraction_parameters = [example_params]

        # Save configuration
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True) # Create directory if needed

        toml_content = _generate_config_toml(config)

        with open(output_path, 'w') as f:
            f.write(toml_content)

        click.echo(f"✓ Configuration file created: {output_path}")
        click.echo("📝 Edit the file to customize extraction parameters and expected columns")

    except Exception as e:
        click.echo(f"✗ Error: {e}", err=True)
        sys.exit(1)


def _generate_config_toml(config: TabuparseConfig) -> str:
    """Generate TOML configuration content manually."""
    lines = [
        "# tabuparse configuration file",
        "# Generated by: tabuparse init-config",
        "",
        "[table_structure]",
        f"expected_columns = {config.expected_columns}",
        "",
        "[settings]",
        f'output_format = "{config.output_format}"',
        f"strict_schema = {str(config.strict_schema).lower()}",
        "",
        "[default_extraction]",
        f'flavor = "{config.default_extraction.flavor}"',
        f'pages = "{config.default_extraction.pages}"',
        "",
        "# Example PDF-specific extraction parameters",
        "[[extraction_parameters]]",
        '# pdf_path = "specific_document.pdf"',
        '# pages = "1-3"',
        '# flavor = "stream"',
        '# table_areas = ["72,72,432,648"]  # left,bottom,right,top in points',
        "",
        "# Add more [[extraction_parameters]] sections as needed",
        "# for different PDF files with specific requirements",
    ]

    return "\n".join(lines)


@cli.command()
@click.argument('pdf_file', type=click.Path(exists=True))
def validate(pdf_file):
    """
    Validate a PDF file for table extraction compatibility.

    This command checks if a PDF file can be processed by tabuparse
    and provides information about potential issues.

    Examples:

        tabuparse validate document.pdf
        tabuparse validate problematic_file.pdf
    """
    try:
        click.echo(f"Validating PDF file: {pdf_file}")

        # Run validation
        is_valid = asyncio.run(
            asyncio.to_thread(validate_pdf_file, pdf_file)
        )

        if is_valid:
            click.echo("✓ PDF file appears to be valid for processing")

            # Try to get additional info
            try:
                from .pdf_extractor import get_pdf_info
                info = asyncio.run(
                    asyncio.to_thread(get_pdf_info, pdf_file)
                )

                if 'error' not in info:
                    click.echo(f"📄 File size: {Path(pdf_file).stat().st_size} bytes")
                    if 'tables_found_on_first_page' in info:
                        click.echo(f"📊 Tables found on first page: {info['tables_found_on_first_page']}")

            except Exception:
                pass  # Additional info is optional

        else:
            click.echo("✗ PDF file validation failed", err=True)
            click.echo("This file may not be processable by tabuparse", err=True)

    except Exception as e:
        click.echo(f"✗ Error during validation: {e}", err=True)
        sys.exit(1)


def main():
    """Entry point for the CLI application."""
    try:
        cli()
    except KeyboardInterrupt:
        click.echo("\n⚠ Operation cancelled by user", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ Unexpected error: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
