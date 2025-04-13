# ENVY - Environment Variable Path Analyzer

ENVY is a Python tool that helps analyze and generate environment variable-based paths and glob patterns. It's particularly useful for finding the most efficient way to reference files and directories using environment variables.

## Features

- Analyzes absolute paths and finds matching environment variables
- Generates glob patterns for path matching
- Supports parallel processing for faster analysis
- Colorful terminal output for better readability
- Option to show all possible matches or just the shortest path

## Installation

1. Clone this repository:
```bash
git clone https://github.com/ThemeHackers/envy.git
cd envy
```

2. Install the required dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Basic usage:
```bash
python envy.py "C:\path\to\analyze"
```

Show all possible matches:
```bash
python envy.py "C:\path\to\analyze" --all
```

## Requirements

- Python 3.6+
- colorama

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request. 