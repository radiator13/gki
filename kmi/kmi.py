import sys


def read_file_to_set(filename):
    line_set = set()
    try:
        with open(filename, "r") as file:
            for line in file:
                line = line.strip().split()
                if len(line) == 1:
                    line_set.add(line[0])
                elif len(line) > 1:
                    line_set.add(line[1])
    except FileNotFoundError:
        raise FileNotFoundError(f"File {filename} not found or cannot be opened.")
    return line_set


def read_file_to_dict(filename):
    line_dict = {}
    try:
        with open(filename, "r") as file:
            for line in file:
                value, key = line.split()[:2]
                line_dict[key.strip()] = value.strip()
    except FileNotFoundError:
        raise FileNotFoundError(f"File {filename} not found or cannot be opened.")
    return line_dict


required_sym_set = read_file_to_set("rss.txt")

kernel_sym_set = read_file_to_set("module.symvers")

kernel_sym_dict = read_file_to_dict("module.symvers")
gki_sym_dict = read_file_to_dict("gki.symvers")

missing_count = 0

for element in required_sym_set:
    if element not in kernel_sym_set:
        print(f"ERROR: {element} IS MISSING")
        missing_count += 1

if missing_count > 0:
    print(f"ERROR:{missing_count} SYMBOLS ARE MISSING")
    sys.exit(1)

mismatch_count = 0
for element in required_sym_set:
    if element in kernel_sym_dict and element in gki_sym_dict:
        kernel_crc = kernel_sym_dict[element]
        gki_crc = gki_sym_dict[element]
        if kernel_crc != gki_crc:
            print(f"ERROR: CRC MISMATCH {element} :: KERNEL:{kernel_crc} GKI:{gki_crc}")
            mismatch_count += 1
    else:
        print(f"SYMBOL{element} IS NOT PRESENT IN GKI")
        sys.exit(1)

if mismatch_count > 0:
    print(f"{mismatch_count} CRC MISMATCHES IN TOTAL")
    sys.exit(1)
