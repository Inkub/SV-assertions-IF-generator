import os
import re
import argparse
import logging
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
from jinja2 import Environment, FileSystemLoader
from collections import Counter

@dataclass
class Config:
    """Configuration settings for the assertion interface generator."""
    path_to_rtl: str = "./rtl"
    top_module_name: str = ""
    top_instance_name: str = "i_dut"
    interface_name: str = ""
    reg_pattern_suffix: str = "_s"

# Create global config instance
config = Config()

#---------------------------------------------------------------------------------------#

module_pattern = re.compile(r"""
    module\s+
                    (?P<module_name>\w+)    # Named group: module_name
                    (?:.*?[#(])             # Ignore everything before '#' or '('
    \s*\#?\s*\(?\s* (?P<parameters>.*?\))?  # Named group: parameters
    \s*\(           (?P<ports>.*?)\)\s*;    # Named group: ports
    \s*             (?P<body>.*?)endmodule  # Named group: body
""", re.VERBOSE | re.DOTALL)

param_pattern = re.compile(r"""
    parameter?
    \s*       (?P<type>(?:logic|logic\s*\[.*?\]|bit|bit\s*\[.*?\]|int(?:\s+unsigned)?))?  # Named group: type
    \s*       (?P<name>\w+)                                                               # Named group: name
    \s*\=?\s* (?P<value>.*?)? (?:\,|\))                                                   # Named group: value
""", re.VERBOSE | re.DOTALL)

port_pattern = re.compile(r"""
    \s*(?P<direction>input|output|inout)    # Named group: direction
    \s*(?P<type>(?:logic(?:\s+unsigned)?|bit|int(?:\s+unsigned)?|\b\w+\_t\b|\bt\_\w+\b)) # Named group: type
    \s*(?P<width>\[.*?\])*?                 # Named group: width
    \s*(?P<name>\w+)                        # Named group: name
""", re.VERBOSE | re.DOTALL)

regs_pattern = re.compile(rf"""
    \s*(?P<type>logic(?:\s+unsigned)?|\b\w+\_t\b|\bt\_\w+\b)  # Named group: type
    \s*(?P<width>\[\s*\w+\s*\-?\s*\d*\s*:\s*\d*\s*\])?  # Named group: width
    \s*(?:\b\w+(?<!{config.reg_pattern_suffix})\b\s*,)?
    \s*(?P<name>\b\w+{config.reg_pattern_suffix}\b)     # Named group: name
    .*?\;
""", re.VERBOSE | re.DOTALL)

#---------------------------------------------------------------------------------------#

def calc_max_type_width(match_list, include_width = True):
    """
    Calculate the maximum width of type declarations in a list of regex matches.

    Args:
        match_list: List of regex matches containing type and width information

    Returns:
        int: Maximum width of type declarations
    """
    rows = []

    for match in match_list:
        row = match['type']
        if include_width:
          if match['width']:
              row += ' '
              row += match['width']
        rows.append(row)
    return calc_max_width(rows)

def calc_max_width(str_list: list) -> int:
    """
    Calculate the maximum width of strings in a list.

    Args:
        str_list: List of strings to measure

    Returns:
        int: Maximum width of strings in the list
    """
    max_width = 0
    for el in str_list:
        if len(el) > max_width:
            max_width = len(el)
    return max_width

def align_cols(match_list, max_width, prefix = "", include_width = True):
    """
    Align columns in a list of regex matches with proper spacing.

    Args:
        match_list: List of regex matches containing type, width and name information
        max_width: Maximum width to align to
        prefix: Optional prefix to add before each line

    Returns:
        list: List of aligned strings
    """
    modified = []
    for match in match_list:
        width = ""
        if include_width and match['width']:
            width = match['width']
        if prefix == "":
            str = f"{match['type']} {width} "
        elif prefix == "// var: ":
            str = f"  {prefix}{match['name']}\n  {match['type']} {width} "
        else:
            str = f"{prefix} {match['type']} {width} "

        space_num = max_width - (len(match['type']) + len(width))
        for _ in range(space_num):
            str += ' '

        str += match['name']
        if prefix == "// var: ":
            str += ';'
        modified.append(str)
    return modified

def align_str_col(cols: list) -> list:
    """
    Align strings in a list by padding with spaces to match the longest string.

    Args:
        cols: List of strings to align

    Returns:
        list: List of aligned strings with equal length
    """
    max_width = calc_max_width(cols)
    result = []
    for col in cols:
        modified = col
        for _ in range(max_width - len(col)):
            modified += ' '
        result.append(modified)
    return result

def is_instantiated(module_name, module_infos):
    """
    Check if a module is instantiated in any other module.

    Args:
        module_name: Name of the module to check
        module_infos: List of all module information objects

    Returns:
        bool: True if the module is instantiated, False otherwise
    """
    for module in module_infos:
        for inst in module.instances:
            if inst[0] == module_name:
                return True
    return False

def find_top_module(module_infos):
    """
    Find the top-level module in the design hierarchy.

    Args:
        module_infos: List of module information objects

    Returns:
        module_info: The top-level module object

    Raises:
        SystemExit: If no top module is found or multiple potential tops exist
    """
    top_module = None

    if config.top_module_name != "":
        for module in module_infos:
            if module.module_name == config.top_module_name:
                top_module = module

    if top_module is None:
        potential_tops = []
        if len(module_infos) == 1:
            top_module = module_infos[0]
        else:
            for module in module_infos:
                if len(module.instances) != 0:
                    if not is_instantiated(module.module_name, module_infos):
                        potential_tops.append(module)
            if len(potential_tops) == 0:
                logging.error(" Top module wasn't found. Try to specify it explicitly")
                exit(1)
            elif len(potential_tops) == 1:
                top_module = potential_tops[0]
            else:
                logging.error(f" More than one potential top module detected: {', '.join([str(lst.module_name) for lst in potential_tops])}. Try to specify it explicitly")
                exit(1)

    return top_module

def get_module_info(module_name, module_infos):
    """
    Get module information object by module name.

    Args:
        module_name: Name of the module to find
        module_infos: List of all module information objects

    Returns:
        module_info: Module information object if found, None otherwise
    """
    for module in module_infos:
        if module.module_name == module_name:
            return module
    return None

def get_module_title(module_name : str) -> str:
    """
    Generate a formatted title string for a module.

    Args:
        module_name: Name of the module

    Returns:
        str: Formatted title string with dashes and module name centered
    """
    title = "//"
    prefix_len = int((84 - len(module_name)) / 2)

    for _ in range(prefix_len):title += '-'
    title += module_name.upper()

    suffix_len = 86 - len(title)
    for _ in range(suffix_len): title += '-'

    title += "//"

    title = "  " + title

    return title

def get_params_descriptions(params: list) -> str:
    """
    Generate parameter descriptions in a formatted string.

    Args:
        params: List of parameter regex matches

    Returns:
        str: Formatted string containing parameter descriptions
    """
    result = ""
    for i in range(len(params)):
        param = params[i]
        result += f"//    {param['name']}"
        if(i != len(params) - 1):
            result += "\n"
    return result

def get_ports_descriptions(ports: list) -> str:
    """
    Generate port descriptions in a formatted string.

    Args:
        ports: List of port regex matches

    Returns:
        str: Formatted string containing port descriptions
    """
    result = ""
    for i in range(len(ports)):
        port = ports[i]
        result += f"//    {port['name']}"
        if(i != len(ports) - 1):
            result += "\n"
    return result

def get_all_registers(module, path, module_infos):
    """
    Recursively collect all register signals from a module and its instances.

    Args:
        module: Current module to process
        path: Current hierarchical path
        module_infos: List of all module information objects

    Returns:
        list: List of tuples containing (register, full_path, module_name)
    """
    spy_signals = [] # reg, path, module_name

    # get all regs from the module
    for reg in module.regs_matches:
        spy_signals.append((reg, f"{path}.{reg['name']}", module.module_name))

    # get all regs from all instantiated modules
    for inst in module.instances:
        inst_module = get_module_info(inst[0], module_infos)
        spy_signals.extend(get_all_registers(inst_module, f"{path}.{inst[1]}", module_infos))

    # Sort by the module names
    spy_signals = sorted(spy_signals, key=lambda x: x[2])

    return spy_signals

def get_all_ports(module, path, module_infos):
    """
    Recursively collect all port signals from a module and its instances.

    Args:
        module: Current module to process
        path: Current hierarchical path
        module_infos: List of all module information objects

    Returns:
        list: List of tuples containing (port, full_path, module_name)
    """
    spy_signals = [] # reg, path, module_name

    for port in module.port_matches:
        spy_signals.append((port, f"{path}.{port['name']}", module.module_name))

    for inst in module.instances:
        inst_module = get_module_info(inst[0], module_infos)
        spy_signals.extend(get_all_ports(inst_module, f"{path}.{inst[1]}", module_infos))

    # Sort by the module names
    spy_signals = sorted(spy_signals, key=lambda x: x[2])

    return spy_signals

def insert_module_names(regs: list, spy_signals: list, args: argparse.Namespace, ports_count: int) -> list:
    module_name = ""
    modified_regs = []
    titles_inserted = 0

    for i in range(len(spy_signals)):
        spy = spy_signals[i]

        if i == ports_count and args.mode != "ports":
            modified_regs.insert(ports_count + titles_inserted,
                                 "  //-------------------------------------REGISTERS--------------------------------------//")

        if spy[2] != module_name:
            module_name = spy[2]
            modified_regs.append(f"{get_module_title(module_name)}")
            titles_inserted += 1
        modified_regs.append(regs[i])

    # insert register/ports divider
    if args.mode != "registers":
        modified_regs.insert(0,
                             "  //---------------------------------------PORTS----------------------------------------//")

    return modified_regs

def parse_args():
    """
    Parse command line arguments for the assertion interface generator.

    Returns:
        argparse.Namespace: Parsed command line arguments

    Raises:
        SystemExit: If input paths are invalid or output path is not a directory
    """
    parser = argparse.ArgumentParser(description="System Verilog assertion interface generator")

    # verbosity
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase verbosity level (-v)")

    # Path to the RTL
    parser.add_argument("-i", "--input", nargs='+', default=[config.path_to_rtl],
                        help="Path to the RTL input files or directory")

    # Output file directory
    parser.add_argument("-o", "--output", help="Path to the generated file directory")

    # Add a mode argument with choices
    parser.add_argument(
        "-m",
        "--mode",
        choices=["ports", "registers", "both"],
        default="both",  # Default mode
        help="Select object that shall be used in the assertion interface: 'ports' for only ports, 'registers' for only registers, 'both' for all."
    )

    args = parser.parse_args()

    # Validate input path
    for input_arg in args.input:
        if not os.path.exists(input_arg):
            logging.error(f" Input path '{input_arg}' does not exist.")
            exit(1)

    # Validate input path
    if args.output:
        if os.path.splitext(args.output)[1]:
            logging.error(f" Output path should be a directory, not a file.")
            exit(1)

    return args

class ModuleInfo:
    """Class to store and process SystemVerilog module information."""

    def __init__(self, sv_code: str):
        self.sv_code = sv_code
        self.module_name: Optional[str] = None
        self.module_match: Optional[re.Match] = None
        self.param_matches: List[re.Match] = []
        self.port_matches: List[re.Match] = []
        self.regs_matches: List[re.Match] = []
        self.instances: List[Tuple[str, str]] = []

    def parse(self) -> bool:
        """Parse the SystemVerilog code to extract module information."""
        self.module_match = re.search(module_pattern, self.sv_code)

        if self.module_match:
            param_list = self.module_match['parameters']
            self.param_matches = list(re.finditer(param_pattern, param_list))

            port_list = self.module_match['ports']
            self.port_matches = list(re.finditer(port_pattern, port_list))

            body = self.module_match['body']
            self.regs_matches = list(re.finditer(regs_pattern, body))

            self.module_name = self.module_match['module_name']
            return True
        else:
            return False

    def find_instances(self, module_names: List[str]) -> None:
        """Find all module instances in the current module."""
        if self.module_match and module_names:
            inst_pattern = re.compile(rf"\b({'|'.join(module_names)})\b\s+(?:\#\(.*?\))\s*(\w+)\s*\(", re.VERBOSE | re.DOTALL)
            instances = list(re.finditer(inst_pattern, self.module_match['body']))
            for inst in instances:
                logging.info(f"Found instance in {self.module_name}: {inst.group(1)} - {inst.group(2)}")
                self.instances.append((inst.group(1), inst.group(2)))

def traverse_input_files(path: str) -> list:
    """
    Traverse input files/directory and parse SystemVerilog modules.

    Args:
        path: Path to input file or directory

    Returns:
        list: List of parsed module information objects
    """
    module_infos = []

    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith((".sv", ".v")):
                    file_path = os.path.join(root, file)
                    content = ""
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = remove_sv_comments(f.read())
                        module = ModuleInfo(content)
                        if(module.parse()):
                            module_infos.append(module)
    else:
        content = ""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            module = ModuleInfo(content)
            if(module.parse()):
                module_infos.append(module)
    return module_infos

def generate_if_bind(top_module: ModuleInfo, if_name: str) -> str:
    """
    Generate SystemVerilog bind statement for the assertion interface.

    Args:
        top_module: Top-level module information object
        if_name: Name of the assertion interface

    Returns:
        str: Generated bind statement
    """
    bind = f"bind {top_module.module_name} {if_name}"

    if len(top_module.param_matches) != 0:
        max_length = 0
        for param in top_module.param_matches:
            if len(param["name"]) > max_length:
                max_length = len(param["name"])

        bind += " #(\n"
        for i in range(len(top_module.param_matches)):
            param_name = top_module.param_matches[i]["name"]
            bind += f"  .{param_name} "
            for _ in range(max_length - len(param_name)):
                bind += ' '
            bind += f"({param_name})"
            if i != len(top_module.param_matches) - 1:
                bind += ','
            bind += '\n'
        bind += ") "
    else:
        bind += "\n  "

    bind += f"i_{if_name}(.*);"

    return bind

def resolve_conflicts(spy_signals):
    """
    Resolve naming conflicts in spy signals by using hierarchical paths.

    Args:
        spy_signals: List of spy signal tuples

    Returns:
        list: List of resolved signal names
    """
    reg_names = [t[0]["name"] for t in spy_signals]

    counts = Counter(reg_names)
    duplicates = [item for item, count in counts.items() if count > 1]

    result = []
    for sig in spy_signals:
        if sig[0]["name"] in duplicates:
            renamed_sig = {
                "direction": None,
                "type": sig[0]["type"],
                "width": sig[0]["width"],
                "name": sig[1][10:].replace('.', '_') # use path from without `PATH_TOP
            }
            result.append((renamed_sig, sig[1], sig[2]))
        else:
            result.append(sig)

    # Sort by the module names
    result = sorted(result, key=lambda x: x[2])

    return result

def resolve_port_conflicts(spy_signals):
    """
    Resolve port naming conflicts by prioritizing output ports and using hierarchical paths.

    Args:
        spy_signals: List of tuples containing (port_match, path, module_name)

    Returns:
        list: List of resolved port signals with conflicts handled
    """
    # Group ports by name
    port_groups = {}
    for sig in spy_signals:
        port_name = sig[0]["name"]
        if port_name not in port_groups:
            port_groups[port_name] = []
        port_groups[port_name].append(sig)

    result = []

    # Process each group of ports with the same name
    for port_name, ports in port_groups.items():
        if len(ports) == 1:
            # No conflict, add the port as is if it has more than one dot
            if ports[0][1].count('.') > 1:
                result.append(ports[0])
        else:
            # Find output ports
            output_ports = [p for p in ports if p[0]["direction"] == "output"]

            if output_ports:
                # If there are output ports, add all of them with renamed signals
                for port in output_ports:
                    # Skip if path has only one dot
                    if port[1].count('.') <= 1:
                        continue
                    # Create a new dictionary with port information
                    renamed_port = {
                        "direction": port[0]["direction"],
                        "type": port[0]["type"],
                        "width": port[0]["width"],
                        "name": port[1][10:].replace('.', '_')
                    }
                    result.append((renamed_port, port[1], port[2]))
            else:
                # If no output ports, find the port with shortest path
                shortest_port = min(ports, key=lambda x: len(x[1]))
                # Only add if path has more than one dot
                if shortest_port[1].count('.') > 1:
                    result.append(shortest_port)

    # Sort by the module names
    result = sorted(result, key=lambda x: x[2])

    return result

def remove_sv_comments(code):
    """
    Remove SystemVerilog comments from code.

    Args:
        code: SystemVerilog code string

    Returns:
        str: Code with comments removed
    """
    # Remove multi-line comments
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)

    # Remove single-line comments
    code = re.sub(r"//.*", "", code)

    return code

def process_spy_signals(top_module: ModuleInfo, mode: str, module_infos: List[ModuleInfo]) -> Tuple[List[Tuple], int]:
    """
    Process spy signals based on the selected mode.

    Args:
        top_module: Top-level module
        mode: Operation mode ("ports", "registers", or "both")
        module_infos: List of all module information objects

    Returns:
        Tuple[List[Tuple], int]: List of spy signals and count of port signals
    """
    spy_signals = []
    ports_count = 0

    if mode == "registers":
        spy_signals = resolve_conflicts(get_all_registers(top_module, "`PATH_TOP", module_infos))
    elif mode == "ports":
        spy_signals = resolve_port_conflicts(get_all_ports(top_module, "`PATH_TOP", module_infos))
    else:
        port_list = resolve_port_conflicts(get_all_ports(top_module, "`PATH_TOP", module_infos))
        reg_list = resolve_conflicts(get_all_registers(top_module, "`PATH_TOP", module_infos))
        spy_signals.extend(port_list)
        spy_signals.extend(reg_list)
        ports_count = len(port_list)

    return spy_signals, ports_count

def generate_interface_content(top_module: ModuleInfo, spy_signals: List[Tuple],
                            ports_count: int, args: argparse.Namespace) -> Dict:
    """
    Generate interface content from module information and spy signals.

    Args:
        top_module: Top-level module
        spy_signals: List of spy signal tuples
        ports_count: Number of port signals
        args: Command line arguments

    Returns:
        Dict: Dictionary containing interface content
    """
    spy_list = [t[0] for t in spy_signals]

    modified_params = align_cols(top_module.param_matches,
                              calc_max_type_width(top_module.param_matches, False), "", False)
    modified_ports = align_cols(top_module.port_matches,
                              calc_max_type_width(top_module.port_matches), "input")
    modified_regs = align_cols(spy_list, calc_max_type_width(spy_list), "// var: ")

    # Insert module names and dividers
    modified_regs = insert_module_names(modified_regs, spy_signals, args, ports_count)

    # Generate descriptions
    parameter_descriptions = get_params_descriptions(top_module.param_matches)
    port_descriptions = get_ports_descriptions(top_module.port_matches)

    # interface name
    if_name = config.interface_name
    if if_name == "":
        if_name = f"{top_module.module_name}_asrt_if"

    # Create interface entity
    # interface_entity = f"interface {if_name} #(\n  {top_module.module_match['parameters']} (\n  " + \
    #                   ",\n  ".join(modified_ports) + "\n);"
    interface_entity = f"interface {if_name}"
    if modified_params:
      interface_entity += " #(\n  parameter " + ",\n  parameter ".join(modified_params) + "\n)"
    if modified_ports:
      interface_entity += " (\n  " + ",\n  ".join(modified_ports) + "\n)"
    interface_entity += ";"

    # Create spy declarations and assignments
    spy_declarations = f"\n\n".join(modified_regs)
    modified_lhs = align_str_col([spy[0]["name"] for spy in spy_signals])
    spy_assigns = "".join(f"  assign {modified_lhs[i]} = {spy[1]};\n"
                         for i, spy in enumerate(spy_signals))

    return {
        "if_name": if_name,
        "module_name": top_module.module_name,
        "parameter_descriptions": parameter_descriptions,
        "port_descriptions": port_descriptions,
        "entity": interface_entity,
        "top_instance": config.top_instance_name,
        "spy_decl": spy_declarations,
        "spy_assigns": spy_assigns
    }

def write_file(file_path: str, content: str) -> None:
    """
    Write content to a file, creating directories if needed.

    Args:
        file_path: Path to the output file
        content: Content to write to the file

    Raises:
        SystemExit: If file writing fails
    """
    try:
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(file_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # Write the file
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        logging.error(f"Failed to write file {file_path}: {str(e)}")
        exit(1)

def main():
    """Main entry point for the assertion interface generator."""
    # Parse arguments and setup logging
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s"
    )

    # Process input files
    module_infos = []
    for input_arg in args.input:
        module_infos.extend(traverse_input_files(input_arg))

    # Find module names and instances
    module_names = [module.module_name for module in module_infos]
    for module in module_infos:
        module.find_instances(module_names)

    # Find top module
    top_module = find_top_module(module_infos)
    logging.info(f"Top module detected: {top_module.module_name}")

    # Process spy signals
    spy_signals, ports_count = process_spy_signals(top_module, args.mode, module_infos)

    # Generate interface content
    interface_data = generate_interface_content(top_module, spy_signals, ports_count, args)

    # get template dir
    # Get the directory where the script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Render template
    env = Environment(loader=FileSystemLoader(script_dir))
    template = env.get_template("asrt_if_template.j2")
    output = template.render(interface_data)

        # interface name
    if_name = config.interface_name
    if if_name == "":
        if_name = f"{top_module.module_name}_asrt_if"

    # Write output file
    output_path = f"gen_{if_name}.sv"
    if args.output:
        output_path = f"{args.output}/gen_{if_name}.sv"

    write_file(output_path, output)
    logging.info(f"Interface successfully generated into: {output_path}")

    # Print bind statement
    print("Assertion interface bind:")
    print("------------------------------------------------------------")
    print(generate_if_bind(top_module, if_name))
    print("------------------------------------------------------------")

if __name__ == "__main__":
    main()