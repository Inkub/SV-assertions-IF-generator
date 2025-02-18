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

def main():

if __name__ == "__main__":
    main()