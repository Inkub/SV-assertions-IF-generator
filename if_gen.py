import os
import re
import argparse
import logging
from jinja2 import Environment, FileSystemLoader
from collections import Counter

# Path to the RTL file or directory
path_to_rtl = "./rtl"

# Design top module name
top_module_name = ""

# Name of the DUT instance (replace with top module instance_name)
top_instance_name = "i_dut"

# Name of the generated assertion interface.
# Default: gen_< top_module_name >_asrt_if 
interface_name = ""

# Registers pattern suffix.
# Default: _s
reg_pattern_suffix = "_s"

#---------------------------------------------------------------------------------------#

module_pattern = re.compile(r"""
    module\s+
                    (?P<module_name>\w+)        # Named group: module_name
    \s\.*?\#?\s*\(? (?P<parameters>.*?\))?      # Named group: parameters
    \s*\(           (?P<ports>.*?)\)\s*;        # Named group: ports
    \s*             (?P<body>.*?)endmodule      # Named group: body
""", re.VERBOSE | re.DOTALL)

param_pattern = re.compile(r"""
    parameter?
    \s*             (?P<type>(?:logic|logic\s*\[.*?\]|int))?    # Named group: type
    \s*             (?P<name>\w+)                               # Named group: name
    \s*(?:\=|\))\s* (?P<value>.*)?\,?                           # Named group: value
""", re.VERBOSE | re.DOTALL)

port_pattern = re.compile(r"""
    \s*(?P<direction>input|output|inout)    # Named group: direction
    \s*(?P<type>\w+)                        # Named group: type
    \s*(?P<width>\[.*?\])*?                 # Named group: width
    \s*(?P<name>\w+)                        # Named group: name
""", re.VERBOSE | re.DOTALL)

regs_pattern = re.compile(f"""
    \s*(?P<type>logic|\w+\_t)              # Named group: type
    \s*(?P<width>\[.*?\])?                 # Named group: width
    \s*(?:\w+(?<!{reg_pattern_suffix})\s*,)?
    \s*(?P<name>\w+{reg_pattern_suffix})   # Named group: name
    \s*(?:\w+)?\s*\;
""", re.VERBOSE | re.DOTALL)

def calc_max_type_width(match_list):
    max_type_width_len = 0

    for match in match_list:
        width = ""
        if match['width']:
            width = match['width']
        if max_type_width_len < (len(match['type']) + len(width)):
            max_type_width_len = len(match['type']) + len(width)
    
    return max_type_width_len

def calc_max_width(str_list: list[str]) -> int:
    max_width = 0
    for el in str_list:
        if len(el) > max_width:
            max_width = len(el)
    return max_width

def align_cols(match_list, max_width, prefix = ""):
    modified = []
    for match in match_list:
        width = ""
        if match['width']:
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

def align_str_col(cols: list[str]) -> list[str]:
    max_width = calc_max_width(cols)
    result = []
    for col in cols:
        modified = col
        for _ in range(max_width - len(col)):
            modified += ' '
        result.append(modified)
    return result

def is_instantiated(module_name, module_infos):
    for module in module_infos:
        for inst in module.instances:
            if inst[0] == module_name:
                return True
    return False

def find_top_module(module_infos):
    top_module = None

    if top_module_name != "":
        for module in module_infos:
            if module.module_name == top_module_name:
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
    for module in module_infos:
        if module.module_name == module_name:
            return module
    return None

def get_module_title(module_name : str) -> str:
    title = "//"
    prefix_len = int((84 - len(module_name)) / 2)

    for _ in range(prefix_len):title += '-'
    title += module_name.upper()

    suffix_len = 86 - len(title)
    for _ in range(suffix_len): title += '-'

    title += "//"

    title = "  " + title

    return title

def get_params_descriptions(params: list[re.Match]) -> str:
    result = ""
    for i in range(len(params)):
        param = params[i]
        result += f"//    {param['name']}"
        if(i != len(params) - 1):
            result += "\n"
    return result

def get_ports_descriptions(ports: list[re.Match]) -> str:
    result = ""
    for i in range(len(ports)):
        port = ports[i]
        result += f"//    {port['name']}"
        if(i != len(ports) - 1):
            result += "\n"
    return result

def get_all_registers(module, path, module_infos):
    spy_signals = [] # reg, path, module_name

    # get all regs from the module
    for reg in module.regs_matches:
        spy_signals.append((reg, f"{path}.{reg['name']}", module.module_name))

    # get all regs from all instantiated modules
    for inst in module.instances:
        inst_module = get_module_info(inst[0], module_infos)
        spy_signals.extend(get_all_registers(inst_module, f"{path}.{inst[1]}", module_infos))
    
    return spy_signals

def insert_module_names(regs: list[str], spy_signals: list) -> list[str]:
    module_name = ""
    modified_regs = []

    for i in range(len(spy_signals)):
        spy = spy_signals[i]
        if spy[2] != module_name:
            module_name = spy[2]
            modified_regs.append(f"{get_module_title(module_name)}")
        modified_regs.append(regs[i])
    
    return modified_regs

def parse_args():
    # Set up argument parser
    parser = argparse.ArgumentParser(description="System Verilog assertion interface generator")

    # verbosity
    parser.add_argument("-v", "--verbose", action="count", default=0,
                        help="Increase verbosity level (-v)")
    
    # Path to the RTL
    parser.add_argument("-i", "--input", nargs='+', default=[path_to_rtl],
                        help="Path to the RTL input files or directory")

    # Output file directory
    parser.add_argument("-o", "--output", help="Path to the generated file directory")
    
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

class module_info:
    def __init__(self, sv_code):
        self.sv_code = sv_code
        self.module_name = str | None
        self.module_match = re.Match[str] | None
        self.param_matches = []
        self.port_matches = []
        self.regs_matches = []
        self.instances = []
    
    def parse(self):
        self.module_match = re.search(module_pattern, self.sv_code)

        if self.module_match:
            param_list = self.module_match['parameters']
            self.param_matches = list(re.finditer(param_pattern, param_list))

            port_list = self.module_match['ports']
            self.port_matches = list(re.finditer(port_pattern, port_list))

            body = self.module_match['body']
            self.regs_matches = list(re.finditer(regs_pattern, body))

            self.module_name = self.module_match['module_name']

    def find_instances(self, module_names):
        if self.module_match and len(module_names) != 0:
            inst_pattern = re.compile(rf"\b({'|'.join(module_names)})\b\s+(?:#\(.*?\))\s*(\w+)\s*\(")
            instances = list(re.finditer(inst_pattern, self.module_match['body'])) # type: ignore
            for inst in instances:
                logging.info(f"Found instance in {self.module_name}: {inst.group(1)} - {inst.group(2)}")
                self.instances.append((inst.group(1), inst.group(2)))


def traverse_input_files(path: str) -> list[module_info]:
    module_infos = []

    if os.path.isdir(path):
        for root, _, files in os.walk(path):
            for file in files:
                if file.endswith((".sv", ".v")):
                    file_path = os.path.join(root, file)
                    content = ""
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = remove_sv_comments(f.read())
                        module = module_info(content)
                        module.parse()
                        module_infos.append(module)
    else:
        content = ""
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
            module = module_info(content)
            module.parse()
            module_infos.append(module)
    return module_infos

def generate_if_bind(top_module: module_info, if_name: str) -> str:
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
            if i != len(top_module.param_matches):
                bind += ','
            bind += '\n'
        bind += ") "
    else:
        bind += "\n  "

    bind += f"i_{if_name}(.*);"

    return bind

def resolve_conflicts(spy_signals):
    reg_names = [t[0] for t in spy_signals]

    counts = Counter(reg_names)
    duplicates = [item for item, count in counts.items() if count > 1]

    result = []
    for sig in spy_signals:
        if sig[0] in duplicates:
            result.append(sig[1][10:].replace('.', '_')) # use path from without `PATH_TOP
        else:
            result.append(sig[0]["name"])

    return result

def remove_sv_comments(code):
    # Remove multi-line comments
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.DOTALL)
    
    # Remove single-line comments
    code = re.sub(r"//.*", "", code)
    
    return code

def main():

    # get script arguments
    args = parse_args()

    # Configure logging based on verbosity level
    log_level = logging.WARNING  # Default: Show only warnings and errors
    if args.verbose == 1:
        log_level = logging.INFO   # Show info messages

    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    module_infos = []

    for input_arg in args.input:
        module_infos += traverse_input_files(input_arg)

    module_names = []

    # get all modules names
    for module in module_infos:
        module_names.append(module.module_name)

    # get all instances names
    for module in module_infos:
        module.find_instances(module_names)
        
    top_module = find_top_module(module_infos)
    logging.info(f"Top module is detected: {top_module.module_name}")

    # interface name
    if_name = interface_name
    if if_name == "":
        if_name = f"{top_module.module_name}_asrt_if"

    spy_signals = get_all_registers(top_module, "`PATH_TOP", module_infos)

    # get list of signals
    resolved_signals = resolve_conflicts(spy_signals)

    spy_list = [t[0] for t in spy_signals]
    regs_list = []

    for i in range(len(resolved_signals)):
        regs_list.append({"type": spy_list[i]["type"], "width": spy_list[i]["width"], "name": resolved_signals[i]})

    modified_ports = align_cols(top_module.port_matches, calc_max_type_width(top_module.port_matches), "input")
    modified_regs = align_cols(regs_list, calc_max_type_width(regs_list), "// var: ")

    # insert relevant module names before registers SPYs declarations
    modified_regs = insert_module_names(modified_regs, spy_signals)

    # parameter descriptions
    parameter_descriptions = get_params_descriptions(top_module.param_matches)

    # port descriptions
    port_descriptions= get_ports_descriptions(top_module.port_matches)

    # Create the interface entity
    interface_entity = f"interface {if_name} #( {top_module.module_match['parameters']} (\n  " + ",\n  ".join(modified_ports) + "\n);"

    # Create spy signals declarations
    spy_declarations = f"\n\n".join(modified_regs)

    # Assigns the spy signals to the RTL
    spy_assigns = ""
    modified_lhs = align_str_col([list(reg.values())[2] for reg in regs_list])
    for i in range(len(spy_signals)):
        spy = spy_signals[i]
        row = f"  assign {modified_lhs[i]} = {spy[1]};\n"
        spy_assigns += row

    # Load template from the current directory
    env = Environment(loader=FileSystemLoader("."))  
    template = env.get_template("asrt_if_template.j2")

    # Data to insert into the template
    data = {
        "if_name": if_name,
        "module_name": top_module.module_name,
        "parameter_descriptions": parameter_descriptions,
        "port_descriptions": port_descriptions,
        "entity": interface_entity,
        "top_instance": top_instance_name,
        "spy_decl": spy_declarations,
        "spy_assigns": spy_assigns
    }

    # Render the template
    output = template.render(data)

    output_path = f"gen_{if_name}.sv"
    if args.output:
        output_path = f"{args.output}/gen_{if_name}.sv"

    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # Check if the interface exists
    if os.path.exists(output_path):
        user_input = input(f"File '{output_path}' already exists. Do you want to regenerate it? [y/n]: ").strip().lower()

        if user_input not in ["y", "yes"]:
            print("Aborting file generation.")
            exit(0)

    # generate interface file
    with open(output_path, "w") as f:
        f.write(output)

    logging.info(f"Interface successfully generated into: {output_path}")

    # Print out the interface's bind
    print("Assertion interface bind:")
    print("------------------------------------------------------------")
    print(generate_if_bind(top_module, if_name))
    print("------------------------------------------------------------")


if __name__ == "__main__":
    main()