"""
Enhanced Energy Analyzer v2
Improvements:
- Operation archetype classification for CAM generalizability
- Normalized energy metrics (Wh/sec, Wh/mm travel)
- Tool-based energy analysis
- Power profile characterization (ramp-up, steady-state)
- Correlation heatmaps and distribution plots
- CAM-ready lookup table export

Author: Andrew (IN-MaC Research)
"""

import pandas as pd
import numpy as np
import glob
import os
from datetime import datetime
import re
import json
import warnings
warnings.filterwarnings('ignore')

# Try importing plotting libraries
try:
    import matplotlib.pyplot as plt
    import seaborn as sns
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False
    print("Note: matplotlib/seaborn not available - skipping plots")

# =============================================================================
# OPERATION ARCHETYPE DEFINITIONS
# =============================================================================
# Maps operation names to standardized categories for CAM generalization

OPERATION_ARCHETYPES = {
    # Roughing operations - high MRR, lower precision
    'CAVITY_MILL_OUTSIDE': 'ROUGH_MILL',
    'CAVITY_MILL_INSIDE': 'ROUGH_MILL', 
    'LID_CAVITY_MILL': 'ROUGH_MILL',
    'LID_POCKETING': 'ROUGH_MILL',
    
    # Facing operations - surface preparation
    'FACE_DATUM_A': 'FACING',
    'FACE_TOP_PLANE': 'FACING',
    'FACE_TOP_PLANE_COPY': 'FACING',
    'FLOOR_FACING': 'FACING',
    'LID_FLOOR_FACING': 'FACING',
    'LID_FINISH_FACE': 'FACING',
    
    # Finishing operations - high precision, lower MRR
    'FINISH_OUTER_WALL': 'FINISH_MILL',
    'FINISH_OUTER_PROFILE': 'FINISH_MILL',
    'FINISH_INNER_PROFILE': 'FINISH_MILL',
    'FINISH_POCKET_HOLE': 'FINISH_MILL',
    'FINISH_CBORE': 'FINISH_MILL',
    'LID_FINISH_SURFACES': 'FINISH_MILL',
    'LID_FINISH_UPPER_WALL': 'FINISH_MILL',
    'LID_FINISH_OUTER_PROFILE': 'FINISH_MILL',
    
    # Profiling/contouring
    'WALL_FLOOR_PROFILING': 'PROFILING',
    'PLANAR_PROFILING_AGAIN': 'PROFILING',
    'PLANAR_PROFILING_AGAIN_COPY': 'PROFILING',
    
    # Deburring/chamfering - light cuts
    'PLANAR_DEBURRING': 'DEBURR_CHAMFER',
    'LID_CHAMFER_EDGES': 'DEBURR_CHAMFER',
    'LID_CHAMFER_EDGES_AGAIN': 'DEBURR_CHAMFER',
    
    # Spot drilling - short, high speed
    'SPOTTING_LID_HOLES': 'SPOT_DRILL',
    'SPOTTING_LH': 'SPOT_DRILL',
    'SPOTTING_CBORE': 'SPOT_DRILL',
    'SPOTTING_POCKET_HOLE': 'SPOT_DRILL',
    'SPOTTING_NPT_TOP': 'SPOT_DRILL',
    'SPOTTING_NPT_BOTTOM': 'SPOT_DRILL',
    'LID_SPOTTING_HOLES': 'SPOT_DRILL',
    'LID_SPOTTING_SHAFT_HOLES': 'SPOT_DRILL',
    
    # Drilling - peck cycles
    'DRILLING_LID_HOLES': 'DRILLING',
    'DRILLING_LH': 'DRILLING',
    'DRILLING_POCKET_HOLE': 'DRILLING',
    'DRILLING_CBORE': 'DRILLING',
    'DRILLING_NPT_TOP': 'DRILLING',
    'DRILLING_NPT_BOTTOM': 'DRILLING',
    'LID_DRILLING_HOLES': 'DRILLING',
    'LID_DRILLING_SHAFT_HOLES': 'DRILLING',
    
    # Tapping - constant torque
    'TAPPING_LID_HOLES': 'TAPPING',
    'TAPPING_NPT_TOP': 'TAPPING',
    'TAPPING_NPT_BOTTOM': 'TAPPING',
    
    # Hole milling - circular interpolation
    'LID_HOLE_MILLING': 'HOLE_MILL',
    
    # Engraving - very light, high speed
    'ENGRAVING': 'ENGRAVING',
    
    # Idle/transition
    'NONE_IDLE': 'IDLE',
    'TRANSITION_OVERHEAD': 'TRANSITION',
}

# Spindle speed bands for categorization
def get_spindle_band(rpm):
    """Categorize spindle speed into bands"""
    if pd.isna(rpm) or rpm <= 0:
        return 'UNKNOWN'
    elif rpm < 3000:
        return 'LOW_RPM'
    elif rpm < 8000:
        return 'MED_RPM'
    else:
        return 'HIGH_RPM'

# Parameter categories
CAM_GENERALIZABLE = ['Spindle_Speed', 'Feed_Rate', 'Current_Tool']
AXIS_LOADS = ['X_Axis_Load', 'Y_Axis_Load', 'Z_Axis_Load', 'A_Axis_Load', 'C_Axis_Load', 'S_Axis_Load']
VIBRATION_PARAMS = [
    'spindle motor v_rms', 'spindle motor a_peak', 'spindle motor crest',
    'z-axis motor v_rms', 'z-axis motor a_peak',
    'y-axis motor v_rms', 'y-axis motor a_peak',
    'x-axis motor v_rms', 'x-axis motor a_peak',
]
POSITION_PARAMS = ['X_Position', 'Y_Position', 'Z_Position', 'A_Position', 'C_Position']

ALL_NUMERIC_PARAMS = CAM_GENERALIZABLE + AXIS_LOADS + VIBRATION_PARAMS


class EnhancedEnergyAnalyzerV2:
    """Energy analysis with archetypes, normalized metrics, and CAM-ready output"""
    
    def __init__(self):
        self.results = []
        self.param_stats = []
        self.power_profiles = []
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
        """Calculate energy with gap handling"""
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
    
    def analyze_power_profile(self, times, powers):
        """Characterize power profile: ramp-up, steady-state, peak"""
        if len(times) < 5:
            return {
                'peak_power': np.nan, 'steady_state_power': np.nan,
                'ramp_up_time': np.nan, 'power_variability': np.nan
            }
        
        powers = np.array(powers)
        times = np.array(times)
        
        peak_power = np.percentile(powers, 95)  # 95th percentile to avoid spikes
        
        # Steady state = middle 60% of operation
        n = len(powers)
        mid_start = int(n * 0.2)
        mid_end = int(n * 0.8)
        if mid_end > mid_start:
            steady_state_power = np.mean(powers[mid_start:mid_end])
            power_variability = np.std(powers[mid_start:mid_end]) / steady_state_power if steady_state_power > 0 else np.nan
        else:
            steady_state_power = np.mean(powers)
            power_variability = np.nan
        
        # Ramp-up time = time to reach 90% of steady state
        threshold = 0.9 * steady_state_power
        ramp_indices = np.where(powers >= threshold)[0]
        if len(ramp_indices) > 0:
            ramp_up_time = times[ramp_indices[0]] - times[0]
        else:
            ramp_up_time = 0
        
        return {
            'peak_power': round(peak_power, 1),
            'steady_state_power': round(steady_state_power, 1),
            'ramp_up_time': round(ramp_up_time, 2),
            'power_variability': round(power_variability, 3) if not np.isnan(power_variability) else np.nan
        }
    
    def calc_position_travel(self, positions):
        """Calculate total axis travel distance"""
        positions = pd.to_numeric(positions, errors='coerce').dropna().values
        if len(positions) < 2:
            return 0.0
        return np.abs(np.diff(positions)).sum()
    
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
    
    def process_file(self, filepath):
        filename = os.path.basename(filepath)
        parsed = self.parse_filename(filename)
        
        try:
            df = pd.read_csv(filepath)
            
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
            
            # Extract parameter data
            param_data = {}
            for param in ALL_NUMERIC_PARAMS:
                param_df = df[df['Dataname'] == param].copy()
                if not param_df.empty:
                    param_df['Time'] = pd.to_datetime(param_df['Time'])
                    param_df['Value'] = pd.to_numeric(param_df['Value'], errors='coerce')
                    param_data[param] = param_df[['Time', 'Value']].dropna()
            
            # Extract position data
            position_data = {}
            for pos_param in POSITION_PARAMS:
                pos_df = df[df['Dataname'] == pos_param].copy()
                if not pos_df.empty:
                    pos_df['Time'] = pd.to_datetime(pos_df['Time'])
                    pos_df['Value'] = pd.to_numeric(pos_df['Value'], errors='coerce')
                    position_data[pos_param] = pos_df[['Time', 'Value']].dropna()
            
            # Extract tool data
            tool_df = df[df['Dataname'] == 'Current_Tool'].copy()
            if not tool_df.empty:
                tool_df['Time'] = pd.to_datetime(tool_df['Time'])
                tool_df['Value'] = pd.to_numeric(tool_df['Value'], errors='coerce')
            
            expected_part = parsed['part_type']
            expected_prog_num = parsed['program_num']
            expected_program = f'PROGRAM_{expected_prog_num}_{expected_part}'
            
            for program in merged['Program'].unique():
                if program == 'NONE' or program.startswith('UNKNOWN'):
                    continue
                if program != expected_program:
                    continue
                
                prog_data = merged[merged['Program'] == program].copy()
                
                for operation in prog_data['Operation'].unique():
                    op_data = prog_data[prog_data['Operation'] == operation].sort_values('Time_Sec')
                    op_times = op_data['Time_Sec'].values
                    op_powers = op_data['Power'].values
                    op_start = op_data['Time'].min()
                    op_end = op_data['Time'].max()
                    
                    energy, duration, n_seg, n_gaps = self.calculate_energy(op_times, op_powers)
                    
                    # Get archetype
                    op_name = operation if operation != 'NONE' else 'NONE_IDLE'
                    archetype = OPERATION_ARCHETYPES.get(op_name, 'OTHER')
                    
                    # Calculate axis travel
                    total_travel = 0.0
                    for pos_param, pdf in position_data.items():
                        mask = (pdf['Time'] >= op_start) & (pdf['Time'] <= op_end)
                        travel = self.calc_position_travel(pdf.loc[mask, 'Value'])
                        total_travel += travel
                    
                    # Get spindle speed stats
                    spindle_mean = np.nan
                    spindle_band = 'UNKNOWN'
                    if 'Spindle_Speed' in param_data:
                        ss_df = param_data['Spindle_Speed']
                        mask = (ss_df['Time'] >= op_start) & (ss_df['Time'] <= op_end)
                        ss_vals = ss_df.loc[mask, 'Value']
                        if len(ss_vals) > 0:
                            spindle_mean = ss_vals.mean()
                            spindle_band = get_spindle_band(spindle_mean)
                    
                    # Get feed rate stats
                    feed_mean = np.nan
                    if 'Feed_Rate' in param_data:
                        fr_df = param_data['Feed_Rate']
                        mask = (fr_df['Time'] >= op_start) & (fr_df['Time'] <= op_end)
                        fr_vals = fr_df.loc[mask, 'Value']
                        if len(fr_vals) > 0:
                            feed_mean = fr_vals.mean()
                    
                    # Get tool number
                    tool_num = np.nan
                    if not tool_df.empty:
                        mask = (tool_df['Time'] >= op_start) & (tool_df['Time'] <= op_end)
                        tool_vals = tool_df.loc[mask, 'Value']
                        if len(tool_vals) > 0:
                            tool_num = tool_vals.mode().iloc[0] if len(tool_vals.mode()) > 0 else tool_vals.iloc[0]
                    
                    # Get axis load stats
                    load_mean = np.nan
                    load_cols = []
                    for load_param in AXIS_LOADS:
                        if load_param in param_data:
                            ld_df = param_data[load_param]
                            mask = (ld_df['Time'] >= op_start) & (ld_df['Time'] <= op_end)
                            ld_vals = ld_df.loc[mask, 'Value']
                            if len(ld_vals) > 0:
                                load_cols.append(ld_vals.mean())
                    if load_cols:
                        load_mean = np.mean(load_cols)
                    
                    # Power profile analysis
                    power_profile = self.analyze_power_profile(op_times, op_powers)
                    
                    # Normalized metrics
                    energy_per_sec = energy * 3600 / duration if duration > 0 else 0  # W (instantaneous)
                    energy_per_mm = energy / total_travel if total_travel > 0 else np.nan  # Wh/mm
                    
                    result = {
                        'Part_Type': parsed['part_type'],
                        'Part_Num': parsed['part_num'],
                        'Program': program,
                        'Operation': op_name,
                        'Archetype': archetype,
                        'Tool_Num': tool_num,
                        'Spindle_RPM_Mean': round(spindle_mean, 0) if not np.isnan(spindle_mean) else np.nan,
                        'Spindle_Band': spindle_band,
                        'Feed_Rate_Mean': round(feed_mean, 1) if not np.isnan(feed_mean) else np.nan,
                        'Axis_Load_Mean': round(load_mean, 1) if not np.isnan(load_mean) else np.nan,
                        'Energy_Wh': round(energy, 4),
                        'Duration_Sec': round(duration, 2),
                        'Avg_Power_W': round(energy_per_sec, 1),
                        'Total_Travel_mm': round(total_travel, 1),
                        'Energy_per_mm_Wh': round(energy_per_mm, 6) if not np.isnan(energy_per_mm) else np.nan,
                        'Peak_Power_W': power_profile['peak_power'],
                        'Steady_Power_W': power_profile['steady_state_power'],
                        'Ramp_Up_Sec': power_profile['ramp_up_time'],
                        'Power_CV': power_profile['power_variability'],
                        'Data_Points': len(op_times),
                        'Segments': n_seg,
                    }
                    self.results.append(result)
                
        except Exception as e:
            print(f"  Error processing {filename}: {e}")
    
    def analyze(self, directory='.'):
        csv_files = sorted(glob.glob(os.path.join(directory, '*.csv')))
        print(f"Found {len(csv_files)} CSV files")
        
        processed = 0
        for f in csv_files:
            filename = os.path.basename(f)
            skip, reason = self.should_skip_file(filename)
            if skip:
                continue
            self.process_file(f)
            processed += 1
        
        print(f"Processed {processed} files")
        return pd.DataFrame(self.results) if self.results else pd.DataFrame()


def clean_data(df):
    """Apply data cleaning rules with IQR-based outlier detection"""
    if df is None or df.empty:
        return None
    
    df = df.copy()
    
    # Exclude bad parts
    bad_parts = [('Body', 17)]
    for part_type, part_num in bad_parts:
        mask = (df['Part_Type'] == part_type) & (df['Part_Num'] == part_num)
        df = df[~mask]
    
    # Exclude UNKNOWN operations
    df = df[~df['Operation'].str.startswith('UNKNOWN')]
    
    # IQR-based outlier detection per operation
    df['Is_Outlier'] = False
    for operation in df['Operation'].unique():
        if operation in ['NONE_IDLE', 'TRANSITION_OVERHEAD']:
            continue
        
        op_mask = df['Operation'] == operation
        energy_vals = df.loc[op_mask, 'Energy_Wh']
        
        if len(energy_vals) < 4:
            continue
        
        Q1 = energy_vals.quantile(0.25)
        Q3 = energy_vals.quantile(0.75)
        IQR = Q3 - Q1
        lower = Q1 - 1.5 * IQR
        upper = Q3 + 1.5 * IQR
        
        outlier_mask = (df['Energy_Wh'] < lower) | (df['Energy_Wh'] > upper)
        df.loc[op_mask & outlier_mask, 'Is_Outlier'] = True
    
    return df


def create_archetype_library(df):
    """
    Create energy library grouped by operation archetype.
    This is the most generalizable format for CAM-based estimation.
    """
    if df is None or df.empty:
        return None
    
    clean_df = df[(df['Is_Outlier'] == False) & (~df['Archetype'].isin(['IDLE', 'TRANSITION']))].copy()
    
    # Group by archetype and spindle band
    archetype_lib = clean_df.groupby(['Archetype', 'Spindle_Band']).agg(
        Energy_Wh_Mean=('Energy_Wh', 'mean'),
        Energy_Wh_Std=('Energy_Wh', 'std'),
        Energy_Wh_Min=('Energy_Wh', 'min'),
        Energy_Wh_Max=('Energy_Wh', 'max'),
        Avg_Power_W=('Avg_Power_W', 'mean'),
        Duration_Sec=('Duration_Sec', 'mean'),
        Feed_Rate=('Feed_Rate_Mean', 'mean'),
        Spindle_RPM=('Spindle_RPM_Mean', 'mean'),
        Energy_per_mm=('Energy_per_mm_Wh', 'mean'),
        N_Samples=('Energy_Wh', 'count'),
    ).round(4)
    
    archetype_lib['CV_pct'] = (archetype_lib['Energy_Wh_Std'] / archetype_lib['Energy_Wh_Mean'] * 100).round(1)
    
    return archetype_lib


def create_tool_library(df):
    """Create energy library grouped by tool number"""
    if df is None or df.empty:
        return None
    
    clean_df = df[(df['Is_Outlier'] == False) & (df['Tool_Num'].notna())].copy()
    
    tool_lib = clean_df.groupby(['Tool_Num', 'Archetype']).agg(
        Energy_Wh_Mean=('Energy_Wh', 'mean'),
        Avg_Power_W=('Avg_Power_W', 'mean'),
        Spindle_RPM=('Spindle_RPM_Mean', 'mean'),
        N_Samples=('Energy_Wh', 'count'),
    ).round(3)
    
    return tool_lib


def create_cam_lookup_table(df):
    """
    Create simplified lookup table for CAM-based energy estimation.
    Format: Archetype + Spindle Band -> Energy/second, typical duration
    """
    if df is None or df.empty:
        return None
    
    clean_df = df[(df['Is_Outlier'] == False) & (~df['Archetype'].isin(['IDLE', 'TRANSITION']))].copy()
    
    lookup = clean_df.groupby(['Archetype', 'Spindle_Band']).agg({
        'Avg_Power_W': 'mean',
        'Duration_Sec': 'mean',
        'Energy_Wh': 'mean',
        'Energy_per_mm_Wh': 'mean',
    }).round(4).reset_index()
    
    lookup.columns = ['Operation_Type', 'Spindle_Band', 'Typical_Power_W', 'Typical_Duration_Sec', 
                      'Typical_Energy_Wh', 'Energy_per_mm_Wh']
    
    # Add usage notes
    lookup['Usage_Notes'] = lookup.apply(
        lambda r: f"For {r['Operation_Type']} at {r['Spindle_Band']}: multiply Typical_Power_W by your operation duration (sec) / 3600 for Wh",
        axis=1
    )
    
    return lookup


def create_correlation_analysis(df):
    """Analyze correlations between parameters and energy"""
    if df is None or df.empty:
        return None
    
    clean_df = df[(df['Is_Outlier'] == False) & (~df['Archetype'].isin(['IDLE', 'TRANSITION']))].copy()
    
    # Select numeric columns for correlation
    corr_cols = ['Energy_Wh', 'Duration_Sec', 'Spindle_RPM_Mean', 'Feed_Rate_Mean', 
                 'Axis_Load_Mean', 'Total_Travel_mm', 'Peak_Power_W', 'Steady_Power_W']
    
    available_cols = [c for c in corr_cols if c in clean_df.columns]
    
    corr_matrix = clean_df[available_cols].corr()
    
    # Extract energy correlations
    energy_corr = corr_matrix['Energy_Wh'].drop('Energy_Wh').sort_values(key=abs, ascending=False)
    
    corr_df = pd.DataFrame({
        'Parameter': energy_corr.index,
        'Correlation_with_Energy': energy_corr.values.round(3),
        'Abs_Correlation': np.abs(energy_corr.values).round(3),
        'Predictive_Value': pd.cut(np.abs(energy_corr.values), 
                                    bins=[0, 0.3, 0.6, 1.0], 
                                    labels=['Low', 'Medium', 'High'])
    })
    
    return corr_df, corr_matrix


def generate_plots(df, output_dir='.'):
    """Generate visualization plots"""
    if not HAS_PLOTTING or df is None or df.empty:
        return
    
    clean_df = df[(df['Is_Outlier'] == False) & (~df['Archetype'].isin(['IDLE', 'TRANSITION']))].copy()
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. Energy by Archetype
    ax1 = axes[0, 0]
    archetype_energy = clean_df.groupby('Archetype')['Energy_Wh'].mean().sort_values(ascending=False)
    archetype_energy.plot(kind='barh', ax=ax1, color='steelblue')
    ax1.set_xlabel('Mean Energy (Wh)')
    ax1.set_title('Energy by Operation Archetype')
    ax1.invert_yaxis()
    
    # 2. Energy vs Duration scatter
    ax2 = axes[0, 1]
    for archetype in clean_df['Archetype'].unique():
        arch_data = clean_df[clean_df['Archetype'] == archetype]
        ax2.scatter(arch_data['Duration_Sec'], arch_data['Energy_Wh'], 
                   label=archetype, alpha=0.6, s=30)
    ax2.set_xlabel('Duration (sec)')
    ax2.set_ylabel('Energy (Wh)')
    ax2.set_title('Energy vs Duration by Archetype')
    ax2.legend(bbox_to_anchor=(1.05, 1), loc='upper left', fontsize=8)
    
    # 3. Power distribution by archetype
    ax3 = axes[1, 0]
    archetype_order = clean_df.groupby('Archetype')['Avg_Power_W'].median().sort_values(ascending=False).index
    clean_df.boxplot(column='Avg_Power_W', by='Archetype', ax=ax3, 
                     positions=range(len(archetype_order)))
    ax3.set_xticklabels(archetype_order, rotation=45, ha='right')
    ax3.set_xlabel('Archetype')
    ax3.set_ylabel('Average Power (W)')
    ax3.set_title('Power Distribution by Archetype')
    plt.suptitle('')  # Remove automatic title
    
    # 4. Spindle speed vs Energy
    ax4 = axes[1, 1]
    valid_spindle = clean_df[clean_df['Spindle_RPM_Mean'].notna()]
    ax4.scatter(valid_spindle['Spindle_RPM_Mean'], valid_spindle['Avg_Power_W'], 
               c=valid_spindle['Archetype'].astype('category').cat.codes, 
               cmap='tab10', alpha=0.6, s=30)
    ax4.set_xlabel('Spindle Speed (RPM)')
    ax4.set_ylabel('Average Power (W)')
    ax4.set_title('Power vs Spindle Speed')
    
    plt.tight_layout()
    plot_path = os.path.join(output_dir, 'energy_analysis_plots.png')
    plt.savefig(plot_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"Saved plots to: {plot_path}")
    
    # Correlation heatmap
    corr_df, corr_matrix = create_correlation_analysis(df)
    if corr_matrix is not None:
        fig, ax = plt.subplots(figsize=(10, 8))
        sns.heatmap(corr_matrix, annot=True, cmap='RdBu_r', center=0, 
                   fmt='.2f', ax=ax, square=True)
        ax.set_title('Parameter Correlation Matrix')
        plt.tight_layout()
        heatmap_path = os.path.join(output_dir, 'correlation_heatmap.png')
        plt.savefig(heatmap_path, dpi=150, bbox_inches='tight')
        plt.close()
        print(f"Saved heatmap to: {heatmap_path}")


def export_json_lookup(cam_lookup, output_path):
    """Export CAM lookup table as JSON for programmatic use"""
    if cam_lookup is None:
        return
    
    lookup_dict = {}
    for _, row in cam_lookup.iterrows():
        key = f"{row['Operation_Type']}_{row['Spindle_Band']}"
        lookup_dict[key] = {
            'typical_power_w': row['Typical_Power_W'],
            'typical_duration_sec': row['Typical_Duration_Sec'],
            'typical_energy_wh': row['Typical_Energy_Wh'],
            'energy_per_mm_wh': row['Energy_per_mm_Wh'] if not pd.isna(row['Energy_per_mm_Wh']) else None,
        }
    
    with open(output_path, 'w') as f:
        json.dump(lookup_dict, f, indent=2)
    print(f"Saved JSON lookup to: {output_path}")


def main():
    directory = input("Enter directory path (Enter for current): ").strip() or "."
    
    print("\n" + "="*70)
    print("ENHANCED ENERGY ANALYZER v2")
    print("="*70)
    
    analyzer = EnhancedEnergyAnalyzerV2()
    results = analyzer.analyze(directory)
    
    if results.empty:
        print("No results generated")
        return
    
    print(f"Generated {len(results)} operation records")
    
    # Clean data
    cleaned = clean_data(results)
    outlier_count = cleaned['Is_Outlier'].sum()
    print(f"Flagged {outlier_count} outliers")
    
    # Create libraries
    archetype_lib = create_archetype_library(cleaned)
    tool_lib = create_tool_library(cleaned)
    cam_lookup = create_cam_lookup_table(cleaned)
    corr_df, corr_matrix = create_correlation_analysis(cleaned)
    
    # Display summaries
    print("\n" + "="*70)
    print("ARCHETYPE ENERGY LIBRARY (for CAM-based estimation)")
    print("="*70)
    if archetype_lib is not None:
        print(archetype_lib[['Energy_Wh_Mean', 'Avg_Power_W', 'CV_pct', 'N_Samples']].to_string())
    
    print("\n" + "="*70)
    print("TOP ENERGY PREDICTORS")
    print("="*70)
    if corr_df is not None:
        print(corr_df.to_string(index=False))
    
    print("\n" + "="*70)
    print("CAM LOOKUP TABLE (simplified)")
    print("="*70)
    if cam_lookup is not None:
        print(cam_lookup[['Operation_Type', 'Spindle_Band', 'Typical_Power_W', 'Typical_Energy_Wh']].to_string(index=False))
    
    # Save outputs
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outfile = f"enhanced_feature_library_v2_{timestamp}.xlsx"
    
    with pd.ExcelWriter(outfile, engine='openpyxl') as writer:
        if archetype_lib is not None:
            archetype_lib.to_excel(writer, sheet_name='Archetype_Library')
        
        if tool_lib is not None:
            tool_lib.to_excel(writer, sheet_name='Tool_Library')
        
        if cam_lookup is not None:
            cam_lookup.to_excel(writer, sheet_name='CAM_Lookup', index=False)
        
        if corr_df is not None:
            corr_df.to_excel(writer, sheet_name='Energy_Correlations', index=False)
        
        if corr_matrix is not None:
            corr_matrix.to_excel(writer, sheet_name='Correlation_Matrix')
        
        # Detailed operation library (original format)
        op_lib = cleaned[cleaned['Is_Outlier'] == False].groupby(['Part_Type', 'Program', 'Operation']).agg(
            Archetype=('Archetype', 'first'),
            Energy_Wh=('Energy_Wh', 'mean'),
            Energy_Std=('Energy_Wh', 'std'),
            Avg_Power_W=('Avg_Power_W', 'mean'),
            Duration_Sec=('Duration_Sec', 'mean'),
            N_Runs=('Energy_Wh', 'count'),
        ).round(4)
        op_lib.to_excel(writer, sheet_name='Operation_Library')
        
        # Raw cleaned data
        cleaned.to_excel(writer, sheet_name='Cleaned_Data', index=False)
    
    print(f"\nSaved Excel to: {outfile}")
    
    # Export JSON lookup
    json_path = f"cam_energy_lookup_{timestamp}.json"
    export_json_lookup(cam_lookup, json_path)
    
    # Generate plots
    generate_plots(cleaned, '.')
    
    print("\n" + "="*70)
    print("OUTPUT FILES")
    print("="*70)
    print(f"  - {outfile}: Full Excel workbook")
    print(f"  - {json_path}: JSON lookup for programmatic CAM integration")
    print("  - energy_analysis_plots.png: Visualization")
    print("  - correlation_heatmap.png: Parameter correlations")
    
    print("\n" + "="*70)
    print("HOW TO USE FOR SOMEONE ELSE'S CAM")
    print("="*70)
    print("""
1. Map their CAM operations to archetypes:
   - Roughing/pocketing -> ROUGH_MILL
   - Finishing/profiling -> FINISH_MILL  
   - Face milling -> FACING
   - Drilling -> DRILLING, etc.

2. Determine spindle speed band (LOW/MED/HIGH_RPM)

3. Look up Typical_Power_W from CAM_Lookup sheet/JSON

4. Estimate energy: 
   Energy_Wh = Typical_Power_W * (their_duration_sec / 3600)
   
   OR if they have toolpath length:
   Energy_Wh = Energy_per_mm_Wh * their_toolpath_mm

5. Sum across all operations for total part energy
""")


if __name__ == "__main__":
    main()