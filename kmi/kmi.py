import sys

# Parse the CVE file with two columns: symbol name and CRC in hex, delimited by -----
def parse_cve(file_path):
    cve_symbols = {}
    with open(file_path, 'r') as file:
        for line in file:
            parts = line.strip().split('-----')
            if len(parts) == 2:
                symbol_name, crc = parts
                cve_symbols[symbol_name.strip()] = crc.strip()
    return cve_symbols

# Parse the vmlinux.symvers file and extract symbol CRCs
def parse_symvers(file_path):
    with open(file_path, 'r') as file:
        return {line.split()[1]: line.split()[0] for line in file if len(line.split()) >= 2}

# Read the list of symbols from the sym_names file
def parse_sym_names(file_path):
    with open(file_path, 'r') as file:
        return [line.strip() for line in file]

# Validate and convert CRC to integer, returns None if invalid
def validate_crc(crc):
    try:
        crc_int = int(crc, 16)
        if 0 <= crc_int < 2**32:
            return crc_int
        else:
            print(f"Warning: CRC value {crc} is not a valid 32-bit value.")
            return None
    except (ValueError, TypeError):
        print(f"Error: Invalid CRC value {crc}.")
        return None

# Compare CRC values and log mismatched symbols
def compare_crcs(cve_symbols, symvers_symbols, target_symbols):
    mismatches = {}
    missing_crcs_in_cve = []
    missing_crcs_in_symvers = []
    matched_count = 0
    checked_count = 0

    for symbol in target_symbols:
        checked_count += 1

        cve_crc = cve_symbols.get(symbol)
        # CVE missing: check if present in symvers or missing entirely
        if cve_crc is None:
            if symbol in symvers_symbols:
                missing_crcs_in_cve.append(symbol)
            else:
                missing_crcs_in_symvers.append(symbol)
            continue

        # CRC in CVE but not in symvers
        symvers_crc = symvers_symbols.get(symbol)
        if symvers_crc is None:
            missing_crcs_in_symvers.append(symbol)
            continue

        # Both CRCs present: validate and compare
        cve_crc_int = validate_crc(cve_crc)
        symvers_crc_int = validate_crc(symvers_crc)
        if cve_crc_int is None or symvers_crc_int is None:
            continue
        if cve_crc_int != symvers_crc_int:
            mismatches[symbol] = (cve_crc, symvers_crc)
        else:
            matched_count += 1

    # Identify any unclassified symbols (for debug)
    all_set = set(target_symbols)
    classified = (
        set(mismatches) |
        set(missing_crcs_in_cve) |
        set(missing_crcs_in_symvers) |
        {s for s in target_symbols if s in cve_symbols and s in symvers_symbols and
         validate_crc(cve_symbols[s]) == validate_crc(symvers_symbols[s])}
    )
    leftover = all_set - classified
    if leftover:
        print("Unclassified symbols (unexpected):", leftover)

    return mismatches, missing_crcs_in_cve, missing_crcs_in_symvers, matched_count, checked_count

# Paths to the files
cve_file = 'abi'
symvers_file = 'module.symvers'
sym_names_file = 'symbols'

# Parse the files
cve_symbols       = parse_cve(cve_file)
symvers_symbols   = parse_symvers(symvers_file)
target_symbols    = parse_sym_names(sym_names_file)

# Compare CRCs
(mismatches,
 missing_crcs_in_cve,
 missing_crcs_in_symvers,
 total_successful_matches,
 total_checked) = compare_crcs(cve_symbols, symvers_symbols, target_symbols)

# Output mismatched symbols
if mismatches or missing_crcs_in_cve or missing_crcs_in_symvers:
    if mismatches:
        print("Mismatched Symbols:")
        for symbol, (cve_crc, sym_crc) in mismatches.items():
            print(f"  ➜ Symbol: {symbol}")
            print(f"    ◉ CVE CRC:     {cve_crc}")
            print(f"    ◉ symvers CRC: {sym_crc}")
    else:
        print("No Mismatched Symbols Found.")

    print("Missing CRCs In CVE (But Found In Symvers):")
    for symbol in missing_crcs_in_cve:
        print(f"  ✦ Symbol: {symbol}")

    print("Missing CRCs Not Found In Symvers:")
    for symbol in missing_crcs_in_symvers:
        print(f"  ➤ Symbol: {symbol}")

total_mismatched            = len(mismatches)
total_missing_crcs_in_cve   = len(missing_crcs_in_cve)
total_missing_crcs_in_symvers = len(missing_crcs_in_symvers)
total_missing_crcs          = total_missing_crcs_in_cve + total_missing_crcs_in_symvers

# Print summary
print("Summary:")
label_width = 45
value_width = 5
print(f"{'Total Symbols Checked:':<{label_width}} {total_checked:>{value_width}}")
print(f"{'Total Successfully Matched CRCs:':<{label_width}} {total_successful_matches:>{value_width}}")
print(f"{'Total Mismatched Symbols:':<{label_width}} {total_mismatched:>{value_width}}")
print()
print(f"{'Total CRCs Missing:':<{label_width}} {total_missing_crcs:>{value_width}}")
print(f"{'Missing CRCs Found In CVE:':<{label_width}} {total_missing_crcs_in_cve:>{value_width}}")
print(f"{'Missing CRCs Not Found In Symvers:':<{label_width}} {total_missing_crcs_in_symvers:>{value_width}}")

# Ensure totals match
assert total_checked == (
    total_successful_matches
  + total_mismatched
  + total_missing_crcs_in_cve
  + total_missing_crcs_in_symvers
), "The totals do not match!"

# Exit if there are CRC mismatches
if mismatches:
    sys.exit("Exiting Due To CRC Mismatches")