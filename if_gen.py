import os
import re
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

class module_info:
    def __init__(self, sv_code):
        self.sv_code = sv_code
        self.module_name = str | None
        self.module_match = re.Match[str] | None
        self.param_matches = {}
        self.port_matches = {}
        self.regs_matches = {}
        self.instances = [(str, str)]
    
    def parse(self):
        self.module_match = re.search(module_pattern, self.sv_code)

        if self.module_match:
            param_list = self.module_match['parameters']
            self.param_matches = re.finditer(param_pattern, param_list)

            port_list = self.module_match['ports']
            self.port_matches = re.finditer(port_pattern, port_list)

            regs_list = self.module_match['body']
            self.regs_matches = re.finditer(regs_pattern, regs_list)

            self.module_name = self.module_match['module_name']

    def find_instances(self, module_names):
        if self.module_match and len(module_names) != 0:
            inst_pattern = re.compile(rf"\b({'|'.join(module_names)})\b\s+(?:#\(.*?\))\s*(\w+)\s*\(")
            instances = list(re.finditer(inst_pattern, self.module_match['body'])) # type: ignore
            for inst in instances:
                print(f"Found instance in {self.module_name}: {inst.group(2)}")
                self.instances.append((inst.group(1), inst.group(2)))


def main():

if __name__ == "__main__":
    main()