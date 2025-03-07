# SystemVerilog Assertion Interface Generator

This script generates a SystemVerilog assertion interface for a given RTL design. It analyzes the RTL code to extract ports and registers, and creates an interface that can be used for writing assertions.

## Features

- Automatically detects the top-level module in the design hierarchy
- Extracts ports and registers from the RTL code
- Handles naming conflicts by using hierarchical paths
- Supports different modes for interface generation (SPY signals source):
  - Ports only (input | output | inout)
  - Registers only (signals with "_s" suffix)
  - Both ports and registers (default)
- Generates a bind statement for easy integration
- Creates well-formatted and organized interface code

## Prerequisites

- Python 3.x
- Required Python packages:
  - jinja2 (for template rendering)

## Usage

```bash
python if_gen.py [options]
```

### Command Line Options

- `-i, --input`: Path to RTL input files or directory (default: "./rtl")
  - Can specify multiple files/directories
  - Example: `-i ./rtl/dir1 ./rtl/dir2`

- `-o, --output`: Path to the output directory (optional)
  - If not specified, generates files in the current directory
  - Example: `-o ./output`

- `-m, --mode`: Select objects to include in the interface (default: "both")
  - Choices: "ports", "registers", "both"
  - Example: `-m ports`

- `-v, --verbose`: Increase verbosity level
  - Can be used for more detailed output

### Examples

1. Basic usage with default settings:
```bash
python if_gen.py
```

2. Generate interface for specific RTL files:
```bash
python if_gen.py -i ./rtl/module1.sv ./rtl/module2.sv
```

3. Generate interface in a specific output directory:
```bash
python if_gen.py -o ./output
```

4. Generate interface with only ports:
```bash
python if_gen.py -m ports
```

5. Generate interface with only registers:
```bash
python if_gen.py -m registers
```

6. Verbose output:
```bash
python if_gen.py -v
```

## Output Files

The script generates two main outputs:

1. Interface file: `gen_<top_module_name>_asrt_if.sv`
   - Contains the SystemVerilog interface definition
   - Includes port declarations and spy signal assignments
   - Organized with module-based sections

2. Bind statement (printed to console)
   - Shows how to bind the interface to the top module
   - Includes parameter mappings if present

## Interface Structure

The generated interface includes:

1. Port declarations from the top module
2. Spy signal declarations for ports and registers
3. Assignments connecting spy signals to the actual signals
4. Module-based organization with clear section headers

## Notes

- The script automatically detects the top module by analyzing the module hierarchy
- Register signals are identified by the suffix "_s" (configurable)
- Port conflicts are resolved by using hierarchical paths
- The interface name is derived from the top module name if not specified

## Error Handling

The script includes error handling for:
- Invalid input paths
- Invalid output directory
- Missing top module
- Multiple potential top modules
- File writing errors

## Contributing

Feel free to submit issues and enhancement requests!
