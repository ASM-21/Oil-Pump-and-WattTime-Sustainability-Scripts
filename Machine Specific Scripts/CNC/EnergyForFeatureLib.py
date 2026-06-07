import pandas as pd
import numpy as np
import glob
import os
from datetime import datetime
import re

class EnergyAnalyzer:
    """Energy analysis with full debugging and data cleaning"""
    
    def __init__(self):
        self.results = []
        self.validation = []
        self.data_quality = []
        self.raw_program_data = []
        self.operation_sequence = []
        self.setup_mappings()
        
    def setup_mappings(self):
        """UUID mappings"""
        self.partkind_to_program = {
            '5BC675E0-40F9-45BE-AE5C-CF7E8F493235': 'NONE',
            '072B393C-87F5-4183-9ABC-0870E4B4F53B': 'PROGRAM_1_Body', 
            'EDB34637-67D8-465A-AFBA-010AD86D34F6': 'PROGRAM_2_Body',
            '5E4A09CE-E1D5-4FCC-B912-38239DF9FDA0': 'PROGRAM_3_Body',
            'D2C78EB3-CB26-4FDA-ABA9-353C0E6A1AB1': 'PROGRAM_4_Body',
            '68C62535-3304-4629-A02B-85CAE2490743': 'PROGRAM_1_Lid',
            '7606F116-3463-4EEF-96CC-1AC408FAA001': 'PROGRAM_2_Lid'            
        }
        
        self.uuid_to_operation = {
            # Body operations
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
            'C382FC41-1DFF-4BFC-B0C3-D6E313A3F60D': 'TAPPING_NPT_BOTTOM',
            # Lid operations
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
            '482AB6CD-5B14-41D0-846D-4AF4A2EB712A': 'LID_CHAMFER_EDGES_AGAIN',
            'NONE': 'NONE'
        }
    
    def calculate_energy(self, times, powers, max_gap_sec=3.0):
        if len(times) < 2:
            return 0.0, 0.0, 0, 0
        
        total_energy = 0.0
        total_duration = 0.0
        n_segments = 0
        n_gaps = 0
        in_segment = False
        
        for i in range(len(times) - 1):
            dt = times[i + 1] - times[i]
            
            if dt <= max_gap_sec:
                dt_hrs = dt / 3600.0
                avg_power = (powers[i] + powers[i + 1]) / 2.0
                total_energy += avg_power * dt_hrs
                total_duration += dt
                if not in_segment:
                    n_segments += 1
                    in_segment = True
            else:
                n_gaps += 1
                in_segment = False
        
        return total_energy, total_duration, n_segments, n_gaps
    
    def parse_filename(self, filename):
        match = re.search(r'Al6061_(lid|body)(\d+)_p(\d+)', filename, re.IGNORECASE)
        if match:
            return {
                'part_type': match.group(1).capitalize(),
                'part_num': int(match.group(2)),
                'program_num': int(match.group(3)),
                'valid': True
            }
        return {'valid': False}
    
    def should_skip_file(self, filename):
        filename_lower = filename.lower()
        
        if 'error' in filename_lower:
            return True, "error file"
        
        if not filename_lower.startswith('al6061'):
            return True, "not Al6061"
        
        parsed = self.parse_filename(filename)
        if not parsed['valid']:
            return True, "invalid filename format"
        
        return False, None
    
    def check_data_quality(self, df, filename, parsed_info):
        issues = []
        
        power_data = df[df['Dataname'] == 'active power']['Value'].astype(float)
        
        if len(power_data) > 10:
            mean_p = power_data.mean()
            std_p = power_data.std()
            outliers = ((power_data > mean_p + 4*std_p) | (power_data < 0)).sum()
            if outliers > 0:
                issues.append(f"Power outliers: {outliers}")
        
        times = pd.to_datetime(df[df['Dataname'] == 'active power']['Time'])
        if len(times) > 1:
            diffs = times.diff().dt.total_seconds().dropna()
            large_gaps = (diffs > 5).sum()
            if large_gaps > 0:
                issues.append(f"Large gaps: {large_gaps}")
        
        self.data_quality.append({
            'File': filename,
            'Part_Type': parsed_info['part_type'],
            'Part_Num': parsed_info['part_num'],
            'Program_Num': parsed_info['program_num'],
            'Data_Points': len(power_data),
            'Issues': '; '.join(issues) if issues else 'OK'
        })
    
    def process_file(self, filepath):
        filename = os.path.basename(filepath)
        parsed = self.parse_filename(filename)
        
        try:
            df = pd.read_csv(filepath)
            self.check_data_quality(df, filename, parsed)
            
            process_data = df[df['Dataname'] == 'processKindId'].copy()
            part_data = df[df['Dataname'] == 'partKindId'].copy()
            power_data = df[df['Dataname'] == 'active power'].copy()
            
            if process_data.empty or part_data.empty or power_data.empty:
                return
            
            for d in [process_data, part_data, power_data]:
                d['Time'] = pd.to_datetime(d['Time'])
            
            merged = process_data[['Time', 'Value']].merge(
                part_data[['Time', 'Value']], on='Time', suffixes=('_proc', '_part')
            ).merge(
                power_data[['Time', 'Value']], on='Time'
            )
            merged.columns = ['Time', 'ProcessUUID', 'PartKindId', 'Power']
            
            merged['Power'] = pd.to_numeric(merged['Power'], errors='coerce').clip(lower=0)
            merged = merged.sort_values('Time').reset_index(drop=True)
            merged['Time_Sec'] = (merged['Time'] - merged['Time'].iloc[0]).dt.total_seconds()
            
            merged['Operation'] = merged['ProcessUUID'].str.strip().str.upper().map(
                lambda x: self.uuid_to_operation.get(x, f'UNKNOWN_{x[:8]}' if pd.notna(x) and len(str(x)) >= 8 else 'UNKNOWN')
            )
            merged['Program'] = merged['PartKindId'].str.strip().str.upper().map(
                lambda x: self.partkind_to_program.get(x, f'UNKNOWN_{x[:8]}' if pd.notna(x) and len(str(x)) >= 8 else 'UNKNOWN')
            )
            
            expected_part = parsed['part_type']
            expected_prog_num = parsed['program_num']
            expected_program = f'PROGRAM_{expected_prog_num}_{expected_part}'
            
            for program in merged['Program'].unique():
                if program == 'NONE' or program.startswith('UNKNOWN'):
                    continue
                if program != expected_program:
                    continue
                
                prog_data = merged[merged['Program'] == program].copy()
                
                prog_times = prog_data['Time_Sec'].values
                prog_powers = prog_data['Power'].values
                prog_energy, prog_duration, _, _ = self.calculate_energy(prog_times, prog_powers)
                
                op_energy_sum = 0.0
                none_energy = 0.0
                
                for operation in prog_data['Operation'].unique():
                    op_data = prog_data[prog_data['Operation'] == operation].sort_values('Time_Sec')
                    op_times = op_data['Time_Sec'].values
                    op_powers = op_data['Power'].values
                    
                    energy, duration, n_seg, n_gaps = self.calculate_energy(op_times, op_powers)
                    
                    if operation == 'NONE':
                        none_energy = energy
                        self.results.append({
                            'Part_Type': parsed['part_type'],
                            'Part_Num': parsed['part_num'],
                            'Program': program,
                            'Operation': 'NONE_IDLE',
                            'Energy_Wh': round(energy, 3),
                            'Duration_Sec': round(duration, 1),
                            'Avg_Power_W': round(energy / (duration/3600), 1) if duration > 0 else 0,
                            'Data_Points': len(op_times),
                            'Segments': n_seg,
                        })
                        continue
                    
                    op_energy_sum += energy
                    
                    self.results.append({
                        'Part_Type': parsed['part_type'],
                        'Part_Num': parsed['part_num'],
                        'Program': program,
                        'Operation': operation,
                        'Energy_Wh': round(energy, 3),
                        'Duration_Sec': round(duration, 1),
                        'Avg_Power_W': round(energy / (duration/3600), 1) if duration > 0 else 0,
                        'Data_Points': len(op_times),
                        'Segments': n_seg,
                    })
                
                transition_energy = prog_energy - op_energy_sum - none_energy
                
                if transition_energy > 0.01:
                    self.results.append({
                        'Part_Type': parsed['part_type'],
                        'Part_Num': parsed['part_num'],
                        'Program': program,
                        'Operation': 'TRANSITION_OVERHEAD',
                        'Energy_Wh': round(transition_energy, 3),
                        'Duration_Sec': 0,
                        'Avg_Power_W': 0,
                        'Data_Points': 0,
                        'Segments': 0,
                    })
                
                self.validation.append({
                    'File': filename,
                    'Part_Type': parsed['part_type'],
                    'Part_Num': parsed['part_num'],
                    'Program': program,
                    'Program_Total_Wh': round(prog_energy, 3),
                    'Operations_Wh': round(op_energy_sum, 3),
                    'NONE_Wh': round(none_energy, 3),
                    'Transition_Wh': round(transition_energy, 3),
                })
                
        except Exception as e:
            print(f"  Error processing {filename}: {e}")
    
    def analyze(self, directory='.'):
        csv_files = sorted(glob.glob(os.path.join(directory, '*.csv')))
        print(f"Found {len(csv_files)} CSV files\n")
        
        for f in csv_files:
            filename = os.path.basename(f)
            skip, reason = self.should_skip_file(filename)
            if skip:
                continue
            self.process_file(f)
        
        return pd.DataFrame(self.results), pd.DataFrame(self.validation), pd.DataFrame(self.data_quality)


def clean_data(results_df, validation_df):
    """
    Apply data cleaning rules based on debug analysis.
    Returns cleaned dataframe and cleaning report.
    """
    if results_df is None or results_df.empty:
        return None, None
    
    df = results_df.copy()
    original_count = len(df)
    cleaning_log = []
    
    # 1. Exclude bad parts (Part 17 Body has too many missing operations)
    bad_parts = [
        ('Body', 17),  # Missing 10+ operations
    ]
    for part_type, part_num in bad_parts:
        mask = (df['Part_Type'] == part_type) & (df['Part_Num'] == part_num)
        removed = mask.sum()
        if removed > 0:
            df = df[~mask]
            cleaning_log.append({
                'Rule': 'Bad Part Exclusion',
                'Details': f'{part_type} Part {part_num}',
                'Records_Removed': removed
            })
    
    # 2. Exclude UNKNOWN operations
    mask = df['Operation'].str.startswith('UNKNOWN')
    removed = mask.sum()
    if removed > 0:
        df = df[~mask]
        cleaning_log.append({
            'Rule': 'Unknown Operations',
            'Details': 'Operations starting with UNKNOWN',
            'Records_Removed': removed
        })
    
    # 3. Exclude records with insufficient data points (likely capture failures)
    min_data_points = {
        'SPOTTING_POCKET_HOLE': 2,
        'SPOTTING_CBORE': 2,
        'ENGRAVING': 3,
    }
    for op, min_pts in min_data_points.items():
        mask = (df['Operation'] == op) & (df['Data_Points'] < min_pts)
        removed = mask.sum()
        if removed > 0:
            df = df[~mask]
            cleaning_log.append({
                'Rule': 'Insufficient Data Points',
                'Details': f'{op} with < {min_pts} points',
                'Records_Removed': removed
            })
    
    # 4. Flag statistical outliers (>2.5 std from mean)
    df['Is_Outlier'] = False
    outlier_details = []
    
    for (part_type, program, operation), group in df.groupby(['Part_Type', 'Program', 'Operation']):
        if len(group) < 4 or operation in ['TRANSITION_OVERHEAD', 'NONE_IDLE']:
            continue
        
        mean = group['Energy_Wh'].mean()
        std = group['Energy_Wh'].std()
        
        if std == 0 or std / mean > 0.5:  # Skip if no variation or too noisy
            continue
        
        for idx, row in group.iterrows():
            deviation = (row['Energy_Wh'] - mean) / std
            if abs(deviation) > 2.5:
                df.loc[idx, 'Is_Outlier'] = True
                outlier_details.append(f"{part_type}/{program}/{operation} Part {row['Part_Num']}")
    
    outlier_count = df['Is_Outlier'].sum()
    if outlier_count > 0:
        cleaning_log.append({
            'Rule': 'Statistical Outliers',
            'Details': f'{outlier_count} records flagged (>2.5 std)',
            'Records_Removed': 0  # Flagged, not removed
        })
    
    cleaning_report = pd.DataFrame(cleaning_log)
    
    print(f"\nData Cleaning Summary:")
    print(f"  Original records: {original_count}")
    print(f"  After cleaning: {len(df)}")
    print(f"  Outliers flagged: {outlier_count}")
    
    return df, cleaning_report


def create_feature_library(df, include_overhead=False):
    """
    Create final feature library from cleaned data.
    """
    if df is None or df.empty:
        return None
    
    # Exclude outliers
    clean_df = df[df['Is_Outlier'] == False].copy()
    
    # Separate overhead operations
    overhead_ops = ['NONE_IDLE', 'TRANSITION_OVERHEAD']
    
    if include_overhead:
        feature_df = clean_df
    else:
        feature_df = clean_df[~clean_df['Operation'].isin(overhead_ops)]
    
    # Aggregate by operation
    feature_lib = feature_df.groupby(['Part_Type', 'Program', 'Operation']).agg(
        Energy_Wh=('Energy_Wh', 'mean'),
        Energy_Std=('Energy_Wh', 'std'),
        Energy_Min=('Energy_Wh', 'min'),
        Energy_Max=('Energy_Wh', 'max'),
        N_Runs=('Energy_Wh', 'count'),
        Duration_Sec=('Duration_Sec', 'mean'),
        Duration_Std=('Duration_Sec', 'std'),
        Avg_Power_W=('Avg_Power_W', 'mean'),
    ).round(3)
    
    # Add CV%
    feature_lib['CV_pct'] = (feature_lib['Energy_Std'] / feature_lib['Energy_Wh'] * 100).round(1)
    
    # Add 95% confidence interval
    feature_lib['CI_95'] = (1.96 * feature_lib['Energy_Std'] / np.sqrt(feature_lib['N_Runs'])).round(3)
    
    return feature_lib


def create_part_totals(df):
    """
    Calculate total energy per part (Body or Lid) for full LCA.
    """
    if df is None or df.empty:
        return None
    
    clean_df = df[df['Is_Outlier'] == False].copy()
    
    # Sum all operations (including overhead) per part
    part_totals = clean_df.groupby(['Part_Type', 'Part_Num']).agg(
        Total_Energy_Wh=('Energy_Wh', 'sum'),
        Total_Duration_Sec=('Duration_Sec', 'sum'),
        N_Operations=('Operation', 'count'),
    ).round(3)
    
    # Calculate stats by part type
    summary = part_totals.groupby('Part_Type').agg(
        Mean_Energy_Wh=('Total_Energy_Wh', 'mean'),
        Std_Energy_Wh=('Total_Energy_Wh', 'std'),
        Min_Energy_Wh=('Total_Energy_Wh', 'min'),
        Max_Energy_Wh=('Total_Energy_Wh', 'max'),
        N_Parts=('Total_Energy_Wh', 'count'),
    ).round(3)
    
    summary['CV_pct'] = (summary['Std_Energy_Wh'] / summary['Mean_Energy_Wh'] * 100).round(1)
    
    return part_totals, summary


def create_program_totals(df):
    """
    Calculate total energy per program for comparison with ecoinvent.
    """
    if df is None or df.empty:
        return None
    
    clean_df = df[df['Is_Outlier'] == False].copy()
    
    # Sum per program per part
    prog_totals = clean_df.groupby(['Part_Type', 'Part_Num', 'Program']).agg(
        Program_Energy_Wh=('Energy_Wh', 'sum'),
        Program_Duration_Sec=('Duration_Sec', 'sum'),
    ).reset_index()
    
    # Stats by program
    summary = prog_totals.groupby(['Part_Type', 'Program']).agg(
        Mean_Energy_Wh=('Program_Energy_Wh', 'mean'),
        Std_Energy_Wh=('Program_Energy_Wh', 'std'),
        N_Runs=('Program_Energy_Wh', 'count'),
    ).round(3)
    
    summary['CV_pct'] = (summary['Std_Energy_Wh'] / summary['Mean_Energy_Wh'] * 100).round(1)
    
    return summary


def main():
    directory = input("Enter directory path (Enter for current): ").strip() or "."
    
    # Analyze
    analyzer = EnergyAnalyzer()
    results, validation, quality = analyzer.analyze(directory)
    
    if results is None or results.empty:
        print("No results generated")
        return
    
    # Clean
    cleaned, cleaning_report = clean_data(results, validation)
    
    # Create outputs
    feature_lib = create_feature_library(cleaned, include_overhead=False)
    overhead_lib = create_feature_library(cleaned[cleaned['Operation'].isin(['NONE_IDLE', 'TRANSITION_OVERHEAD'])], include_overhead=True)
    part_totals, part_summary = create_part_totals(cleaned)
    program_summary = create_program_totals(cleaned)
    
    # Display
    print("\n" + "="*70)
    print("FEATURE LIBRARY (Clean, No Overhead)")
    print("="*70)
    print(feature_lib.to_string())
    
    print("\n" + "="*70)
    print("PART TOTALS SUMMARY")
    print("="*70)
    print(part_summary.to_string())
    
    print("\n" + "="*70)
    print("PROGRAM TOTALS SUMMARY")
    print("="*70)
    print(program_summary.to_string())
    
    # Save
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outfile = f"feature_library_final_{timestamp}.xlsx"
    
    with pd.ExcelWriter(outfile, engine='openpyxl') as writer:
        # Main deliverables
        feature_lib.to_excel(writer, sheet_name='Feature_Library')
        
        if overhead_lib is not None and not overhead_lib.empty:
            overhead_lib.to_excel(writer, sheet_name='Overhead_Library')
        
        part_summary.to_excel(writer, sheet_name='Part_Summary')
        program_summary.to_excel(writer, sheet_name='Program_Summary')
        
        # Supporting data
        part_totals.to_excel(writer, sheet_name='Part_Totals_Detail')
        cleaned.to_excel(writer, sheet_name='Cleaned_Data', index=False)
        cleaning_report.to_excel(writer, sheet_name='Cleaning_Log', index=False)
        
        # Pivot for easy viewing
        pivot = cleaned[~cleaned['Operation'].isin(['NONE_IDLE', 'TRANSITION_OVERHEAD']) & ~cleaned['Is_Outlier']].pivot_table(
            index=['Part_Type', 'Program', 'Operation'],
            columns='Part_Num',
            values='Energy_Wh',
            aggfunc='first'
        )
        pivot.to_excel(writer, sheet_name='Energy_Pivot')
        
        # Validation
        validation.to_excel(writer, sheet_name='Validation', index=False)
    
    print(f"\nSaved to: {outfile}")
    print("\nKey sheets:")
    print("  - Feature_Library: Energy per operation (for LCA)")
    print("  - Part_Summary: Total energy per Body/Lid")
    print("  - Program_Summary: Energy by CNC program")
    print("  - Overhead_Library: NONE_IDLE + TRANSITION stats")


if __name__ == "__main__":
    main()