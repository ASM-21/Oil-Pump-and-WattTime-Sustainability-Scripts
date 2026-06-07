import pandas as pd
import numpy as np
import os
import re
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import seaborn as sns

def parse_time_to_seconds(time_str):
    """
    Convert datetime string to total seconds from epoch or parse MM:SS.S format
    
    Args:
        time_str (str): Time in datetime format or MM:SS.S format
    
    Returns:
        float: Total seconds (unix timestamp for datetime, or seconds for MM:SS.S)
    """
    try:
        # First try to parse as datetime (which is the actual format in your data)
        if '-' in time_str and ':' in time_str and len(time_str) > 10:
            # This looks like a datetime string: '2025-09-10 14:40:00.473234'
            dt = pd.to_datetime(time_str)
            return dt.timestamp()
        else:
            # Fallback: try to parse as MM:SS.S format
            parts = time_str.split(':')
            minutes = int(parts[0])
            seconds = float(parts[1])
            return minutes * 60 + seconds
    except Exception as e:
        print(f"Warning: Could not parse time '{time_str}': {e}")
        return 0

def extract_part_info(filename):
    """
    Extract part type and number from filename
    
    Args:
        filename (str): CSV filename
    
    Returns:
        tuple: (part_type, part_number)
    """
    # Remove .csv extension
    base_name = filename.replace('.csv', '')
    
    # Define patterns for each part type
    patterns = {
        'DriveGear': r'DriveGear_Part(\d+)',
        'DriveShaft': r'DriveShaft_Part(\d+)', 
        'IdleGear': r'IdleGear_Part(\d+)',
        'IdleShaft': r'IdleShaft_Part(\d+)'
    }
    
    for part_type, pattern in patterns.items():
        match = re.match(pattern, base_name)
        if match:
            part_number = int(match.group(1))
            return part_type, part_number
    
    return 'Unknown', 0

def analyze_single_part(csv_file):
    """
    Analyze a single CSV file for energy consumption
    
    Args:
        csv_file (str): Path to CSV file
    
    Returns:
        dict: Analysis results
    """
    try:
        # Read CSV file
        df = pd.read_csv(csv_file)
        
        # Debug: Print first few rows and column info
        print(f"  Columns: {list(df.columns)}")
        print(f"  Total rows: {len(df)}")
        print(f"  Unique datanames: {df['Dataname'].unique() if 'Dataname' in df.columns else 'No Dataname column'}")
        
        # Filter for power readings only
        power_data = df[df['Dataname'] == 'power'].copy()
        
        if power_data.empty:
            print(f"  Warning: No power data found in {csv_file}")
            print(f"  Available datanames: {df['Dataname'].unique() if 'Dataname' in df.columns else 'None'}")
            return None
        
        print(f"  Found {len(power_data)} power readings")
        print(f"  Power value range: {power_data['Value'].min():.2f} - {power_data['Value'].max():.2f} W")
        
        # Debug: Show some time values
        print(f"  Sample time values: {power_data['Time'].head(3).tolist()}")
        
        # Convert time to seconds
        power_data['time_seconds'] = power_data['Time'].apply(parse_time_to_seconds)
        power_data = power_data.sort_values('time_seconds')
        
        # Debug: Show converted time values
        print(f"  Sample converted times: {power_data['time_seconds'].head(3).tolist()}")
        
        # Calculate time intervals between readings
        power_data['time_diff'] = power_data['time_seconds'].diff()
        
        # Debug: Show time differences
        print(f"  Sample time differences: {power_data['time_diff'].head(5).tolist()}")
        
        # For the first reading, use the median interval from subsequent readings
        valid_intervals = power_data['time_diff'].dropna()
        print(f"  Valid intervals count: {len(valid_intervals)}")
        print(f"  Valid intervals sample: {valid_intervals.head(5).tolist()}")
        
        if len(valid_intervals) > 0:
            # Use median interval to avoid outlier issues
            avg_interval = valid_intervals.median()
            print(f"  Calculated median interval: {avg_interval:.4f} seconds")
            
            # If median is still 0, there might be an issue with time parsing
            if avg_interval == 0:
                print("  Warning: Median interval is 0! Using default 0.5 seconds")
                avg_interval = 0.5
                
            power_data.iloc[0, power_data.columns.get_loc('time_diff')] = avg_interval
        else:
            # Fallback to 0.5 seconds
            avg_interval = 0.5
            power_data.iloc[0, power_data.columns.get_loc('time_diff')] = avg_interval
            print(f"  Using default 0.5 second interval")
        
        print(f"  Final average time interval: {avg_interval:.4f} seconds")
        
        # Calculate energy (power × time) and convert to kWh
        power_data['energy_kwh'] = (power_data['Value'] * power_data['time_diff']) / 3600000  # Convert to kWh
        
        # Also calculate total watts (sum of all power readings)
        total_watts = power_data['Value'].sum()
        
        # Debug: Show energy calculation
        total_energy_kwh = power_data['energy_kwh'].sum()
        print(f"  Sample energy calculations (kWh): {power_data['energy_kwh'].head(3).tolist()}")
        print(f"  Total energy calculated: {total_energy_kwh:.6f} kWh")
        print(f"  Total watts (sum of all readings): {total_watts:.2f} W")
        
        # Extract part information
        part_type, part_number = extract_part_info(os.path.basename(csv_file))
        
        # Calculate summary statistics
        avg_power = power_data['Value'].mean()
        peak_power = power_data['Value'].max()
        min_power = power_data['Value'].min()
        print_duration_min = (power_data['time_seconds'].max() - power_data['time_seconds'].min()) / 60
        num_readings = len(power_data)
        
        print(f"  Print duration: {print_duration_min:.2f} minutes")
        
        return {
            'filename': os.path.basename(csv_file),
            'part_type': part_type,
            'part_number': part_number,
            'total_energy_kwh': total_energy_kwh,
            'total_watts': total_watts,
            'print_duration_min': print_duration_min,
            'avg_power_w': avg_power,
            'peak_power_w': peak_power,
            'min_power_w': min_power,
            'num_readings': num_readings,
            'energy_per_minute_kwh': total_energy_kwh / print_duration_min if print_duration_min > 0 else 0
        }
        
    except Exception as e:
        print(f"  Error processing {csv_file}: {e}")
        import traceback
        traceback.print_exc()
        return None

def analyze_all_parts(directory="."):
    """
    Analyze all CSV files in directory and create summary
    
    Args:
        directory (str): Directory containing CSV files
    
    Returns:
        pd.DataFrame: Summary of all parts
    """
    # Find all relevant CSV files
    csv_files = []
    part_patterns = ['DriveGear_Part', 'DriveShaft_Part', 'IdleGear_Part', 'IdleShaft_Part']
    
    for file in os.listdir(directory):
        if file.endswith('.csv') and any(pattern in file for pattern in part_patterns):
            csv_files.append(os.path.join(directory, file))
    
    print(f"Found {len(csv_files)} CSV files to analyze:")
    for file in csv_files:
        print(f"  - {os.path.basename(file)}")
    
    # Analyze each file
    results = []
    for csv_file in csv_files:
        print(f"\nAnalyzing: {os.path.basename(csv_file)}")
        result = analyze_single_part(csv_file)
        if result:
            results.append(result)
    
    # Create summary DataFrame
    if results:
        summary_df = pd.DataFrame(results)
        
        # Sort by part type and part number
        summary_df = summary_df.sort_values(['part_type', 'part_number'])
        
        return summary_df
    else:
        print("No valid data found in any files!")
        return pd.DataFrame()

def create_summary_excel(summary_df, output_file="3D_Printer_Energy_Summary.xlsx"):
    """
    Create Excel file with summary and analysis
    
    Args:
        summary_df (pd.DataFrame): Summary data
        output_file (str): Output Excel filename
    """
    with pd.ExcelWriter(output_file, engine='openpyxl') as writer:
        # Main summary sheet
        summary_df.to_excel(writer, sheet_name='Energy Summary', index=False)
        
        # Statistics by part type
        part_type_stats = summary_df.groupby('part_type').agg({
            'total_energy_kwh': ['count', 'mean', 'std', 'min', 'max'],
            'total_watts': ['mean', 'std', 'min', 'max'],
            'print_duration_min': ['mean', 'std'],
            'avg_power_w': ['mean', 'std'],
            'peak_power_w': ['mean', 'max']
        }).round(6)
        
        # Flatten column names
        part_type_stats.columns = ['_'.join(col).strip() for col in part_type_stats.columns]
        part_type_stats.to_excel(writer, sheet_name='Part Type Statistics')
        
        # Individual part details
        for part_type in summary_df['part_type'].unique():
            part_data = summary_df[summary_df['part_type'] == part_type]
            part_data.to_excel(writer, sheet_name=f'{part_type} Details', index=False)
    
    print(f"\nExcel summary saved as: {output_file}")

def create_visualizations(summary_df):
    """
    Create visualization plots for energy analysis
    
    Args:
        summary_df (pd.DataFrame): Summary data
    """
    # Check if we have valid data
    if summary_df.empty or summary_df['total_energy_kwh'].sum() == 0:
        print("Warning: No valid energy data to visualize")
        return
    
    # Set up plotting style
    plt.style.use('seaborn-v0_8')
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))
    
    # 1. Energy consumption by part type (in kWh)
    ax1 = axes[0, 0]
    part_type_energy = summary_df.groupby('part_type')['total_energy_kwh'].mean()
    bars1 = ax1.bar(part_type_energy.index, part_type_energy.values, color='steelblue', alpha=0.7)
    ax1.set_title('Average Energy Consumption by Part Type', fontweight='bold')
    ax1.set_ylabel('Energy (kWh)')
    ax1.tick_params(axis='x', rotation=45)
    
    # Add value labels on bars
    for bar in bars1:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.6f}', ha='center', va='bottom')
    
    # 2. Total watts by part type
    ax2 = axes[0, 1]
    part_type_watts = summary_df.groupby('part_type')['total_watts'].mean()
    bars2 = ax2.bar(part_type_watts.index, part_type_watts.values, color='green', alpha=0.7)
    ax2.set_title('Average Total Watts by Part Type', fontweight='bold')
    ax2.set_ylabel('Total Watts')
    ax2.tick_params(axis='x', rotation=45)
    
    # Add value labels on bars
    for bar in bars2:
        height = bar.get_height()
        ax2.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.0f}', ha='center', va='bottom')
    
    # 3. Print duration vs Energy
    ax3 = axes[1, 0]
    ax3.scatter(summary_df['print_duration_min'], summary_df['total_energy_kwh'], 
               alpha=0.7, s=60, color='green')
    ax3.set_title('Print Duration vs Energy Consumption', fontweight='bold')
    ax3.set_xlabel('Print Duration (minutes)')
    ax3.set_ylabel('Energy (kWh)')
    ax3.grid(True, alpha=0.3)
    
    # Add trend line only if we have variation in data
    if summary_df['total_energy_kwh'].std() > 0 and summary_df['print_duration_min'].std() > 0:
        try:
            z = np.polyfit(summary_df['print_duration_min'], summary_df['total_energy_kwh'], 1)
            p = np.poly1d(z)
            ax3.plot(summary_df['print_duration_min'], p(summary_df['print_duration_min']), 
                     "r--", alpha=0.8, label=f'Trend: y={z[0]:.6f}x+{z[1]:.6f}')
            ax3.legend()
        except np.linalg.LinAlgError:
            print("Warning: Could not create trend line")
    
    # 4. Box plot of total watts by part type
    ax4 = axes[1, 1]
    part_types = summary_df['part_type'].unique()
    watts_by_type = [summary_df[summary_df['part_type'] == pt]['total_watts'].values 
                     for pt in part_types]
    
    box_plot = ax4.boxplot(watts_by_type, labels=part_types, patch_artist=True)
    ax4.set_title('Total Watts Distribution by Part Type', fontweight='bold')
    ax4.set_ylabel('Total Watts')
    ax4.tick_params(axis='x', rotation=45)
    
    # Color the boxes
    colors = ['lightblue', 'lightgreen', 'lightcoral', 'lightyellow']
    for patch, color in zip(box_plot['boxes'], colors[:len(box_plot['boxes'])]):
        patch.set_facecolor(color)
    
    plt.tight_layout()
    plt.savefig('3D_Printer_Energy_Analysis.png', dpi=300, bbox_inches='tight')
    plt.show()

def print_summary_report(summary_df):
    """
    Print a detailed summary report
    
    Args:
        summary_df (pd.DataFrame): Summary data
    """
    print("\n" + "="*80)
    print("3D PRINTER ENERGY CONSUMPTION ANALYSIS REPORT")
    print("="*80)
    
    # Overall statistics
    total_parts = len(summary_df)
    total_energy = summary_df['total_energy_kwh'].sum()
    avg_energy = summary_df['total_energy_kwh'].mean()
    total_watts_sum = summary_df['total_watts'].sum()
    
    print(f"\nOVERALL SUMMARY:")
    print(f"  Total parts analyzed: {total_parts}")
    print(f"  Total energy consumed: {total_energy:.6f} kWh ({total_energy*1000:.3f} Wh)")
    print(f"  Average energy per part: {avg_energy:.6f} kWh ({avg_energy*1000:.3f} Wh)")
    print(f"  Total watts (sum of all readings): {total_watts_sum:.1f} W")
    
    # Part type breakdown
    print(f"\nENERGY BY PART TYPE:")
    for part_type in summary_df['part_type'].unique():
        part_data = summary_df[summary_df['part_type'] == part_type]
        count = len(part_data)
        total = part_data['total_energy_kwh'].sum()
        avg = part_data['total_energy_kwh'].mean()
        std = part_data['total_energy_kwh'].std()
        total_watts_type = part_data['total_watts'].sum()
        
        print(f"  {part_type}:")
        print(f"    Count: {count} parts")
        print(f"    Total: {total:.6f} kWh ({total*1000:.3f} Wh)")
        print(f"    Average: {avg:.6f} ± {std:.6f} kWh")
        print(f"    Total watts: {total_watts_type:.1f} W")
    
    # Top energy consumers
    print(f"\nTOP 5 ENERGY CONSUMERS:")
    top_consumers = summary_df.nlargest(5, 'total_energy_kwh')
    for idx, row in top_consumers.iterrows():
        print(f"  {row['filename']}: {row['total_energy_kwh']:.6f} kWh ({row['total_watts']:.1f} W total)")
    
    # Most efficient parts
    print(f"\nMOST EFFICIENT PARTS:")
    most_efficient = summary_df.nsmallest(5, 'total_energy_kwh')
    for idx, row in most_efficient.iterrows():
        print(f"  {row['filename']}: {row['total_energy_kwh']:.6f} kWh ({row['total_watts']:.1f} W total)")

def debug_csv_file(csv_file):
    """
    Debug function to examine CSV file structure
    
    Args:
        csv_file (str): Path to CSV file
    """
    print(f"\nDEBUGGING: {csv_file}")
    print("-" * 50)
    
    try:
        # Read raw CSV
        df = pd.read_csv(csv_file)
        
        print(f"Shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        print("\nFirst 10 rows:")
        print(df.head(10))
        
        print(f"\nUnique values in 'Dataname' column:")
        if 'Dataname' in df.columns:
            print(df['Dataname'].value_counts())
        
        # Check for power data
        if 'Dataname' in df.columns:
            power_data = df[df['Dataname'] == 'power']
            print(f"\nPower data found: {len(power_data)} rows")
            if len(power_data) > 0:
                print("Sample power data:")
                print(power_data.head())
                print(f"Power range: {power_data['Value'].min()} - {power_data['Value'].max()}")
        
    except Exception as e:
        print(f"Error reading file: {e}")

# Main execution function
def main():
    """
    Main function to run the complete analysis
    """
    print("3D Printer Energy Consumption Analysis")
    print("="*50)
    
    # First, let's debug a single file to see what's happening
    csv_files = []
    part_patterns = ['DriveGear_Part', 'DriveShaft_Part', 'IdleGear_Part', 'IdleShaft_Part']
    
    for file in os.listdir("."):
        if file.endswith('.csv') and any(pattern in file for pattern in part_patterns):
            csv_files.append(file)
    
    if csv_files:
        print(f"\nDebugging first file: {csv_files[0]}")
        debug_csv_file(csv_files[0])
        
        # Ask user if they want to continue
        print(f"\nFound {len(csv_files)} files total. Continue with full analysis? (y/n)")
        # For now, let's continue automatically
        proceed = 'y'  # input().lower()
        
        if proceed == 'y':
            # Analyze all parts
            summary_df = analyze_all_parts()
            
            if summary_df.empty:
                print("No data found to analyze!")
                return
            
            # Print summary report
            print_summary_report(summary_df)
            
            # Create Excel summary
            create_summary_excel(summary_df)
            
            # Create visualizations only if we have valid data
            if summary_df['total_energy_kwh'].sum() > 0:
                create_visualizations(summary_df)
                print(f"\nAnalysis complete! Check the generated files:")
                print(f"  - 3D_Printer_Energy_Summary.xlsx")
                print(f"  - 3D_Printer_Energy_Analysis.png")
            else:
                print("\nNo energy data found - skipping visualizations")
                print("Check the Excel file for detailed debugging info")
    else:
        print("No CSV files found matching the expected patterns!")

if __name__ == "__main__":
    main()