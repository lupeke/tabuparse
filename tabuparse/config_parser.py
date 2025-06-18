"""
Configuration parser.

This module handles parsing TOML configuration files that define:
- Expected column schemas for table normalization
- PDF-specific extraction parameters (pages, flavors, table areas)
- Default extraction settings
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # Fallback for older Python versions

logger = logging.getLogger(__name__)


@dataclass
class ExtractionParameters:
    """Parameters for PDF table extraction."""

    pdf_path: Optional[str] = None
    pages: Union[str, int, List[int]] = "all"
    start_page: Optional[int] = None
    end_page: Optional[int] = None
    flavor: str = "lattice"
    table_areas: Optional[List[str]] = None
    columns: Optional[List[str]] = None
    split_text: bool = False
    flag_size: bool = True
    strip_text: str = "\n"
    row_tol: int = 2
    column_tol: int = 0


@dataclass
class TabuparseConfig:
    """Main configuration class."""

    expected_columns: List[str] = field(default_factory=list)
    extraction_parameters: List[ExtractionParameters] = field(default_factory=list)
    default_extraction: ExtractionParameters = field(default_factory=ExtractionParameters)
    strict_schema: bool = False
    output_format: str = "csv"
    output_path: Optional[str] = None


def parse_config(config_path: Union[str, Path]) -> TabuparseConfig:
    """
    Parse a TOML configuration file and return a TabuparseConfig object.

    Args:
        config_path: Path to the TOML configuration file

    Returns:
        TabuparseConfig object with parsed settings

    Raises:
        FileNotFoundError: If the config file doesn't exist
        ValueError: If the config file is malformed or invalid
    """
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    try:
        with open(config_path, "rb") as f:
            config_data = tomllib.load(f)
    except Exception as e:
        raise ValueError(f"Failed to parse TOML configuration: {e}") from e

    return _build_config_from_dict(config_data)


def _build_config_from_dict(config_data: Dict[str, Any]) -> TabuparseConfig:
    """Build TabuparseConfig from parsed TOML dictionary."""
    config = TabuparseConfig()

    table_structure = config_data.get("table_structure", {})
    config.expected_columns = table_structure.get("expected_columns", [])

    settings = config_data.get("settings", {})
    config.strict_schema = settings.get("strict_schema", False)
    config.output_format = settings.get("output_format", "csv")
    config.output_path = settings.get("output_path")

    default_params = config_data.get("default_extraction", {})
    config.default_extraction = _build_extraction_params(default_params)

    extraction_params_list = config_data.get("extraction_parameters", [])
    config.extraction_parameters = [
        _build_extraction_params(params) for params in extraction_params_list
    ]

    _validate_config(config)

    logger.info(f"Loaded configuration with {len(config.expected_columns)} expected columns")
    if config.extraction_parameters:
        logger.info(f"Found {len(config.extraction_parameters)} PDF-specific parameter sets")

    return config


def _build_extraction_params(params_dict: Dict[str, Any]) -> ExtractionParameters:
    """Build ExtractionParameters from dictionary."""
    params = ExtractionParameters()

    direct_fields = [
        "pdf_path", "pages", "start_page", "end_page", "flavor",
        "table_areas", "columns", "split_text", "flag_size",
        "strip_text", "row_tol", "column_tol"
    ]

    for field_name in direct_fields:
        if field_name in params_dict:
            setattr(params, field_name, params_dict[field_name])

    # Handle pages parameter conversion
    if "pages" in params_dict:
        pages_value = params_dict["pages"]
        if isinstance(pages_value, str):
            params.pages = pages_value
        elif isinstance(pages_value, int):
            params.pages = str(pages_value)
        elif isinstance(pages_value, list):
            params.pages = ",".join(map(str, pages_value))

    # Handle start_page/end_page to pages conversion
    if params.start_page is not None and params.end_page is not None:
        if params.pages == "all":
            params.pages = f"{params.start_page}-{params.end_page}"
    elif params.start_page is not None and params.pages == "all":
        params.pages = f"{params.start_page}-"
    elif params.end_page is not None and params.pages == "all":
        params.pages = f"1-{params.end_page}"

    return params


def _validate_config(config: TabuparseConfig) -> None:
    """Validate the parsed configuration."""
    # Check that expected_columns is not empty if we have extraction parameters
    if config.extraction_parameters and not config.expected_columns:
        logger.warning(
            "Extraction parameters defined but no expected_columns specified. "
            "Schema normalization will be skipped."
        )

    valid_formats = ["csv", "sqlite"]
    if config.output_format not in valid_formats:
        raise ValueError(
            f"Invalid output_format '{config.output_format}'. "
            f"Must be one of: {valid_formats}"
        )

    valid_flavors = ["lattice", "stream"]
    for params in config.extraction_parameters:
        if params.flavor not in valid_flavors:
            raise ValueError(
                f"Invalid flavor '{params.flavor}'. Must be one of: {valid_flavors}"
            )

    if config.default_extraction.flavor not in valid_flavors:
        raise ValueError(
            f"Invalid default flavor '{config.default_extraction.flavor}'. "
            f"Must be one of: {valid_flavors}"
        )


def create_default_config() -> TabuparseConfig:
    """Create a default configuration with sensible defaults."""
    return TabuparseConfig(
        expected_columns=[],
        extraction_parameters=[],
        default_extraction=ExtractionParameters(),
        strict_schema=False,
        output_format="csv",
        output_path=None
    )


def get_extraction_params_for_pdf(
    config: TabuparseConfig, pdf_path: str
) -> ExtractionParameters:
    """
    Get extraction parameters for a specific PDF file.

    Returns PDF-specific parameters if found, otherwise returns default parameters.
    """
    pdf_name = Path(pdf_path).name

    # Look for exact path match first
    for params in config.extraction_parameters:
        if params.pdf_path and Path(params.pdf_path).name == pdf_name:
            return params

    # Look for exact full path match
    for params in config.extraction_parameters:
        if params.pdf_path == pdf_path:
            return params

    return config.default_extraction


def save_config(config: TabuparseConfig, config_path: Union[str, Path]) -> None:
    """
    Save a TabuparseConfig to a TOML file.

    Note: This is a utility function for generating example configs.
    """
    import toml  # Note: requires python-toml for writing

    config_dict = {
        "table_structure": {
            "expected_columns": config.expected_columns
        },
        "settings": {
            "strict_schema": config.strict_schema,
            "output_format": config.output_format,
        }
    }

    if config.output_path:
        config_dict["settings"]["output_path"] = config.output_path

    # Add default extraction parameters if they differ from defaults
    default_params = ExtractionParameters()
    if config.default_extraction != default_params:
        config_dict["default_extraction"] = _extraction_params_to_dict(
            config.default_extraction
        )

    # Add PDF-specific extraction parameters
    if config.extraction_parameters:
        config_dict["extraction_parameters"] = [
            _extraction_params_to_dict(params)
            for params in config.extraction_parameters
        ]

    with open(config_path, "w") as f:
        toml.dump(config_dict, f)


def _extraction_params_to_dict(params: ExtractionParameters) -> Dict[str, Any]:
    """Convert ExtractionParameters to dictionary for TOML serialization."""
    result = {}
    default_params = ExtractionParameters()

    for field_name in params.__dataclass_fields__:
        value = getattr(params, field_name)
        default_value = getattr(default_params, field_name)

        if value != default_value and value is not None:
            result[field_name] = value

    return result
