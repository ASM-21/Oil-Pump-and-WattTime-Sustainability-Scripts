import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import seaborn as sns

def plot_3d_printer_data(csv_file):
    """
    Read 3D printer data from CSV and create separate plots for each metric over time.
    
    Args:
        csv_file (str): Path to the CSV file containing the 3D printer data
    """
    
    # Read the CSV file
    try:
        df = pd.read_csv(csv_file)
        print(f"Successfully loaded {len(df)} data points from {csv_file}")
    except FileNotFoundError:
        print(f"Error: Could not find file {csv_file}")
        return
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return
    
    # Convert Time column to datetime
    df['Time'] = pd.to_datetime(df['Time'])
    
    # Get unique metrics
    metrics = df['Dataname'].unique()
    print(f"Found metrics: {', '.join(metrics)}")
    
    # Set up the plotting style
    plt.style.use('seaborn-v0_8')
    
    # Create subplot layout - adjust rows and columns based on number of metrics
    n_metrics = len(metrics)
    if n_metrics <= 2:
        rows, cols = 1, n_metrics
    elif n_metrics <= 4:
        rows, cols = 2, 2
    else:
        rows = (n_metrics + 2) // 3  # Round up division
        cols = 3
    
    # Create figure with subplots
    fig, axes = plt.subplots(rows, cols, figsize=(15, 4*rows))
    
    # If only one subplot, axes won't be an array
    if n_metrics == 1:
        axes = [axes]
    elif rows == 1:
        axes = axes if n_metrics > 1 else [axes]
    else:
        axes = axes.flatten()
    
    # Plot each metric
    for i, metric in enumerate(metrics):
        # Filter data for current metric
        metric_data = df[df['Dataname'] == metric].copy()
        metric_data = metric_data.sort_values('Time')  # Ensure chronological order
        
        # Create the plot
        ax = axes[i]
        ax.plot(metric_data['Time'], metric_data['Value'], 
                marker='o', markersize=3, linewidth=1.5, alpha=0.8)
        
        # Customize the plot
        ax.set_title(f'{metric.replace("_", " ").title()} Over Time', 
                    fontsize=12, fontweight='bold')
        ax.set_xlabel('Time', fontsize=10)
        ax.set_ylabel('Value', fontsize=10)
        ax.grid(True, alpha=0.3)
        
        # Format x-axis to show time nicely
        ax.tick_params(axis='x', rotation=45)
        
        # Add some statistics to the plot
        mean_val = metric_data['Value'].mean()
        ax.axhline(y=mean_val, color='red', linestyle='--', alpha=0.5, 
                  label=f'Mean: {mean_val:.2f}')
        ax.legend(fontsize=8)
    
    # Hide empty subplots if any
    for j in range(i+1, len(axes)):
        axes[j].set_visible(False)
    
    # Adjust layout to prevent overlap
    plt.tight_layout()
    
    # Show the plot
    plt.show()
    
    # Print summary statistics
    print("\n" + "="*50)
    print("SUMMARY STATISTICS")
    print("="*50)
    
    for metric in metrics:
        metric_data = df[df['Dataname'] == metric]['Value']
        print(f"\n{metric.upper()}:")
        print(f"  Count: {len(metric_data)}")
        print(f"  Mean: {metric_data.mean():.3f}")
        print(f"  Std Dev: {metric_data.std():.3f}")
        print(f"  Min: {metric_data.min():.3f}")
        print(f"  Max: {metric_data.max():.3f}")

def save_individual_plots(csv_file, output_dir="plots"):
    """
    Create and save individual plots for each metric.
    
    Args:
        csv_file (str): Path to the CSV file
        output_dir (str): Directory to save individual plots
    """
    import os
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Read the data
    df = pd.read_csv(csv_file)
    df['Time'] = pd.to_datetime(df['Time'])
    
    metrics = df['Dataname'].unique()
    
    for metric in metrics:
        # Filter data for current metric
        metric_data = df[df['Dataname'] == metric].copy()
        metric_data = metric_data.sort_values('Time')
        
        # Create individual plot
        plt.figure(figsize=(10, 6))
        plt.plot(metric_data['Time'], metric_data['Value'], 
                marker='o', markersize=4, linewidth=2, color='steelblue')
        
        plt.title(f'{metric.replace("_", " ").title()} Over Time', 
                 fontsize=14, fontweight='bold')
        plt.xlabel('Time', fontsize=12)
        plt.ylabel('Value', fontsize=12)
        plt.grid(True, alpha=0.3)
        plt.xticks(rotation=45)
        
        # Add mean line
        mean_val = metric_data['Value'].mean()
        plt.axhline(y=mean_val, color='red', linestyle='--', alpha=0.7, 
                   label=f'Mean: {mean_val:.2f}')
        plt.legend()
        
        plt.tight_layout()
        
        # Save the plot
        filename = f"{metric}_over_time.png"
        filepath = os.path.join(output_dir, filename)
        plt.savefig(filepath, dpi=300, bbox_inches='tight')
        print(f"Saved: {filepath}")
        
        plt.close()  # Close to free memory

# Main execution
if __name__ == "__main__":
    
    csv_filename = r"C:\Users\Administrator\OneDrive - purdue.edu\Documents\python\__pycache__\Research python\Raw Data from IN-MaC Part Runs\DriveShaft_Part16.csv"
    
    print("3D Printer Data Visualization")
    print(f"Reading data from: {csv_filename}")
    print("="*40)
    
    # Create combined subplot view
    plot_3d_printer_data(csv_filename)
    
    # Optionally save individual plots
    save_choice = input("\nWould you like to save individual plots? (y/n): ").lower()
    if save_choice == 'y':
        save_individual_plots(csv_filename)
        print("Individual plots saved in 'plots' directory!")