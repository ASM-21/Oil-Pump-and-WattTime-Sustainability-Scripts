import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import glob
import re
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

class EnergyTerminalAnalyzer:
    """
    Terminal-only energy analyzer that compares program UUID energy vs total CSV energy
    Provides detailed breakdowns and flags multi-program files
    """
    
    def __init__(self, debug=True):
        self.debug = debug
        self.uuid_to_operation = {}
        self.partkind_to_program = {}
        self.program_uuid_map = {}
        self.file_analysis_results = []  # Store results from each file
        self.setup_partkind_mapping()
        self.setup_uuid_operation_mapping()
        
    def setup_partkind_mapping(self):
        """Setup hardcoded partKindId to program mapping"""
        self.partkind_to_program = {
            '5BC675E0-40F9-45BE-AE5C-CF7E8F493235': 'NONE',
            '072B393C-87F5-4183-9ABC-0870E4B4F53B': 'PROGRAM_1_Body', 
            'EDB34637-67D8-465A-AFBA-010AD86D34F6': 'PROGRAM_2_Body',
            '5E4A09CE-E1D5-4FCC-B912-38239DF9FDA0': 'PROGRAM_3_Body',
            'D2C78EB3-CB26-4FDA-ABA9-353C0E6A1AB1': 'PROGRAM_4_Body',
            '68C62535-3304-4629-A02B-85CAE2490743': 'PROGRAM_1_Lid',
            '7606F116-3463-4EEF-96CC-1AC408FAA001': 'PROGRAM_2_Lid'            
        }
        
        for uuid, program in self.partkind_to_program.items():
            self.program_uuid_map[program] = uuid
        
        self.log(f"Setup partKindId mapping for {len(self.partkind_to_program)} programs")
    
    def setup_uuid_operation_mapping(self):
        """Setup hardcoded UUID to operation mapping"""
        body_operations = {
            'C874D6A3-7A89-44E1-B0D4-6783FF55F19D': 'CAVITY_MILL_OUTSIDE',
            '7A0C0A5C-9BBB-42CC-9C34-897E84D4F9BA': 'CAVITY_MILL_INSIDE',
            'B893297A-D47C-4029-BAF0-218F58387DFF': 'SPOTTING_LID_HOLES',
            '962A9D60-A315-4D3B-BF12-FDAA9EFBF2AF': 'SPOTTING_LH',
            'DB204000-40E6-4720-8721-98173D9A37FF': 'SPOTTING_CBORE',
            '5A4B2394-640B-4ADA-BBB7-717B839D0E6F': 'SPOTTING_POCKET_HOLE',
            '527F92C5-9C39-48DD-A37F-86E1D81497FC': 'DRILLING_LID_HOLES',
            '70AA639A-4325-448F-BFFB-D5EE218DA38C': 'TAPPING_LID_HOLES',
            '3D1978A5-7663-4DAA-A0D2-3995EBB1B582': 'DRILLING_LH',
            'F0FA6A59-3010-44CC-BFFF-4A4F04B7A39B': 'DRILLING_POCKET_HOLE',
            '9D44D6BA-0640-4530-8725-2069F885B77C': 'DRILLING_CBORE',
            'BEC9A210-A8D4-41B7-A2DC-32E6FCAE8291': 'FINISH_POCKET_HOLE',
            'F3339F2A-EF90-4511-8ABF-3917196A2E76': 'FINISH_CBORE',
            '02F78302-5F12-474A-A693-A8328EE54864': 'FACE_DATUM_A',
            'CF5DB674-3928-4BAA-A4E6-695A35019B38': 'FACE_TOP_PLANE',
            '7203BEC1-4B64-4F7F-BD5B-092BF23AA2C2': 'FINISH_OUTER_WALL',
            'D26C121D-4255-454F-9BFF-BC3FE92091D3': 'FINISH_OUTER_PROFILE',
            '02682EDC-F0B9-4AD5-A930-C5E08AA9FC0E': 'FINISH_INNER_PROFILE',
            '0B601775-6267-421A-9EA6-DD4531A80D99': 'WALL_FLOOR_PROFILING',
            'DE045126-2C5E-4E72-8491-E202079EAC7C': 'PLANAR_DEBURRING',
            '1925A9DD-E557-4ED5-A106-DA5F7D08FBE5': 'PLANAR_PROFILING_AGAIN',
            'AF6B782E-23DD-4144-8665-11C813BE7660': 'FLOOR_FACING',
            '6A897FFD-29C0-423B-A692-D9CCB0612FB0': 'FACE_TOP_PLANE_COPY',
            '89918109-7350-48A4-A5F9-AE742269E029': 'PLANAR_PROFILING_AGAIN_COPY',
            'C14415F1-CFEE-431E-92CB-E7F5CB809961': 'ENGRAVING',
            '27D6DC59-16BC-4185-AA97-4E474C98E615': 'SPOTTING_NPT_TOP',
            '94AE40F8-AC19-405A-A87C-42158C42D530': 'DRILLING_NPT_TOP',
            '3C44659E-1CC5-4F24-88FD-04F834435743': 'TAPPING_NPT_TOP',
            'CF0FEA34-836B-413B-B472-DF89D832DA95': 'SPOTTING_NPT_BOTTOM',
            '465E99DA-B681-4FD4-894C-3B1EF84592C2': 'DRILLING_NPT_BOTTOM',
            'C382FC41-1DFF-4BFC-B0C3-D6E313A3F60D': 'TAPPING_NPT_BOTTOM'
        }
        
        lid_operations = {
            '3C7357E5-BC37-4F42-861A-CF4E44BF79B6': 'LID_CAVITY_MILL',
            '34B5F4DD-FB2F-4F6A-83A1-0A5CD0F47697': 'LID_SPOTTING_HOLES',
            '5D29409C-31B1-4B6B-A5DB-7F9F6AE3D06D': 'LID_DRILLING_HOLES',
            'E17C1DE6-D8A5-4D60-BFB2-DCB7EF2BAC8C': 'LID_FINISH_SURFACES',
            'A06C758F-7E20-4B57-997A-E14283E11DC5': 'LID_FINISH_UPPER_WALL',
            'B5414A60-078F-49C6-BA61-FED2768D3C8D': 'LID_FINISH_OUTER_PROFILE',
            '5D1DD6BB-EB5D-41B4-98B2-77D314F4455E': 'LID_CHAMFER_EDGES',
            '1BFABEA4-68A9-484B-AE13-2E0BF9278D50': 'LID_FLOOR_FACING',
            'C5A68CD3-BCDF-4119-B596-9FAC41AAB033': 'LID_SPOTTING_SHAFT_HOLES',
            '0279764B-BF92-4F75-8255-A1BD34484848': 'LID_DRILLING_SHAFT_HOLES',
            'E5EDCE94-46C8-449C-9FA0-71F22978959A': 'LID_HOLE_MILLING',
            'D99BADF2-7704-48EB-B36B-2AF891BF9D78': 'LID_FINISH_FACE',
            'F9707002-75F7-45CD-B115-64EB377603B0': 'LID_POCKETING',
            '482AB6CD-5B14-41D0-846D-4AF4A2EB712A': 'LID_CHAMFER_EDGES_AGAIN'
        }
        
        duplicate_handling = {
            'DE045126-2C5E-4E72-8491-E202079EAC7C': 'DEBURRING',
            'C14415F1-CFEE-431E-92CB-E7F5CB809961': 'ENGRAVING'
        }
        
        self.uuid_to_operation = {}
        self.uuid_to_operation.update(body_operations)
        
        for uuid, operation in lid_operations.items():
            if uuid not in duplicate_handling:
                self.uuid_to_operation[uuid] = operation
        
        self.uuid_to_operation.update(duplicate_handling)
        self.uuid_to_operation['NONE'] = 'NONE'
        
        self.log(f"Setup UUID to operation mapping for {len(self.uuid_to_operation)} operations")
        
    def log(self, message):
        """Simple logging for debugging"""
        if self.debug:
            print(f"[DEBUG] {message}")
    
    def analyze_single_file(self, csv_filepath):
        """
        Analyze a single CSV file and return comprehensive energy breakdown
        """
        basename = os.path.basename(csv_filepath)
        
        print(f"\n{'='*100}")
        print(f"ANALYZING FILE: {basename}")
        print(f"{'='*100}")
        
        try:
            csv_data = pd.read_csv(csv_filepath)
            csv_data['Time'] = pd.to_datetime(csv_data['Time'])
            print(f"✓ Loaded CSV with {len(csv_data)} rows")
        except Exception as e:
            print(f"✗ ERROR loading {basename}: {e}")
            return None
        
        # Extract data streams
        processkindid_data = csv_data[csv_data['Dataname'] == 'processKindId'].copy()
        partkindid_data = csv_data[csv_data['Dataname'] == 'partKindId'].copy()
        power_data = csv_data[csv_data['Dataname'] == 'active power'].copy()
        
        if processkindid_data.empty or partkindid_data.empty or power_data.empty:
            print(f"✗ WARNING: Missing required data streams in {basename}")
            return None
        
        print(f"✓ Found processKindId: {len(processkindid_data)} rows")
        print(f"✓ Found partKindId: {len(partkindid_data)} rows")
        print(f"✓ Found active power: {len(power_data)} rows")
        
        # Prepare data
        processkindid_data = processkindid_data[['Time', 'Value']].rename(columns={'Value': 'UUID'})
        partkindid_data = partkindid_data[['Time', 'Value']].rename(columns={'Value': 'PartKindId'})
        power_data = power_data[['Time', 'Value']].rename(columns={'Value': 'Power_W'})
        
        power_data['Power_W'] = pd.to_numeric(power_data['Power_W'], errors='coerce')
        power_data['Power_W'] = power_data['Power_W'].clip(lower=0)
        
        # Merge data
        timeline_data = pd.merge(processkindid_data, partkindid_data, on='Time', how='inner')
        timeline_data = pd.merge(timeline_data, power_data, on='Time', how='inner')
        timeline_data = timeline_data.sort_values('Time').reset_index(drop=True)
        
        # Calculate energy
        timeline_data['time_diff_hours'] = timeline_data['Time'].diff().dt.total_seconds() / 3600
        timeline_data = timeline_data.iloc[1:].reset_index(drop=True)
        timeline_data['energy_kwh'] = timeline_data['Power_W'] * timeline_data['time_diff_hours'] / 1000
        
        # Calculate TOTAL energy in CSV
        total_energy_csv = timeline_data['energy_kwh'].sum()
        
        print(f"\n{'-'*100}")
        print(f"TOTAL ENERGY IN CSV FILE: {total_energy_csv:.6f} kWh")
        print(f"{'-'*100}")
        
        # Normalize UUIDs for matching
        timeline_data['PartKindId_Upper'] = timeline_data['PartKindId'].str.strip().str.upper()
        timeline_data['UUID_Upper'] = timeline_data['UUID'].str.strip().str.upper()
        
        # Identify all unique program UUIDs in this file
        unique_program_uuids = timeline_data['PartKindId_Upper'].unique()
        
        # Map to program names
        programs_found = []
        unknown_programs = []
        
        for uuid in unique_program_uuids:
            program_name = None
            for known_uuid, prog_name in self.partkind_to_program.items():
                if uuid == known_uuid.upper():
                    program_name = prog_name
                    break
            
            if program_name:
                programs_found.append((uuid, program_name))
            else:
                unknown_programs.append(uuid)
        
        # FLAG: Check if multiple programs in one file
        non_none_programs = [p for _, p in programs_found if p != 'NONE']
        
        print(f"\nPROGRAM UUIDs FOUND IN FILE:")
        print(f"{'-'*100}")
        
        if len(non_none_programs) > 1:
            print(f"⚠️  WARNING: MULTIPLE PROGRAMS DETECTED IN SINGLE FILE!")
            print(f"⚠️  Expected 1 program per file, found {len(non_none_programs)}")
        
        for uuid, program_name in programs_found:
            count = len(timeline_data[timeline_data['PartKindId_Upper'] == uuid])
            print(f"  • {program_name:30s} (UUID: {uuid}) - {count} data points")
        
        if unknown_programs:
            print(f"\n  ⚠️  UNKNOWN PROGRAM UUIDs:")
            for uuid in unknown_programs:
                count = len(timeline_data[timeline_data['PartKindId_Upper'] == uuid])
                print(f"     • {uuid} - {count} data points")
        
        # Energy breakdown by program UUID
        print(f"\n{'-'*100}")
        print(f"ENERGY BREAKDOWN BY PROGRAM UUID:")
        print(f"{'-'*100}")
        
        program_energy_breakdown = {}
        
        for uuid, program_name in programs_found:
            program_data = timeline_data[timeline_data['PartKindId_Upper'] == uuid]
            program_energy = program_data['energy_kwh'].sum()
            percentage = (program_energy / total_energy_csv * 100) if total_energy_csv > 0 else 0
            
            program_energy_breakdown[program_name] = {
                'energy_kwh': program_energy,
                'percentage': percentage,
                'uuid': uuid
            }
            
            print(f"  {program_name:30s}: {program_energy:10.6f} kWh ({percentage:6.2f}%)")
        
        # Unknown program energy
        unknown_energy = 0
        for uuid in unknown_programs:
            unknown_data = timeline_data[timeline_data['PartKindId_Upper'] == uuid]
            unknown_energy += unknown_data['energy_kwh'].sum()
        
        if unknown_energy > 0:
            percentage = (unknown_energy / total_energy_csv * 100) if total_energy_csv > 0 else 0
            print(f"  {'UNKNOWN PROGRAMS':30s}: {unknown_energy:10.6f} kWh ({percentage:6.2f}%)")
        
        # Operation breakdown for each program
        print(f"\n{'-'*100}")
        print(f"DETAILED OPERATION BREAKDOWN BY PROGRAM:")
        print(f"{'-'*100}")
        
        for uuid, program_name in programs_found:
            if program_name == 'NONE':
                continue
                
            program_data = timeline_data[timeline_data['PartKindId_Upper'] == uuid].copy()
            
            if program_data.empty:
                continue
            
            print(f"\n  {program_name}:")
            print(f"  {'-'*95}")
            
            # Map operations
            program_data['Operation'] = program_data['UUID_Upper'].apply(
                lambda x: self.uuid_to_operation.get(x, 'Unknown')
            )
            
            # Group by operation
            operation_summary = program_data.groupby('Operation')['energy_kwh'].agg(['sum', 'count']).reset_index()
            operation_summary = operation_summary.sort_values('sum', ascending=False)
            
            total_program_energy = program_data['energy_kwh'].sum()
            
            unknown_ops_energy = 0
            
            for _, row in operation_summary.iterrows():
                op_name = row['Operation']
                op_energy = row['sum']
                op_count = row['count']
                op_percentage = (op_energy / total_program_energy * 100) if total_program_energy > 0 else 0
                
                if op_name == 'Unknown':
                    unknown_ops_energy = op_energy
                    print(f"    ⚠️  {op_name:40s}: {op_energy:10.6f} kWh ({op_percentage:6.2f}%) [{op_count:4d} points]")
                else:
                    print(f"    • {op_name:40s}: {op_energy:10.6f} kWh ({op_percentage:6.2f}%) [{op_count:4d} points]")
            
            # Show unknown operation UUIDs if any
            if unknown_ops_energy > 0:
                unknown_ops = program_data[program_data['Operation'] == 'Unknown']['UUID_Upper'].unique()
                print(f"\n    UNKNOWN OPERATION UUIDs:")
                for unknown_uuid in unknown_ops:
                    unknown_op_data = program_data[program_data['UUID_Upper'] == unknown_uuid]
                    unknown_op_energy = unknown_op_data['energy_kwh'].sum()
                    print(f"      • {unknown_uuid}: {unknown_op_energy:.6f} kWh")
        
        # Summary statistics
        print(f"\n{'-'*100}")
        print(f"FILE SUMMARY:")
        print(f"{'-'*100}")
        print(f"  Total Energy (CSV):          {total_energy_csv:.6f} kWh")
        print(f"  Programs Found:              {len(programs_found)}")
        print(f"  Non-NONE Programs:           {len(non_none_programs)}")
        if len(non_none_programs) > 1:
            print(f"  ⚠️  MULTI-PROGRAM WARNING:     YES - Expected 1, Found {len(non_none_programs)}")
        else:
            print(f"  ✓ Single Program:            YES")
        print(f"  Unknown Programs:            {len(unknown_programs)}")
        
        # Return results for aggregation
        result = {
            'filename': basename,
            'total_energy': total_energy_csv,
            'programs_found': programs_found,
            'program_energy': program_energy_breakdown,
            'unknown_programs': unknown_programs,
            'unknown_energy': unknown_energy,
            'multi_program_warning': len(non_none_programs) > 1
        }
        
        return result
    
    def analyze_directory(self, directory, pattern="*.csv"):
        """
        Analyze all CSV files in directory
        """
        print(f"\n{'#'*100}")
        print(f"# ENERGY TERMINAL ANALYZER - DIRECTORY ANALYSIS")
        print(f"{'#'*100}")
        print(f"Directory: {os.path.abspath(directory)}")
        print(f"Pattern: {pattern}")
        
        # Find all CSV files
        search_pattern = os.path.join(directory, pattern)
        all_files = glob.glob(search_pattern)
        
        # Filter out files starting with "Idle" or "Drive"
        files = []
        excluded_files = []
        for filepath in all_files:
            basename = os.path.basename(filepath)
            if basename.startswith('Idle') or basename.startswith('Drive'):
                excluded_files.append(basename)
            else:
                files.append(filepath)
        
        files.sort()
        
        if excluded_files:
            print(f"\n✓ Excluded {len(excluded_files)} files (starting with 'Idle' or 'Drive'):")
            for filename in sorted(excluded_files)[:10]:  # Show first 10
                print(f"    • {filename}")
            if len(excluded_files) > 10:
                print(f"    ... and {len(excluded_files) - 10} more")
        
        if not files:
            print(f"\n✗ No CSV files found matching pattern: {search_pattern}")
            return False
        
        print(f"\n✓ Found {len(files)} CSV files to analyze")
        
        # Analyze each file
        self.file_analysis_results = []
        
        for i, filepath in enumerate(files, 1):
            print(f"\n\n{'#'*100}")
            print(f"# FILE {i} of {len(files)}")
            print(f"{'#'*100}")
            
            result = self.analyze_single_file(filepath)
            
            if result:
                self.file_analysis_results.append(result)
        
        # Print aggregated summary
        if self.file_analysis_results:
            self.print_aggregated_summary()
        
        return True
    
    def print_aggregated_summary(self):
        """
        Print aggregated summary across all analyzed files
        """
        print(f"\n\n{'#'*100}")
        print(f"# AGGREGATED SUMMARY ACROSS ALL FILES")
        print(f"{'#'*100}")
        
        total_files = len(self.file_analysis_results)
        total_energy_all_files = sum(r['total_energy'] for r in self.file_analysis_results)
        
        print(f"\nTotal Files Analyzed: {total_files}")
        print(f"Total Energy (All CSV Files): {total_energy_all_files:.6f} kWh")
        
        # Multi-program warnings
        multi_program_files = [r for r in self.file_analysis_results if r.get('multi_program_warning', False)]
        if multi_program_files:
            print(f"\n⚠️  WARNING: {len(multi_program_files)} files contain MULTIPLE PROGRAMS:")
            for result in multi_program_files:
                print(f"    • {result['filename']}")
        
        # Aggregate by program
        print(f"\n{'-'*100}")
        print(f"AGGREGATED ENERGY BY PROGRAM (across all files):")
        print(f"{'-'*100}")
        
        program_totals = {}
        
        for result in self.file_analysis_results:
            for program_name, data in result['program_energy'].items():
                if program_name not in program_totals:
                    program_totals[program_name] = {
                        'total_energy': 0,
                        'file_count': 0
                    }
                program_totals[program_name]['total_energy'] += data['energy_kwh']
                program_totals[program_name]['file_count'] += 1
        
        # Sort by energy
        sorted_programs = sorted(program_totals.items(), key=lambda x: x[1]['total_energy'], reverse=True)
        
        # Calculate total energy attributed to all programs
        total_program_energy = 0
        for program_name, data in sorted_programs:
            percentage = (data['total_energy'] / total_energy_all_files * 100) if total_energy_all_files > 0 else 0
            avg_per_file = data['total_energy'] / data['file_count'] if data['file_count'] > 0 else 0
            print(f"  {program_name:30s}: {data['total_energy']:10.6f} kWh ({percentage:6.2f}%) "
                  f"[{data['file_count']:3d} files, avg: {avg_per_file:.6f} kWh/file]")
            total_program_energy += data['total_energy']
        
        # Unknown programs aggregated
        total_unknown_energy = sum(r.get('unknown_energy', 0) for r in self.file_analysis_results)
        if total_unknown_energy > 0:
            percentage = (total_unknown_energy / total_energy_all_files * 100) if total_energy_all_files > 0 else 0
            print(f"  {'UNKNOWN PROGRAMS':30s}: {total_unknown_energy:10.6f} kWh ({percentage:6.2f}%)")
        
        # COMPARISON: Program UUID Energy vs Total CSV Energy
        print(f"\n{'-'*100}")
        print(f"PROGRAM UUID ENERGY vs TOTAL CSV ENERGY COMPARISON:")
        print(f"{'-'*100}")
        
        unaccounted_energy = total_energy_all_files - total_program_energy
        accounted_percentage = (total_program_energy / total_energy_all_files * 100) if total_energy_all_files > 0 else 0
        unaccounted_percentage = (unaccounted_energy / total_energy_all_files * 100) if total_energy_all_files > 0 else 0
        
        print(f"  Total Energy in All CSV Files:      {total_energy_all_files:10.6f} kWh (100.00%)")
        print(f"  Total Energy from Program UUIDs:    {total_program_energy:10.6f} kWh ({accounted_percentage:6.2f}%)")
        print(f"  Unaccounted Energy:                  {unaccounted_energy:10.6f} kWh ({unaccounted_percentage:6.2f}%)")
        
        if total_unknown_energy > 0:
            print(f"\n  Note: Unaccounted energy includes:")
            print(f"    • Unknown Program UUIDs:           {total_unknown_energy:10.6f} kWh ({(total_unknown_energy/total_energy_all_files*100):6.2f}%)")
            other_unaccounted = unaccounted_energy - total_unknown_energy
            if other_unaccounted > 0:
                print(f"    • Other (gaps, transitions, etc.): {other_unaccounted:10.6f} kWh ({(other_unaccounted/total_energy_all_files*100):6.2f}%)")
        
        if unaccounted_percentage > 10:
            print(f"\n  ⚠️  WARNING: {unaccounted_percentage:.2f}% of total energy is unaccounted!")
            print(f"     This may indicate data quality issues or missing UUID mappings.")
        elif unaccounted_percentage > 5:
            print(f"\n  ⚠️  Note: {unaccounted_percentage:.2f}% of energy is unaccounted (within typical range)")
        else:
            print(f"\n  ✓ Good: Only {unaccounted_percentage:.2f}% of energy is unaccounted")
        
        # Files by program
        print(f"\n{'-'*100}")
        print(f"FILES BY PROGRAM:")
        print(f"{'-'*100}")
        
        program_files = {}
        for result in self.file_analysis_results:
            for program_name in result['program_energy'].keys():
                if program_name not in program_files:
                    program_files[program_name] = []
                program_files[program_name].append(result['filename'])
        
        for program_name in sorted(program_files.keys()):
            print(f"\n  {program_name} ({len(program_files[program_name])} files):")
            for filename in sorted(program_files[program_name]):
                print(f"    • {filename}")
        
        print(f"\n{'#'*100}")
        print(f"# ANALYSIS COMPLETE")
        print(f"{'#'*100}")


def main():
    """
    Main function - terminal output only
    """
    print("="*100)
    print("ENERGY TERMINAL ANALYZER")
    print("Compares program UUID energy vs total CSV energy")
    print("Terminal output only - no figures generated")
    print("="*100)
    
    # Initialize analyzer
    analyzer = EnergyTerminalAnalyzer(debug=False)
    
    # Get directory
    directory = input("\nEnter directory path (or press Enter for current directory): ").strip()
    if not directory:
        directory = "."
    
    if not os.path.exists(directory):
        print(f"ERROR: Directory not found: {directory}")
        return
    
    # Get file pattern
    pattern = input("Enter file pattern (default: *.csv): ").strip()
    if not pattern:
        pattern = "*.csv"
    
    # Run analysis
    analyzer.analyze_directory(directory, pattern)


if __name__ == "__main__":
    main()