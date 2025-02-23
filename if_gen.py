import os
import re
import argparse
import logging
from jinja2 import Environment, FileSystemLoader

path_to_rtl = "./rtl"
top_module_name = ""
top_instance_name = "i_dut" # Replace with top module instance_name

module_pattern = re.compile(r"""
    module\s+
                    (?P<module_name>\w+)        # Named group: module_name
    \s*\#?\s*\(?    (?P<parameters>.*?\))?      # Named group: parameters
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

regs_pattern = re.compile(r"""
    \s*(?P<type>logic|\w+\_t)              # Named group: type
    \s*(?P<width>\[.*?\])?                 # Named group: width
    \s*(?:\w+(?<!\_s)\s*,)?
    \s*(?P<name>\w+\_s)                    # Named group: name
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
        modified.append(str)
    return modified

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
                raise Exception("Top module wasn't found. Try to specify it explicitly")
            elif len(potential_tops) == 1:
                top_module = potential_tops[0]
            else:
                raise Exception(f"More than one potential top module detected: {', '.join([str(lst.module_name) for lst in potential_tops])}. Try to specify it explicitly")
    
    return top_module

def get_module_info(module_name, module_infos):
    for module in module_infos:
        if module.module_name == module_name:
            return module
    return None

def get_all_registers(module, path, module_infos):
    spy_signals = [] # reg, path

    # get all regs from the module
    for reg in module.regs_matches:
        spy_signals.append((reg, f"{path}.{reg['name']}"))

    # get all regs from all instantiated modules
    for inst in module.instances:
        inst_module = get_module_info(inst[0], module_infos)
        spy_signals.extend(get_all_registers(inst_module, f"{path}.{inst[1]}", module_infos))
    
    return spy_signals

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
        self.param_matches = {}
        self.port_matches = []
        self.regs_matches = []
        self.instances = []
    
    def parse(self):
        self.module_match = re.search(module_pattern, self.sv_code)

        if self.module_match:
            param_list = self.module_match['parameters']
            self.param_matches = re.finditer(param_pattern, param_list)

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
                print(f"Found instance in {self.module_name}: {inst.group(1)} - {inst.group(2)}")
                self.instances.append((inst.group(1), inst.group(2)))


def main():
    module_infos = []
    module_names = []
    spy_signals = [] # reg, path

    for root, _, files in os.walk(path_to_rtl):
        for file in files:
            if file.endswith((".sv", ".v")):
                file_path = os.path.join(root, file)
                content = ""
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
                    module = module_info(content)
                    module.parse()
                    module_infos.append(module)

    for module in module_infos:
        module_names.append(module.module_name)

    for module in module_infos:
        module.find_instances(module_names)
        
    top_module = find_top_module(module_infos)
    print(f"Top module is detected: {top_module.module_name}")

    spy_signals = get_all_registers(top_module, top_instance_name, module_infos)

    for sig in spy_signals:
        reg = sig[0]
        print(f"Signal: {reg['name']}, path: {sig[1]}")

    params = top_module.module_match['parameters']
    port_matches_list = top_module.port_matches
    regs_list = [t[0] for t in spy_signals]

    modified_ports = align_cols(port_matches_list, calc_max_type_width(port_matches_list), "input")
    modified_regs = align_cols(regs_list, calc_max_type_width(regs_list), "// var: ")

    # Create the interface entity
    interface_entity = f"interface {top_module.module_name} ( {params} (\n  " + ",\n  ".join(modified_ports) + "\n);\n"

    # Create spy signals declarations
    spy_declarations = f"\n" + ";\n".join(modified_regs) + ";\n"

    # Assigns the spy signals to the RTL
    spy_assigns = ""
    for spy in spy_signals:
        row = f"assign {spy[0]['name']} = {spy[1]};\n"
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

    with open("generated_interface.sv", "w") as f:
        f.write(output)

if __name__ == "__main__":
    main()