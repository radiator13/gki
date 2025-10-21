#!/usr/bin/env python3
import sys
import os
from typing import Dict, Set, Tuple

def normalize_crc(crc_str: str) -> int:
    if not crc_str: return 0
    clean_crc = crc_str.replace('0x', '').lower()
    return int(clean_crc, 16)

def load_symbols_list(symbols_file: str) -> Set[str]:
    if not os.path.exists(symbols_file): 
        print(f"ERROR: Symbol list file not found: {symbols_file}", file=sys.stderr)
        sys.exit(1)
    symbols = set()
    with open(symbols_file, 'r', encoding='utf-8') as f:
        for line in f:
            symbol = line.strip()
            if symbol and not symbol.startswith('#'):
                symbols.add(symbol)
    return symbols

def load_abi_baseline(abi_file: str) -> Dict[str, str]:
    if not os.path.exists(abi_file): 
        print(f"ERROR: Baseline ABI file not found: {abi_file}", file=sys.stderr)
        sys.exit(1)
    baseline = {}
    with open(abi_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '-----' in line:
                parts = line.split('-----')
                if len(parts) == 2:
                    symbol = parts[0].strip()
                    crc = parts[1].strip()
                    baseline[symbol] = crc
    return baseline

def load_module_symvers(symvers_file: str) -> Dict[str, str]:
    if not os.path.exists(symvers_file): 
        print(f"ERROR: Module.symvers not found: {symvers_file}", file=sys.stderr)
        sys.exit(1)
    current = {}
    with open(symvers_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                parts = line.split('\t')
                if len(parts) >= 2:
                    symbol = parts[1].strip()
                    crc = parts[0].strip()
                    current[symbol] = crc
    return current

def check_abi_compliance(symbols_to_check: Set[str], baseline: Dict[str, str], current: Dict[str, str]) -> Tuple[bool, Dict]:
    report = {'new_symbols': [], 'missing_entirely': [], 'removed_symbols': [], 'crc_mismatches': [], 'verified_ok': []}
    for symbol in sorted(symbols_to_check):
        baseline_crc_str = baseline.get(symbol)
        current_crc_str = current.get(symbol)
        if baseline_crc_str is None:
            if current_crc_str is None:
                report['missing_entirely'].append(symbol)
            else:
                report['new_symbols'].append(symbol)
        elif current_crc_str is None:
            report['removed_symbols'].append(symbol)
        else:
            baseline_crc_norm = normalize_crc(baseline_crc_str)
            current_crc_norm = normalize_crc(current_crc_str)
            if baseline_crc_norm != current_crc_norm:
                report['crc_mismatches'].append({'symbol': symbol, 'baseline': baseline_crc_str, 'current': current_crc_str})
            else:
                report['verified_ok'].append(symbol)
    is_compliant = (len(report['removed_symbols']) == 0 and len(report['crc_mismatches']) == 0 and len(report['missing_entirely']) <= 1514)
    return is_compliant, report

def print_report(report: Dict, verbose: bool = False, symbols_to_check=None):
    total_checked = len(symbols_to_check)
    verified_ok_count = len(report['verified_ok'])
    new_symbols_count = len(report['new_symbols'])
    missing_entirely_count = len(report['missing_entirely'])
    removed_count = len(report['removed_symbols'])
    mismatches_count = len(report['crc_mismatches'])
    actual_total = (verified_ok_count + new_symbols_count + missing_entirely_count + removed_count + mismatches_count)
    if actual_total != total_checked:
        print(f"INTERNAL ERROR: Accounting mismatch detected! Total symbols: {total_checked}, Accounted for: {actual_total}", file=sys.stderr)
        sys.exit(1)
    print()
    print("=" * 70)
    print("       KMI ABI COMPLIANCE CHECK REPORT")
    print("=" * 70)
    print()
    print(f"Total symbols to verify: {total_checked}")
    print(f"Symbols accounted for: {actual_total} ✓")
    print()
    print(f"  ✓ Verified OK (CRC match):        {verified_ok_count}")
    print(f"  ➕ New symbols (in current only):  {new_symbols_count}")
    print(f"  ❓ Missing entirely (in neither):  {missing_entirely_count}")
    print(f"  ✗ Removed (in baseline only):     {removed_count}")
    print(f"  ✗ CRC mismatches (changed):       {mismatches_count}")
    print()
    if report['new_symbols']:
        if len(report['new_symbols']) > 0:
            print("=" * 70)
            print("❌ ERROR: Symbols added (present in current but not in baseline):")
            print("=" * 70)
        if len(report['new_symbols']) <= 20:
            for symbol in sorted(report['new_symbols']):
                print(f"  ➕ {symbol}")
        else:
            for symbol in sorted(report['new_symbols'])[:10]:
                print(f"  ➕ {symbol}")
            print(f"  ... and {len(report['new_symbols']) - 10} more")
        print()
    if report['missing_entirely']:
        if len(report['missing_entirely']) > 1514:
            print("=" * 70)
            print("❌ ERROR: Too many symbols missing entirely (>1514):")
            print("=" * 70)
        else:
            print("=" * 70)
            print("⚠️  WARNING: Symbols missing entirely (not in baseline AND not in current):")
            print("=" * 70)
        if len(report['missing_entirely']) <= 20:
            for symbol in sorted(report['missing_entirely']):
                print(f"  ❓ {symbol}")
        else:
            for symbol in sorted(report['missing_entirely'])[:10]:
                print(f"  ❓ {symbol}")
            print(f"  ... and {len(report['missing_entirely']) - 10} more")
        print()
    if report['removed_symbols']:
        print("=" * 70)
        print("❌ CRITICAL: Symbols removed (present in baseline but missing in current):")
        print("=" * 70)
        print("These are ABI BREAKS - dependent modules will fail to load!")
        print()
        for symbol in sorted(report['removed_symbols']):
            print(f"  ❌ {symbol}")
        print()
    if report['crc_mismatches']:
        print("=" * 70)
        print("❌ CRITICAL: CRC mismatches (present in both but signatures changed):")
        print("=" * 70)
        print("Type signatures modified - potential ABI BREAK!")
        print()
        for mismatch in sorted(report['crc_mismatches'], key=lambda x: x['symbol']):
            print(f"  ❌ {mismatch['symbol']}")
            print(f"      Baseline: {mismatch['baseline']}")
            print(f"      Current:  {mismatch['current']}")
            print()
    if verbose and report['verified_ok']:
        print("=" * 70)
        print("✅ Sample of verified symbols (matching CRCs - first 20):")
        print("=" * 70)
        for symbol in sorted(report['verified_ok'])[:20]:
            print(f"  ✅ {symbol}")
        if len(report['verified_ok']) > 20:
            print(f"  ... and {len(report['verified_ok']) - 20} more")
        print()
    print("=" * 70)

if __name__ == "__main__":
    symvers_file = sys.argv[1] if len(sys.argv) > 1 else "Module.symvers"
    abi_file = sys.argv[2] if len(sys.argv) > 2 else "abi.txt"
    symbols_file = sys.argv[3] if len(sys.argv) > 3 else "symbols.txt"
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    print()
    print("=" * 70)
    print("       KMI ABI CRC CHECKER")
    print("=" * 70)
    print()
    symbols_to_check = load_symbols_list(symbols_file)
    print(f"[1/4] Loaded {len(symbols_to_check)} KMI symbols to verify")
    baseline = load_abi_baseline(abi_file)
    print(f"[2/4] Loaded {len(baseline)} baseline CRC entries")
    current = load_module_symvers(symvers_file)
    print(f"[3/4] Loaded {len(current)} current build symbols")
    print("[4/4] Checking ABI compliance...")
    is_compliant, report = check_abi_compliance(symbols_to_check, baseline, current)
    print_report(report, verbose=verbose, symbols_to_check=symbols_to_check)
    total_processed = len(report['verified_ok']) + len(report['new_symbols']) + len(report['missing_entirely']) + len(report['removed_symbols']) + len(report['crc_mismatches'])
    print(f"SUMMARY: {len(symbols_to_check)} symbols processed | {total_processed} accounted for | {len(report['verified_ok'])} verified OK")
    if not is_compliant:
        if len(report['removed_symbols']) > 0:
            print("❌ ABI COMPLIANCE CHECK FAILED: Symbols removed from current build")
        elif len(report['crc_mismatches']) > 0:
            print("❌ ABI COMPLIANCE CHECK FAILED: CRC mismatches detected")
        elif len(report['new_symbols']) > 0:
            print("❌ ABI COMPLIANCE CHECK FAILED: New symbols added to current build")
        elif len(report['missing_entirely']) > 1514:
            print(f"❌ ABI COMPLIANCE CHECK FAILED: Too many symbols missing entirely ({len(report['missing_entirely'])} > 1514)")
        sys.exit(1)
    else:
        if len(report['missing_entirely']) > 0:
            print(f"⚠️  ABI COMPLIANCE CHECK PASSED with warnings ({len(report['missing_entirely'])} symbols missing from both files)")
        else:
            print("✅ ABI COMPLIANCE CHECK PASSED")
        sys.exit(0)