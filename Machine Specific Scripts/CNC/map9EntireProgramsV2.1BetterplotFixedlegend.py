import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import glob
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

class ActivePowerAnalyzer:
    """
    Enhanced Active Power Analyzer for sequential program analysis
    """
    
    def __init__(self, debug=True):
        self.debug = debug
        self.csv_data = None
        self.uuid_to_operation = {}
        self.partkind_to_program = {}
        self.operation_power_data = {}
        self.timeline_data = None
        self.setup_partkind_mapping()
        self.setup_uuid_operation_mapping()
        
    def setup_partkind_mapping(self):
        """
        Setup hardcoded partKindId to program mapping based on provided data
        """
        self.partkind_to_program = {
            '5BC675E0-40F9-45BE-AE5C-CF7E8F493235': 'NONE',
            '072B393C-87F5-4183-9ABC-0870E4B4F53B': 'PROGRAM_1_Body', 
            'EDB34637-67D8-465A-AFBA-010AD86D34F6': 'PROGRAM_2_Body',
            '5E4A09CE-E1D5-4FCC-B912-38239DF9FDA0': 'PROGRAM_3_Body',
            'D2C78EB3-CB26-4FDA-ABA9-353C0E6A1AB1': 'PROGRAM_4_Body',
            '68C62535-3304-4629-A02B-85CAE2490743': 'PROGRAM_1_Lid',
            '7606F116-3463-4EEF-96CC-1AC408FAA001': 'PROGRAM_2_Lid'            
        }
        
        self.log(f"Setup partKindId mapping for {len(self.partkind_to_program)} programs")
    
    def setup_uuid_operation_mapping(self):
        """
        Setup hardcoded UUID to operation mapping for both Body and Lid operations
        """
        # Body operations mapping
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
        
        # Lid operations mapping
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
        
        # Combine all mappings
        self.uuid_to_operation = {}
        self.uuid_to_operation.update(body_operations)
        self.uuid_to_operation.update(lid_operations)
        self.uuid_to_operation['NONE'] = 'NONE'
        
        self.log(f"Setup UUID to operation mapping for {len(self.uuid_to_operation)} operations")
        
    def log(self, message):
        """Simple logging for debugging"""
        if self.debug:
            print(f"[DEBUG] {message}")
    
    def load_csv_data(self, csv_filepath):
        """
        Load CSV data with proper structure understanding
        """
        self.log(f"\nLoading CSV: {os.path.basename(csv_filepath)}")
        
        try:
            self.csv_data = pd.read_csv(csv_filepath)
            self.log(f"CSV shape: {self.csv_data.shape}")
            
            if 'Dataname' not in self.csv_data.columns:
                self.log("ERROR: No 'Dataname' column found")
                return False
            
            # Convert Time column to datetime
            self.csv_data['Time'] = pd.to_datetime(self.csv_data['Time'])
            
            return True
            
        except Exception as e:
            self.log(f"Error loading CSV: {e}")
            return False
    
    def extract_paired_data(self):
        """
        Extract processKindId (UUID), partKindId, and power values at each timestamp
        Also calculate energy consumption (Power * Time)
        """
        self.log("\nExtracting paired data...")
        
        if self.csv_data is None:
            self.log("No CSV data loaded")
            return None
        
        # Get processKindId data
        processkindid_data = self.csv_data[self.csv_data['Dataname'] == 'processKindId'].copy()
        
        # Get partKindId data  
        partkindid_data = self.csv_data[self.csv_data['Dataname'] == 'partKindId'].copy()
        
        # Get power data
        active_power_data = self.csv_data[self.csv_data['Dataname'] == 'active power'].copy()
        
        if processkindid_data.empty or partkindid_data.empty or active_power_data.empty:
            self.log("ERROR: Missing required data")
            return None
        
        self.log(f"Found {len(processkindid_data)} processKindId entries")
        self.log(f"Found {len(partkindid_data)} partKindId entries") 
        self.log(f"Found {len(active_power_data)} power entries")
        
        # Prepare data for merging
        processkindid_data = processkindid_data[['Time', 'Value']].rename(columns={'Value': 'UUID'})
        partkindid_data = partkindid_data[['Time', 'Value']].rename(columns={'Value': 'PartKindId'})
        active_power_data = active_power_data[['Time', 'Value']].rename(columns={'Value': 'ActivePower'})
        
        # Convert power to numeric and handle negatives
        active_power_data['ActivePower'] = pd.to_numeric(active_power_data['ActivePower'], errors='coerce')
        active_power_data['ActivePower'] = active_power_data['ActivePower'].clip(lower=0)
        
        # Merge all three datasets on timestamp
        timeline_data = pd.merge(processkindid_data, partkindid_data, on='Time', how='inner')
        timeline_data = pd.merge(timeline_data, active_power_data, on='Time', how='inner')
        
        # Sort by time
        timeline_data = timeline_data.sort_values('Time').reset_index(drop=True)
        
        # Create time in seconds from start
        if len(timeline_data) > 0:
            start_time = timeline_data['Time'].iloc[0]
            timeline_data['Time_Seconds'] = (timeline_data['Time'] - start_time).dt.total_seconds()
        
        # Calculate energy consumption (Power * Time = Energy)
        # Calculate time differences in hours
        timeline_data['time_diff_hours'] = timeline_data['Time'].diff().dt.total_seconds() / 3600
        
        # Remove the first row (NaN time_diff)
        if len(timeline_data) > 1:
            timeline_data.loc[timeline_data.index[0], 'time_diff_hours'] = 0
        
        # Calculate energy for each interval (Power * Time = Energy)
        # Convert W to kW and multiply by time in hours to get kWh
        timeline_data['energy_kwh'] = (timeline_data['ActivePower'] * timeline_data['time_diff_hours']) / 1000
        
        # Map UUID to operation name
        timeline_data['Operation'] = timeline_data['UUID'].apply(
            lambda x: self.uuid_to_operation.get(str(x).strip().upper(), 'NONE' if str(x).strip().upper() == 'NONE' else f'Idle/Preprocessing')
        )
        
        # Map PartKindId to program name
        timeline_data['Program'] = timeline_data['PartKindId'].apply(
            lambda x: self.partkind_to_program.get(str(x).strip().upper(), f'Idle/Preprocessing')
        )
        
        self.log(f"Created timeline with {len(timeline_data)} paired data points")
        
        self.timeline_data = timeline_data
        return timeline_data
    
    def analyze_part_programs(self, part_number, part_type='body', base_directory='.'):
        """
        Analyze all programs for a specific part (body or lid) and plot them sequentially
        Uses partKindId (UUID) to detect actual program boundaries
        
        Args:
            part_number: The part number (e.g., 26 for al6061_body26)
            part_type: 'body' or 'lid'
            base_directory: Directory containing CSV files
        
        Returns:
            Tuple of (combined_timeline, program_boundaries) or None if failed
        """
        print(f"\n{'='*100}")
        print(f"SEQUENTIAL PROGRAM ANALYSIS - {part_type.upper()} Part #{part_number}")
        print(f"{'='*100}")
        
        # Determine number of programs based on type
        num_programs = 4 if part_type.lower() == 'body' else 2
        print(f"Expected programs: {num_programs} (for {part_type})")
        
        # Auto-detect files
        file_pattern = f"al6061_{part_type.lower()}{part_number}_p{{program}}.csv"
        
        # Load all program files
        all_timeline_data = []
        cumulative_time = 0
        
        for program_num in range(1, num_programs + 1):
            filename = file_pattern.format(program=program_num)
            filepath = os.path.join(base_directory, filename)
            
            print(f"\nLooking for: {filename}")
            
            if not os.path.exists(filepath):
                print(f"WARNING: File not found: {filename}")
                continue
            
            # Load this program's data
            print(f"Loading {filename}...")
            if not self.load_csv_data(filepath):
                print(f"ERROR: Failed to load {filename}")
                continue
            
            # Extract power timeline
            timeline = self.extract_paired_data()
            if timeline is None or timeline.empty:
                print(f"ERROR: Failed to extract data from {filename}")
                continue
            
            # Adjust time by adding cumulative offset
            timeline['Time_Seconds_Adjusted'] = timeline['Time_Seconds'] + cumulative_time
            timeline['File_Program_Number'] = program_num
            
            # Update cumulative time for next program (end of this file's timeline)
            cumulative_time = timeline['Time_Seconds_Adjusted'].max()
            
            # Store this program's data
            all_timeline_data.append(timeline)
            
            print(f"✓ Loaded {filename}: {len(timeline)} data points")
        
        if not all_timeline_data:
            print("\nERROR: No program data loaded")
            return None
        
        print(f"\n{'='*80}")
        print(f"Successfully loaded {len(all_timeline_data)} out of {num_programs} programs")
        print(f"{'='*80}")
        
        # Combine all programs into one dataset
        combined_timeline = pd.concat(all_timeline_data, ignore_index=True)
        
        # Detect program boundaries based on partKindId (UUID) changes
        program_boundaries = self.detect_program_boundaries(combined_timeline, part_type)
        
        # Plot the sequential power timeline
        self.plot_sequential_programs(combined_timeline, program_boundaries, part_number, part_type)
        
        return combined_timeline, program_boundaries
    
    def detect_program_boundaries(self, combined_timeline, part_type):
        """
        Detect program boundaries based on partKindId (UUID) changes in the data
        Calculate energy consumption for each program
        """
        print("\nDetecting program boundaries from partKindId (UUID) changes...")
        
        program_boundaries = []
        current_partkind = None
        segment_start_idx = 0
        
        for idx, row in combined_timeline.iterrows():
            if row['PartKindId'] != current_partkind:
                # End previous segment if it exists
                if current_partkind is not None and segment_start_idx < idx:
                    segment_data = combined_timeline.iloc[segment_start_idx:idx]
                    
                    # Get program name from UUID mapping
                    program_name = self.partkind_to_program.get(
                        str(current_partkind).strip().upper(), 
                        f'Idle/Preprocessing'
                    )
                    
                    # Extract program number from name (e.g., "PROGRAM_1_Body" -> 1)
                    if 'PROGRAM_' in program_name:
                        try:
                            prog_num = int(program_name.split('_')[1])
                        except:
                            prog_num = len(program_boundaries) + 1
                    else:
                        prog_num = 'NONE' if program_name == 'NONE' else len(program_boundaries) + 1
                    
                    # Calculate total energy for this program segment
                    total_energy_kwh = segment_data['energy_kwh'].sum()
                    
                    program_boundaries.append({
                        'program': prog_num,
                        'program_name': program_name,
                        'partkind_uuid': current_partkind,
                        'start': segment_data['Time_Seconds_Adjusted'].iloc[0],
                        'end': segment_data['Time_Seconds_Adjusted'].iloc[-1],
                        'duration': segment_data['Time_Seconds_Adjusted'].iloc[-1] - segment_data['Time_Seconds_Adjusted'].iloc[0],
                        'total_energy_kwh': total_energy_kwh,
                        'avg_power': segment_data['ActivePower'].mean(),
                        'data_points': len(segment_data)
                    })
                    
                    print(f"  Found program segment: {program_name} (UUID: {str(current_partkind)[:36]})")
                    print(f"    Start: {segment_data['Time_Seconds_Adjusted'].iloc[0]:.1f}s, "
                          f"End: {segment_data['Time_Seconds_Adjusted'].iloc[-1]:.1f}s, "
                          f"Duration: {segment_data['Time_Seconds_Adjusted'].iloc[-1] - segment_data['Time_Seconds_Adjusted'].iloc[0]:.1f}s, "
                          f"Energy: {total_energy_kwh:.4f} kWh")
                
                # Start new segment
                current_partkind = row['PartKindId']
                segment_start_idx = idx
        
        # Handle the last segment
        if current_partkind is not None and segment_start_idx < len(combined_timeline):
            segment_data = combined_timeline.iloc[segment_start_idx:]
            
            program_name = self.partkind_to_program.get(
                str(current_partkind).strip().upper(), 
                f'Idle/Preprocessing'
            )
            
            if 'PROGRAM_' in program_name:
                try:
                    prog_num = int(program_name.split('_')[1])
                except:
                    prog_num = len(program_boundaries) + 1
            else:
                prog_num = 'NONE' if program_name == 'NONE' else len(program_boundaries) + 1
            
            total_energy_kwh = segment_data['energy_kwh'].sum()
            
            program_boundaries.append({
                'program': prog_num,
                'program_name': program_name,
                'partkind_uuid': current_partkind,
                'start': segment_data['Time_Seconds_Adjusted'].iloc[0],
                'end': segment_data['Time_Seconds_Adjusted'].iloc[-1],
                'duration': segment_data['Time_Seconds_Adjusted'].iloc[-1] - segment_data['Time_Seconds_Adjusted'].iloc[0],
                'total_energy_kwh': total_energy_kwh,
                'avg_power': segment_data['ActivePower'].mean(),
                'data_points': len(segment_data)
            })
            
            print(f"  Found program segment: {program_name} (UUID: {str(current_partkind)[:36]})")
            print(f"    Start: {segment_data['Time_Seconds_Adjusted'].iloc[0]:.1f}s, "
                  f"End: {segment_data['Time_Seconds_Adjusted'].iloc[-1]:.1f}s, "
                  f"Duration: {segment_data['Time_Seconds_Adjusted'].iloc[-1] - segment_data['Time_Seconds_Adjusted'].iloc[0]:.1f}s, "
                  f"Energy: {total_energy_kwh:.4f} kWh")
        
        print(f"\nTotal program segments detected: {len(program_boundaries)}")
        
        return program_boundaries
    
    def plot_sequential_programs(self, combined_timeline, program_boundaries, part_number, part_type):
        """
        Plot all programs sequentially in a single plot with labeled sections based on UUID boundaries
        """
        print("\nCreating sequential program plot...")
        
        fig, ax = plt.subplots(figsize=(24, 9))
        
        # Plot the continuous power line
        power_line = ax.plot(combined_timeline['Time_Seconds_Adjusted'], 
                combined_timeline['ActivePower'],
                linewidth=2.5, color='#1f77b4', label='Power', zorder=5)
        
        # Define highly visible, distinct colors for programs 1-4
        colors = [
            '#1E88E5',  # Deep blue - Program 1
            '#FFA726',  # Bright orange - Program 2
            '#66BB6A',  # Green - Program 3
            "#4776BC",  # Purple - Program 4
            "#3B0C72",  # Pink - Program 5 (if needed)
            '#26A69A',  # Teal - Program 6 (if needed)
            '#FFA726',  # Orange alternate
            '#5C6BC0',  # Indigo
            '#EF5350',  # Red alternate
            '#9CCC65'   # Light green
        ]
        
        # Red color for idle/preprocessing periods
        idle_color = '#D32F2F'  # Red for idle/preprocessing
        
        # Create color map for each unique program
        active_programs = [b for b in program_boundaries if b['program'] != 'NONE' and b['duration'] >= 1]
        program_color_map = {}
        legend_patches = []


        # Add idle/preprocessing to legend with correct color
        idle_programs = [b for b in program_boundaries if (b['program'] == 'NONE' or 'Idle' in b['program_name'] or 'Preprocessing' in b['program_name']) and b['duration'] >= 1]
        if idle_programs:
            idle_patch = plt.Rectangle((0, 0), 1, 1, fc=idle_color, alpha=0.3, edgecolor=idle_color, linewidth=2)
            legend_patches.append((idle_patch, f"Idle/Preprocessing - {idle_programs[0]['total_energy_kwh']:.4f} kWh"))
       
                # Assign colors to programs and create legend
        for i, boundary in enumerate(active_programs):
            prog_name = boundary['program_name']
            if prog_name not in program_color_map:
                # ADD THIS CONDITION to skip Idle/Preprocessing in the original loop
                if 'Idle' not in prog_name and 'Preprocessing' not in prog_name:
                    color = colors[len(program_color_map) % len(colors)]
                    program_color_map[prog_name] = color
                    
                    # Create legend entry with energy (no UUID)
                    legend_label = f"{prog_name} - {boundary['total_energy_kwh']:.4f} kWh"
                    patch = plt.Rectangle((0, 0), 1, 1, fc=color, alpha=0.3, edgecolor=color, linewidth=2)
                    legend_patches.append((patch, legend_label))
        
        # Plot shaded backgrounds for each program
        for boundary in program_boundaries:
            # Skip NONE programs or very short segments
            if boundary['program'] == 'NONE' or boundary['duration'] < 1:
                continue
            
            prog_name = boundary['program_name']
            
            # Use red for idle/preprocessing, otherwise use program color
            if 'Idle' in prog_name or 'Preprocessing' in prog_name:
                color = idle_color
            else:
                color = program_color_map.get(prog_name, idle_color)
            
            # Add shaded background for each program
            ax.axvspan(boundary['start'], boundary['end'],
                       color=color, alpha=0.25, zorder=1)
            
            # Add vertical line at program start
            ax.axvline(boundary['start'], color='darkred', linestyle='--', 
                       linewidth=1.5, alpha=0.7, zorder=3)
        
        # Add final vertical line
        if program_boundaries:
            ax.axvline(program_boundaries[-1]['end'], color='darkred', 
                       linestyle='--', linewidth=1.5, alpha=0.7, zorder=3)
        
        # Get initial y-axis range to calculate label positions
        y_min_init, y_max_init = ax.get_ylim()
        y_range = y_max_init - y_min_init
        
        # Calculate positions below x-axis (as absolute values)
        y_label_positions_below = [
            -0.08 * y_range,
            -0.15 * y_range,
            -0.22 * y_range,
            -0.29 * y_range,
            -0.36 * y_range,
            -0.43 * y_range
        ]
        
        # Add compact labels - ALL below the plot with staggering
        # Use 6 different height levels below x-axis for better separation
        label_height_idx = 0
        
        for boundary in program_boundaries:
            if boundary['duration'] < 1:
                continue
            
            prog_name = boundary['program_name']
            
            # Check if this is Idle/Preprocessing or NONE
            is_idle = boundary['program'] == 'NONE' or 'Idle' in prog_name or 'Preprocessing' in prog_name
            
            # Place all labels below x-axis
            mid_time = (boundary['start'] + boundary['end']) / 2
            y_pos = y_label_positions_below[label_height_idx % len(y_label_positions_below)]
            label_height_idx += 1
            
            if is_idle:
                # Simpler label for idle/preprocessing
                color = idle_color
                label_text = f"{prog_name}\n{boundary['duration']:.0f}s"
                font_size = 7
            else:
                # Full label with energy for known programs
                color = program_color_map[prog_name]
                label_text = f"{prog_name}\n{boundary['duration']:.0f}s\n{boundary['total_energy_kwh']:.4f} kWh"
                font_size = 8
            
            ax.text(mid_time, y_pos, label_text,
                    ha='center', va='center', fontsize=font_size, fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.4', facecolor='white', 
                             edgecolor=color, linewidth=2, alpha=0.98),
                    zorder=10)
        
        # Calculate total stats (excluding NONE programs)
        active_boundaries = [b for b in program_boundaries if b['program'] != 'NONE']
        total_duration_seconds = combined_timeline['Time_Seconds_Adjusted'].max()
        total_duration_minutes = total_duration_seconds / 60  # Convert to minutes
        total_energy_kwh = sum(b['total_energy_kwh'] for b in active_boundaries)
        avg_power = combined_timeline['ActivePower'].mean()
        
        # Count actual programs (1-4 for body, 1-2 for lid)
        num_actual_programs = 4 if part_type.lower() == 'body' else 2
        
        ax.set_title(f'Sequential Power Timeline - {part_type.upper()} Part #{part_number}\n'
                     f'{num_actual_programs} Programs | Total Duration: {total_duration_minutes:.1f} min | '
                     f'Total Energy: {total_energy_kwh:.4f} kWh | Avg Power: {avg_power:.2f} W',
                     fontsize=16, pad=20, fontweight='bold')
        ax.set_xlabel('Time (seconds)', fontsize=14, fontweight='bold')
        ax.set_ylabel('Power (W)', fontsize=14, fontweight='bold')
        ax.grid(True, alpha=0.3, linestyle=':', linewidth=1)
        
        # Extend y-axis limits to accommodate labels below
        ax.set_ylim(min(y_label_positions_below) - (y_range * 0.1), y_max_init)
        
        # Add comprehensive legend
        # Combine power line with program patches
        all_handles = [power_line[0]]
        all_labels = ['Power']
        
        for patch, label in legend_patches:
            all_handles.append(patch)
            all_labels.append(label)
        
        # Create legend in top-left area (left third of plot)
        ax.legend(all_handles, all_labels, 
                 loc='upper left', 
                 bbox_to_anchor=(0.1, 1.0),  # Change first number (0.0-1.0) to move righ
                 fontsize=11, 
                 framealpha=0.95,
                 edgecolor='black',
                 title='Programs & Energy',
                 title_fontsize=12)
        
        plt.tight_layout()
        plt.show()
        
        # Print summary table
        self.print_program_summary(program_boundaries, part_number, part_type)
    
    def print_program_summary(self, program_boundaries, part_number, part_type):
        """
        Print a summary table of all programs detected from UUIDs with energy calculations
        """
        print(f"\n{'='*100}")
        print(f"PROGRAM SUMMARY - {part_type.upper()} Part #{part_number}")
        print(f"Based on partKindId (UUID) Detection")
        print(f"{'='*100}")
        
        # Separate NONE and active programs
        active_programs = [p for p in program_boundaries if p['program'] != 'NONE']
        idle_programs = [p for p in program_boundaries if p['program'] == 'NONE']
        
        if active_programs:
            total_duration = sum(p['duration'] for p in active_programs)
            total_energy_kwh = sum(p['total_energy_kwh'] for p in active_programs)
            
            print(f"\nActive Programs: {len(active_programs)}")
            print(f"Total Duration (active): {total_duration:.1f} seconds ({total_duration/60:.1f} minutes)")
            print(f"Total Energy (active): {total_energy_kwh:.4f} kWh")
            print(f"Average Power: {(total_energy_kwh * 1000) / (total_duration / 3600):.2f} W")
            
            print(f"\n{'-'*120}")
            print(f"{'PROGRAM':<20} {'UUID':<40} {'START (s)':<12} {'END (s)':<12} {'DURATION (s)':<15} "
                  f"{'ENERGY (kWh)':<15}")
            print(f"{'-'*120}")
            
            for boundary in active_programs:
                uuid_display = str(boundary['partkind_uuid'])[:36]
                
                print(f"{boundary['program_name']:<20} {uuid_display:<40} {boundary['start']:<12.1f} "
                      f"{boundary['end']:<12.1f} {boundary['duration']:<15.1f} "
                      f"{boundary['total_energy_kwh']:<15.4f}")
            
            print(f"{'-'*120}")
            
            # Find program with highest energy consumption
            max_energy_program = max(active_programs, key=lambda x: x['total_energy_kwh'])
            print(f"\nHighest Energy Consumption: {max_energy_program['program_name']} "
                  f"with {max_energy_program['total_energy_kwh']:.4f} kWh")
            
            # Find longest program
            longest_program = max(active_programs, key=lambda x: x['duration'])
            print(f"Longest Duration: {longest_program['program_name']} "
                  f"with {longest_program['duration']:.1f}s duration")
            
            # Find highest average power
            max_power_program = max(active_programs, key=lambda x: x['avg_power'])
            print(f"Highest Avg Power: {max_power_program['program_name']} "
                  f"with {max_power_program['avg_power']:.2f} W average power")
        
        if idle_programs:
            print(f"\n{'='*100}")
            print(f"IDLE/PREPROCESSING PERIODS:")
            print(f"{'='*100}")
            
            total_idle_duration = sum(p['duration'] for p in idle_programs)
            total_idle_energy_kwh = sum(p['total_energy_kwh'] for p in idle_programs)
            avg_idle_power = sum(p['avg_power'] * p['duration'] for p in idle_programs) / total_idle_duration if total_idle_duration > 0 else 0
            
            print(f"Number of idle/preprocessing periods: {len(idle_programs)}")
            print(f"Total idle time: {total_idle_duration:.1f} seconds ({total_idle_duration/60:.1f} minutes)")
            print(f"Total idle energy: {total_idle_energy_kwh:.4f} kWh")
            print(f"Average power during idle: {avg_idle_power:.2f} W")
            
            print(f"\n{'-'*100}")
            print(f"Individual Idle/Preprocessing Segments:")
            print(f"{'SEGMENT':<10} {'START (s)':<12} {'END (s)':<12} {'DURATION (s)':<15} {'ENERGY (kWh)':<15}")
            print(f"{'-'*100}")
            
            for i, boundary in enumerate(idle_programs, 1):
                print(f"#{i:<9} {boundary['start']:<12.1f} {boundary['end']:<12.1f} "
                      f"{boundary['duration']:<15.1f} {boundary['total_energy_kwh']:<15.4f}")
            
            print(f"{'-'*100}")
            print(f"{'TOTAL':<10} {'':<12} {'':<12} {total_idle_duration:<15.1f} {total_idle_energy_kwh:<15.4f}")
            print(f"{'-'*100}")


# Main execution
def main():
    """
    Main function for analyzing power and energy with sequential program analysis
    Calculates energy consumption (kWh) by integrating power over time
    """
    print("="*100)
    print("ENHANCED POWER & ENERGY ANALYZER - SEQUENTIAL PROGRAM ANALYSIS")
    print("="*100)
    print("This analyzer plots power for all programs of a part sequentially")
    print("Calculates energy consumption (kWh) by integrating power measurements over time")
    print("Uses partKindId (UUID) to detect actual program boundaries and idle times")
    print("="*100)
    
    # Initialize analyzer
    analyzer = ActivePowerAnalyzer(debug=True)
    
    print("\nSEQUENTIAL PROGRAM ANALYSIS MODE")
    print("="*80)
    
    # Get part number
    part_number = input("Enter part number (e.g., 26 for al6061_body26): ").strip()
    if not part_number:
        print("No part number entered. Using default: 26")
        part_number = "26"
    
    # Get part type
    part_type = input("Enter part type (body or lid, press Enter for body): ").strip().lower()
    if not part_type or part_type not in ['body', 'lid']:
        print("Invalid or no input. Using default: body")
        part_type = 'body'
    
    # Get directory
    directory = input("Enter directory path (or press Enter for current directory): ").strip()
    if not directory:
        directory = "."
    
    print(f"\nSearching for {part_type} programs for part #{part_number} in: {directory}")
    
    # Run sequential analysis
    result = analyzer.analyze_part_programs(part_number, part_type, directory)
    
    if result:
        combined_timeline, program_boundaries = result
        print("\n" + "="*100)
        print("SEQUENTIAL ANALYSIS COMPLETE")
        print("="*100)
        active_programs = [b for b in program_boundaries if b['program'] != 'NONE']
        idle_programs = [b for b in program_boundaries if b['program'] == 'NONE']
        total_energy = sum(b['total_energy_kwh'] for b in active_programs)
        idle_energy = sum(b['total_energy_kwh'] for b in idle_programs)
        
        # Count actual programs (1-4 for body, 1-2 for lid)
        num_actual_programs = 4 if part_type.lower() == 'body' else 2
        
        print(f"\nAnalyzed {num_actual_programs} programs with {len(idle_programs)} idle/preprocessing periods")
        print(f"Total data points: {len(combined_timeline)}")
        print(f"Total program energy: {total_energy:.4f} kWh")
        print(f"Total idle/preprocessing energy: {idle_energy:.4f} kWh")
        print(f"Total combined energy: {total_energy + idle_energy:.4f} kWh")
    else:
        print("\nSEQUENTIAL ANALYSIS FAILED - Please check error messages above")


if __name__ == "__main__":
    main()