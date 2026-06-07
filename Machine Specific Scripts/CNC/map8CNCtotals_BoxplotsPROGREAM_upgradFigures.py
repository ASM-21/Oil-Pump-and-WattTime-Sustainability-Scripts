import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import os
import glob
import re
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

class AllProgramsEnergyAnalyzer:
    """
    Analyzes all programs (all body or all lid) and creates comprehensive comparison plots
    Professional version for ASME MSEC conference submission
    """
    
    def __init__(self, debug=True):
        self.debug = debug
        self.uuid_to_operation = {}
        self.partkind_to_program = {}
        self.program_uuid_map = {}
        self.all_programs_data = {}  # {program_name: {part_name: {operation: energy}}}
        self.setup_partkind_mapping()
        self.setup_uuid_operation_mapping()
        
        # Set publication-quality matplotlib parameters
        self.setup_publication_style()
        
    def setup_publication_style(self):
        """Setup matplotlib parameters for publication-quality figures"""
        plt.rcParams.update({
            'font.size': 10,
            'font.family': 'serif',
            'font.serif': ['Times New Roman', 'DejaVu Serif'],
            'axes.labelsize': 11,
            'axes.titlesize': 12,
            'xtick.labelsize': 9,
            'ytick.labelsize': 10,
            'legend.fontsize': 9,
            'figure.dpi': 300,
            'savefig.dpi': 300,
            'lines.linewidth': 1.0,
            'axes.linewidth': 0.8,
            'grid.linewidth': 0.5,
            'xtick.major.width': 0.8,
            'ytick.major.width': 0.8,
        })
        
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
            if program != 'NONE':
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
    
    def analyze_single_file_for_program(self, csv_filepath, target_program_name):
        """
        Analyze a single CSV file but only extract data for the specified program
        Returns: {operation: energy_kwh} dictionary for this part
        """
        basename = os.path.basename(csv_filepath)
        self.log(f"\nAnalyzing {basename} for program {target_program_name}")
        
        try:
            csv_data = pd.read_csv(csv_filepath)
            csv_data['Time'] = pd.to_datetime(csv_data['Time'])
        except Exception as e:
            print(f"ERROR loading {basename}: {e}")
            return None
        
        target_uuid = self.program_uuid_map.get(target_program_name)
        if not target_uuid:
            print(f"ERROR: Unknown program {target_program_name}")
            return None
        
        processkindid_data = csv_data[csv_data['Dataname'] == 'processKindId'].copy()
        partkindid_data = csv_data[csv_data['Dataname'] == 'partKindId'].copy()
        power_data = csv_data[csv_data['Dataname'] == 'active power'].copy()
        
        if processkindid_data.empty or partkindid_data.empty or power_data.empty:
            print(f"WARNING: Missing data streams in {basename}")
            return None
        
        processkindid_data = processkindid_data[['Time', 'Value']].rename(columns={'Value': 'UUID'})
        partkindid_data = partkindid_data[['Time', 'Value']].rename(columns={'Value': 'PartKindId'})
        power_data = power_data[['Time', 'Value']].rename(columns={'Value': 'Power_W'})
        
        power_data['Power_W'] = pd.to_numeric(power_data['Power_W'], errors='coerce')
        power_data['Power_W'] = power_data['Power_W'].clip(lower=0)
        
        timeline_data = pd.merge(processkindid_data, partkindid_data, on='Time', how='inner')
        timeline_data = pd.merge(timeline_data, power_data, on='Time', how='inner')
        timeline_data = timeline_data.sort_values('Time').reset_index(drop=True)
        
        timeline_data['time_diff_hours'] = timeline_data['Time'].diff().dt.total_seconds() / 3600
        timeline_data = timeline_data.iloc[1:].reset_index(drop=True)
        timeline_data['energy_kwh'] = timeline_data['Power_W'] * timeline_data['time_diff_hours'] / 1000
        
        timeline_data['PartKindId_Upper'] = timeline_data['PartKindId'].str.strip().str.upper()
        target_uuid_upper = target_uuid.upper()
        
        filtered_data = timeline_data[timeline_data['PartKindId_Upper'] == target_uuid_upper].copy()
        
        if filtered_data.empty:
            print(f"WARNING: No data found for {target_program_name} in {basename}")
            return None
        
        self.log(f"  Filtered to {len(filtered_data)} rows matching program UUID")
        
        filtered_data['Operation'] = filtered_data['UUID'].apply(
            lambda x: self.uuid_to_operation.get(str(x).strip().upper(), 'Unknown')
        )
        
        operation_energy = {}
        for operation, group in filtered_data.groupby('Operation'):
            if operation == 'Unknown':
                continue
            total_energy = group['energy_kwh'].sum()
            operation_energy[operation] = total_energy
        
        self.log(f"  Found {len(operation_energy)} operations with energy data")
        
        return operation_energy
    
    def analyze_all_programs(self, directory, part_type):
        """
        Analyze all programs for a given part type (body or lid)
        """
        print(f"\n{'='*100}")
        print(f"ANALYZING ALL {part_type.upper()} PROGRAMS")
        print(f"{'='*100}")
        
        # Determine program numbers
        if part_type.lower() == 'body':
            program_numbers = [1, 2, 3, 4]
        else:
            program_numbers = [1, 2]
        
        # Analyze each program
        for program_num in program_numbers:
            program_name = f'PROGRAM_{program_num}_{part_type.capitalize()}'
            
            print(f"\n{'-'*100}")
            print(f"Processing {program_name}")
            print(f"{'-'*100}")
            
            # Find files
            pattern = os.path.join(directory, f"*_{part_type}*_p{program_num}.csv")
            files = glob.glob(pattern)
            files.sort()
            
            if not files:
                print(f"  No files found for {program_name}")
                continue
            
            print(f"  Found {len(files)} files")
            
            # Analyze each file
            program_parts_data = {}
            
            for filepath in files:
                basename = os.path.basename(filepath)
                
                # Extract part name
                match = re.search(r'_(body|lid)(\d+)_', basename, re.IGNORECASE)
                if match:
                    part_name = f"{match.group(1)}{match.group(2)}"
                else:
                    part_name = basename
                
                operation_energy = self.analyze_single_file_for_program(filepath, program_name)
                
                if operation_energy is not None:
                    program_parts_data[part_name] = operation_energy
                    print(f"    ✓ {part_name}: {sum(operation_energy.values()):.4f} kWh")
            
            if program_parts_data:
                self.all_programs_data[program_name] = program_parts_data
                print(f"  Successfully processed {len(program_parts_data)} parts for {program_name}")
        
        if not self.all_programs_data:
            print(f"\nERROR: No data found for any {part_type} programs")
            return False
        
        print(f"\n{'='*100}")
        print(f"Successfully loaded {len(self.all_programs_data)} programs")
        print(f"{'='*100}")
        
        return True
    
    def plot_all_operations_combined(self, part_type, save_path=None):
        """
        Figure 1: All operations from all programs combined
        Professional version for ASME conference
        """
        print(f"\n{'='*100}")
        print(f"CREATING COMBINED OPERATIONS BOXPLOT FOR ALL {part_type.upper()} PROGRAMS")
        print(f"{'='*100}")
        
        # Collect all unique operations across all programs
        all_operations = set()
        for program_data in self.all_programs_data.values():
            for part_data in program_data.values():
                all_operations.update(part_data.keys())
        
        all_operations = sorted(all_operations)
        
        print(f"Found {len(all_operations)} unique operations across all programs")
        
        # For each operation, collect energy values from all programs
        operation_data = []
        operation_labels = []
        operation_stats = []
        
        for operation in all_operations:
            values = []
            
            # Collect from all programs and all parts
            for program_name, program_data in self.all_programs_data.items():
                for part_name, part_operations in program_data.items():
                    if operation in part_operations:
                        values.append(part_operations[operation])
            
            # Only include if we have data
            if values:
                operation_data.append(values)
                # Shorten labels for readability
                label = operation.replace('_', ' ').title()
                if len(label) > 25:
                    label = label[:22] + '...'
                operation_labels.append(label)
                operation_stats.append({
                    'mean': np.mean(values),
                    'std': np.std(values),
                    'n': len(values)
                })
                print(f"  {operation}: {len(values)} data points")
        
        # Create figure - ASME two-column format (7" for full-width figure)
        fig, ax = plt.subplots(figsize=(7, 4.5))
        
        # Create boxplot with professional styling
        bp = ax.boxplot(operation_data, 
                        labels=operation_labels,
                        patch_artist=True,
                        widths=0.6,
                        showmeans=True,
                        meanprops=dict(marker='D', markerfacecolor='red', 
                                      markeredgecolor='red', markersize=3),
                        medianprops=dict(color='black', linewidth=1.2),
                        boxprops=dict(facecolor='lightgray', edgecolor='black', 
                                     linewidth=0.8),
                        whiskerprops=dict(color='black', linewidth=0.8),
                        capprops=dict(color='black', linewidth=0.8),
                        flierprops=dict(marker='o', markerfacecolor='white', 
                                       markersize=3, markeredgecolor='black',
                                       markeredgewidth=0.5, alpha=0.5))
        
        # Grayscale-friendly coloring (important for print)
        grays = plt.cm.Greys(np.linspace(0.3, 0.7, len(operation_data)))
        for patch, gray in zip(bp['boxes'], grays):
            patch.set_facecolor(gray)
            patch.set_alpha(0.8)
        
        # Professional title without excessive formatting
        ax.set_title(f'Energy Distribution of {part_type.capitalize()} Manufacturing Operations', 
                    fontsize=12, fontweight='bold', pad=15)
        
        ax.set_ylabel('Energy Consumption (kWh)', fontsize=11, fontweight='bold')
        ax.set_xlabel('Manufacturing Operation', fontsize=11, fontweight='bold')
        
        # Rotate x-axis labels for readability
        ax.tick_params(axis='x', rotation=45, labelsize=8)
        ax.tick_params(axis='y', labelsize=10)
        
        # Professional grid
        ax.grid(True, alpha=0.3, axis='y', linestyle='--', linewidth=0.5)
        ax.set_axisbelow(True)  # Grid behind data
        
        # Set y-axis to start at 0
        ax.set_ylim(bottom=0)
        
        # Add legend for boxplot elements
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], color='black', linewidth=1.2, label='Median'),
            Line2D([0], [0], marker='D', color='w', markerfacecolor='red', 
                   markersize=5, label='Mean'),
            Line2D([0], [0], marker='o', color='w', markerfacecolor='white',
                   markeredgecolor='black', markersize=4, label='Outliers')
        ]
        ax.legend(handles=legend_elements, loc='upper right', 
                 frameon=True, fancybox=False, edgecolor='black',
                 fontsize=8)
        
        # Add sample size annotation
        total_parts = sum(len(prog_data) for prog_data in self.all_programs_data.values())
        annotation = (f'Programs: {len(self.all_programs_data)}, '
                     f'Parts: {total_parts}, '
                     f'Operations: {len(operation_data)}')
        ax.text(0.02, 0.98, annotation, transform=ax.transAxes, 
               fontsize=9, verticalalignment='top',
               bbox=dict(boxstyle='round', facecolor='white', 
                        edgecolor='black', linewidth=0.8, alpha=0.9))
        
        plt.tight_layout()
        
        # Save with high quality
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight', 
                       facecolor='white', edgecolor='none')
            print(f"Saved to: {save_path}")
        
        plt.show()
    
    def plot_program_comparison(self, part_type, save_path=None):
        """
        Figure 2: Compare total energy across programs
        Professional version for ASME conference
        """
        print(f"\n{'='*100}")
        print(f"CREATING PROGRAM COMPARISON BOXPLOT FOR {part_type.upper()}")
        print(f"{'='*100}")
        
        # Collect total energy for each program
        program_names = sorted(self.all_programs_data.keys())
        program_totals = []
        program_stats = []
        
        for program_name in program_names:
            program_data = self.all_programs_data[program_name]
            
            # Calculate total energy for each part in this program
            part_totals = [sum(part_ops.values()) for part_ops in program_data.values()]
            program_totals.append(part_totals)
            
            program_stats.append({
                'name': program_name,
                'n': len(part_totals),
                'mean': np.mean(part_totals),
                'std': np.std(part_totals),
                'min': np.min(part_totals),
                'max': np.max(part_totals)
            })
            
            print(f"{program_name}: n={len(part_totals)}, "
                  f"μ={np.mean(part_totals):.4f} kWh, "
                  f"σ={np.std(part_totals):.4f} kWh")
        
        # Create figure - ASME column format
        fig, ax = plt.subplots(figsize=(7, 4.5))
        
        # Create professional boxplot
        positions = np.arange(1, len(program_names) + 1)
        bp = ax.boxplot(program_totals, 
                        positions=positions,
                        labels=program_names,
                        patch_artist=True,
                        widths=0.6,
                        showmeans=True,
                        meanprops=dict(marker='D', markerfacecolor='red', 
                                      markeredgecolor='darkred', markersize=5),
                        medianprops=dict(color='black', linewidth=2.0),
                        boxprops=dict(edgecolor='black', linewidth=0.8),
                        whiskerprops=dict(color='black', linewidth=0.8, linestyle='-'),
                        capprops=dict(color='black', linewidth=0.8),
                        flierprops=dict(marker='o', markerfacecolor='white', 
                                       markersize=4, markeredgecolor='black',
                                       markeredgewidth=0.6))
        
        # Use grayscale gradient for print-friendly output
        colors = plt.cm.gray_r(np.linspace(0.3, 0.8, len(program_names)))
        for patch, color in zip(bp['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
            patch.set_edgecolor('black')
            patch.set_linewidth(0.8)
        
        # Professional title
        ax.set_title(f'Total Energy Consumption Comparison: {part_type.capitalize()} Programs', 
                    fontsize=12, fontweight='bold', pad=15)
        
        ax.set_ylabel('Total Energy per Part (kWh)', fontsize=11, fontweight='bold')
        ax.set_xlabel('Manufacturing Program', fontsize=11, fontweight='bold')
        
        # Clean up x-axis labels with sample size included
        cleaned_labels = []
        for name, stats in zip(program_names, program_stats):
            clean_name = name.replace('PROGRAM_', 'P').replace(f'_{part_type.capitalize()}', '')
            cleaned_labels.append(f'{clean_name}\n(n={stats["n"]})')
        
        ax.set_xticklabels(cleaned_labels, fontsize=10)
        ax.tick_params(axis='both', labelsize=10)
        
        # Professional grid
        ax.grid(True, alpha=0.3, axis='y', linestyle='--', linewidth=0.5)
        ax.set_axisbelow(True)
        
        # Set appropriate y-axis limits with more space
        all_values = [val for prog in program_totals for val in prog]
        y_max = max(all_values)
        ax.set_ylim(bottom=0, top=y_max * 1.25)
        
        # Add mean value above boxes (removed from text to reduce clutter)
        for i, (pos, stats) in enumerate(zip(positions, program_stats)):
            y_pos = stats['mean'] + 0.02 * y_max
            ax.text(pos, y_pos, f'{stats["mean"]:.3f}', 
                   ha='center', va='bottom', fontsize=7,
                   bbox=dict(boxstyle='round,pad=0.3', facecolor='white', 
                            edgecolor='gray', linewidth=0.5, alpha=0.8))
        
        # Add legend - moved to upper right and made more compact
        from matplotlib.lines import Line2D
        legend_elements = [
            Line2D([0], [0], marker='D', color='w', markerfacecolor='red', 
                   markeredgecolor='darkred', markersize=6, label='Mean', linestyle='None'),
            Line2D([0], [0], color='black', linewidth=2.0, label='Median'),
        ]
        ax.legend(handles=legend_elements, loc='upper right', 
                 frameon=True, fancybox=False, edgecolor='black',
                 fontsize=9, framealpha=0.95)
        
        plt.tight_layout()
        
        # Save with high quality
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight',
                       facecolor='white', edgecolor='none')
            print(f"Saved to: {save_path}")
        
        plt.show()
        
        # Print detailed statistics table
        print(f"\n{'='*100}")
        print("STATISTICAL SUMMARY")
        print(f"{'='*100}")
        print(f"{'Program':<20} {'n':>5} {'Mean':>10} {'Std':>10} {'Min':>10} {'Max':>10} {'CV%':>8}")
        print(f"{'-'*100}")
        for stats in program_stats:
            cv = (stats['std'] / stats['mean'] * 100) if stats['mean'] > 0 else 0
            print(f"{stats['name']:<20} {stats['n']:>5} {stats['mean']:>10.4f} "
                  f"{stats['std']:>10.4f} {stats['min']:>10.4f} {stats['max']:>10.4f} {cv:>7.2f}%")
    
    def export_statistics_table(self, part_type, output_path=None):
        """
        Export statistics table in format suitable for ASME paper
        """
        if output_path is None:
            output_path = f'statistics_table_{part_type}.csv'
        
        # Prepare data
        rows = []
        for program_name in sorted(self.all_programs_data.keys()):
            program_data = self.all_programs_data[program_name]
            part_totals = [sum(part_ops.values()) for part_ops in program_data.values()]
            
            rows.append({
                'Program': program_name,
                'Sample Size': len(part_totals),
                'Mean (kWh)': f'{np.mean(part_totals):.4f}',
                'Std Dev (kWh)': f'{np.std(part_totals):.4f}',
                'Min (kWh)': f'{np.min(part_totals):.4f}',
                'Max (kWh)': f'{np.max(part_totals):.4f}',
                'CV (%)': f'{np.std(part_totals)/np.mean(part_totals)*100:.2f}'
            })
        
        df = pd.DataFrame(rows)
        df.to_csv(output_path, index=False)
        print(f"Statistics table saved to: {output_path}")
        
        # Also print LaTeX table format for ASME paper
        print("\nLaTeX Table Format:")
        print("\\begin{table}[h]")
        print("\\caption{Energy Consumption Statistics by Program}")
        print("\\label{tab:energy_stats}")
        print("\\begin{tabular}{lcccccc}")
        print("\\hline")
        print("Program & n & Mean & Std Dev & Min & Max & CV \\\\")
        print("& & (kWh) & (kWh) & (kWh) & (kWh) & (\\%) \\\\")
        print("\\hline")
        for _, row in df.iterrows():
            print(f"{row['Program']} & {row['Sample Size']} & {row['Mean (kWh)']} & "
                  f"{row['Std Dev (kWh)']} & {row['Min (kWh)']} & {row['Max (kWh)']} & "
                  f"{row['CV (%)']} \\\\")
        print("\\hline")
        print("\\end{tabular}")
        print("\\end{table}")
    
    def print_summary(self, part_type):
        """
        Print comprehensive summary
        """
        print(f"\n{'='*100}")
        print(f"COMPREHENSIVE SUMMARY - ALL {part_type.upper()} PROGRAMS")
        print(f"{'='*100}")
        
        for program_name in sorted(self.all_programs_data.keys()):
            program_data = self.all_programs_data[program_name]
            
            print(f"\n{program_name}:")
            print(f"  Parts analyzed: {len(program_data)}")
            
            # Collect all operations
            all_ops = set()
            for part_data in program_data.values():
                all_ops.update(part_data.keys())
            
            print(f"  Unique operations: {len(all_ops)}")
            
            # Calculate total energy statistics
            part_totals = [sum(part_ops.values()) for part_ops in program_data.values()]
            print(f"  Total energy - Mean: {np.mean(part_totals):.4f} kWh, "
                  f"Std: {np.std(part_totals):.4f} kWh, "
                  f"Range: [{np.min(part_totals):.4f}, {np.max(part_totals):.4f}]")
    
    def analyze_and_plot(self, directory, part_type, save_figures=True):
        """
        Complete analysis pipeline with figure saving
        """
        # Analyze all programs
        success = self.analyze_all_programs(directory, part_type)
        
        if not success:
            return False
        
        # Print summary
        self.print_summary(part_type)
        
        # Create output directory for figures
        if save_figures:
            output_dir = os.path.join(directory, 'conference_figures')
            os.makedirs(output_dir, exist_ok=True)
            
            save_path_1 = os.path.join(output_dir, f'Fig1_All_Operations_{part_type}.pdf')
            save_path_2 = os.path.join(output_dir, f'Fig2_Program_Comparison_{part_type}.pdf')
            stats_path = os.path.join(output_dir, f'statistics_table_{part_type}.csv')
        else:
            save_path_1 = None
            save_path_2 = None
            stats_path = None
        
        # Create visualizations
        self.plot_all_operations_combined(part_type, save_path=save_path_1)
        self.plot_program_comparison(part_type, save_path=save_path_2)
        
        # Export statistics table
        if save_figures:
            self.export_statistics_table(part_type, output_path=stats_path)
        
        return True


# Main execution
def main():
    """
    Main function for all-programs analysis - Professional ASME version
    """
    print("="*100)
    print("ALL PROGRAMS ENERGY ANALYZER - ASME MSEC CONFERENCE VERSION")
    print("="*100)
    print("Generates publication-quality figures at 300 DPI with professional formatting")
    print("Outputs PDF figures and LaTeX-formatted statistics tables")
    print("="*100)
    
    # Initialize analyzer
    analyzer = AllProgramsEnergyAnalyzer(debug=False)
    
    # Get directory
    directory = input("\nEnter directory path (or press Enter for current directory): ").strip()
    if not directory:
        directory = "."
    
    if not os.path.exists(directory):
        print(f"ERROR: Directory not found: {directory}")
        return
    
    # Get part type
    print("\nSelect Part Type:")
    print("  1. Body (4 programs)")
    print("  2. Lid (2 programs)")
    part_type_choice = input("Enter choice (1 or 2): ").strip()
    
    if part_type_choice == "1":
        part_type = "body"
    elif part_type_choice == "2":
        part_type = "lid"
    else:
        print("Invalid choice")
        return
    
    # Ask about saving
    save_choice = input("\nSave figures as PDF files? (y/n, default=y): ").strip().lower()
    save_figures = save_choice != 'n'
    
    # Run analysis
    success = analyzer.analyze_and_plot(directory, part_type, save_figures=save_figures)
    
    if success:
        print("\n" + "="*100)
        print("ALL PROGRAMS ANALYSIS COMPLETE")
        if save_figures:
            print(f"Figures saved to: {os.path.join(directory, 'conference_figures')}")
            print("Files generated:")
            print(f"  - Fig1_All_Operations_{part_type}.pdf")
            print(f"  - Fig2_Program_Comparison_{part_type}.pdf")
            print(f"  - statistics_table_{part_type}.csv")
        print("="*100)
    else:
        print("\nANALYSIS FAILED")


if __name__ == "__main__":
    main()