import time
import datetime
import numpy as np
import matplotlib.pyplot as plt
from muse.muse import Muse
from muse.muse_memory import MuseMemory
from muse.dj_persona import DJPersona

def create_test_persona(last_hello_time=None, last_signoff_time=None):
    """Helper function to create a test persona with specific timing."""
    persona = DJPersona(
        name="Test DJ",
        voice_name="test_voice",
        language="English",
        language_code="en",
        s="M",
        tone="friendly",
        characteristics=["energetic", "knowledgeable"],
        system_prompt="You are a friendly DJ.",
        is_mock=True
    )
    if last_hello_time is not None:
        persona.last_hello_time = last_hello_time
    if last_signoff_time is not None:
        persona.last_signoff_time = last_signoff_time
    return persona

def get_mock_muse():
    class MockMuseArgs:
        placeholder = True
    return Muse(MockMuseArgs(), None)

def format_time(timestamp):
    """Format a timestamp into a readable string."""
    if timestamp is None or timestamp == 0:
        return "Never"
    return datetime.datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')

def format_time_diff(seconds):
    """Format a time difference into a readable string."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds/60)}m"
    elif seconds < 86400:
        return f"{int(seconds/3600)}h"
    else:
        return f"{int(seconds/86400)}d"

def test_case(muse, name, persona, expected_result, now=None):
    """Helper function to run a test case and print the result."""
    result = muse._determine_intro_type(now, persona)
    print("\n" + "="*80)
    print(f"Test Case: {name}")
    print("-"*40)
    
    # Calculate time differences
    hello_to_signoff = None
    signoff_to_now = None
    if persona.last_hello_time and persona.last_signoff_time:
        hello_to_signoff = persona.last_signoff_time - persona.last_hello_time
    if persona.last_signoff_time and now:
        signoff_to_now = now - persona.last_signoff_time
    
    # Print times and differences
    print(f"Hello: {format_time(persona.last_hello_time)} | Signoff: {format_time(persona.last_signoff_time)} | Current: {format_time(now)}")
    print(f"           Time since hello: {format_time_diff(hello_to_signoff) if hello_to_signoff is not None else 'N/A'}        |        Time since signoff: {format_time_diff(signoff_to_now) if signoff_to_now is not None else 'N/A'}")
    print("-"*40)
    
    status = "✓ PASS" if result == expected_result else "✗ FAIL"
    if result == expected_result:
        print(f"Expected: {expected_result} | Got: {result} | Status: {status}")
    else:
        print(f"\033[91mExpected: {expected_result} | Got: {result} | Status: {status}\033[0m")

def visualize_outcomes(muse, reference_timestamp, hours=48):
    """Create a 2D heatmap showing the distribution of outcomes based on hello and signoff times."""
    # Create a grid of times
    time_points = np.linspace(0, hours * 3600, 100)  # 100 points over 48 hours
    outcomes = np.zeros((len(time_points), len(time_points)))
    persona = create_test_persona()
    
    # For each combination of hello and signoff times
    for i, hello_offset in enumerate(time_points):
        for j, signoff_offset in enumerate(time_points):
            # Skip invalid combinations (signoff before hello)
            if signoff_offset > hello_offset:  # Fixed condition: signoff_offset > hello_offset means signoff happened before hello
                outcomes[i, j] = -1  # Invalid region
                continue
                
            # Calculate actual timestamps
            hello_time = reference_timestamp - hello_offset
            signoff_time = reference_timestamp - signoff_offset
            
            # Update persona and determine outcome
            persona.last_hello_time = hello_time
            persona.last_signoff_time = signoff_time
            
            result = muse._determine_intro_type(reference_timestamp, persona)
            
            # Map outcomes to numeric values
            if result == "intro":
                outcomes[i, j] = 1
            elif result == "reintro":
                outcomes[i, j] = 2
            else:
                outcomes[i, j] = 0
    
    # Create the plot
    plt.figure(figsize=(12, 10))
    
    # Create a custom colormap with distinct colors for each region
    colors = ['#FF9999', '#99FF99', '#9999FF', '#FFFF99']  # Red, Green, Blue, Yellow
    cmap = plt.cm.colors.ListedColormap(colors)
    bounds = [-1.5, -0.5, 0.5, 1.5, 2.5]  # Boundaries between colors
    norm = plt.cm.colors.BoundaryNorm(bounds, cmap.N)
    
    im = plt.imshow(outcomes, aspect='equal', origin='lower', cmap=cmap, norm=norm)
    
    # Add colorbar with correct label setting
    cbar = plt.colorbar(im, ticks=[-1, 0, 1, 2])
    cbar.ax.set_yticklabels(['Invalid', 'None', 'Intro', 'Reintro'])
    
    # Add labels
    plt.xlabel('Hours since signoff')
    plt.ylabel('Hours since hello')
    
    # Add title with reference time
    reference_time = datetime.datetime.fromtimestamp(reference_timestamp)
    plt.title(f'Introduction Type Distribution\nReference Time: {reference_time.strftime("%Y-%m-%d %H:%M:%S")}')
    
    # Format axis ticks
    tick_positions = np.linspace(0, len(time_points)-1, 6, dtype=int)
    tick_labels = [f'{time_points[i]/3600:.0f}h' for i in tick_positions]
    plt.xticks(tick_positions, tick_labels)
    plt.yticks(tick_positions, tick_labels)
    
    # Add grid
    plt.grid(True, color='gray', linestyle=':', alpha=0.3)
    
    # Save the plot to a file with hour in the name
    plt.tight_layout()
    output_file = f"intro_type_distribution_{reference_time.strftime('%H')}.png"
    plt.savefig(output_file, dpi=300, bbox_inches='tight')
    plt.close()  # Close the figure to free memory
    print(f"\nVisualization saved to: {output_file}")

def mktime(dt):
    return time.mktime(dt.timetuple())

def generate_hourly_visualizations(muse, base_date, hours=24):
    """Generate visualizations for each hour of the day."""
    print("\nGenerating hourly outcome distribution visualizations...")
    for hour in range(24):
        reference_time = base_date.replace(hour=hour, minute=0, second=0)
        reference_timestamp = mktime(reference_time)
        print(f"\nGenerating visualization for {reference_time.strftime('%Y-%m-%d %H:%M:%S')}")
        visualize_outcomes(muse, reference_timestamp, hours=hours)
        print(f"Completed visualization for hour {hour:02d}")

def main():
    print("\nRunning Introduction Type Tests")
    print("="*80)
    
    # Use a fixed reference time: 2024-03-20 12:00:00
    reference_time = datetime.datetime(2024, 3, 20, 12, 0, 0)
    reference_timestamp = mktime(reference_time)
    
    MuseMemory.load()
    from muse.muse_memory import muse_memory
    muse_memory.get_persona_manager().allow_mock_personas = True
    muse_memory.get_persona_manager().set_current_persona("test_voice")
    muse = get_mock_muse()
    
    # Test Case 1: First-time introduction (no previous interactions)
    persona = create_test_persona()
    test_case(muse, "First-time introduction", persona, "intro", reference_timestamp)
    
    # Test Case 2: Long absence (more than 6 hours since both hello and signoff)
    # Last interaction at 5:00 AM, current time 12:00 PM
    last_interaction = mktime(reference_time.replace(hour=5, minute=0))
    persona = create_test_persona(
        last_hello_time=last_interaction,
        last_signoff_time=last_interaction
    )
    test_case(muse, "Long absence", persona, "intro", reference_timestamp)
    
    # Test Case 3: Recent return (1-6 hours since signoff, more than 6 hours since hello)
    # Last hello at 5:00 AM, last signoff at 9:00 AM, current time 12:00 PM
    persona = create_test_persona(
        last_hello_time=mktime(reference_time.replace(hour=5, minute=0)),
        last_signoff_time=mktime(reference_time.replace(hour=9, minute=0))
    )
    test_case(muse, "Recent return", persona, "reintro", reference_timestamp)
    
    # Test Case 4: Very recent return (less than 1 hour since signoff)
    # Last hello at 5:00 AM, last signoff at 11:30 AM, current time 12:00 PM
    persona = create_test_persona(
        last_hello_time=mktime(reference_time.replace(hour=5, minute=0)),
        last_signoff_time=mktime(reference_time.replace(hour=11, minute=30))
    )
    test_case(muse, "Very recent return", persona, None, reference_timestamp)
    
    # Test Case 5: Sleeping hours case (last signoff at 11 PM, current time 6 AM)
    # Last hello at 5:00 PM, last signoff at 11:00 PM, current time 6:00 AM next day
    last_signoff = mktime(reference_time.replace(hour=23, minute=0))
    current_time = mktime(reference_time.replace(hour=6, minute=0)) + 86400  # Add 24 hours
    persona = create_test_persona(
        last_hello_time=mktime(reference_time.replace(hour=17, minute=0)),
        last_signoff_time=last_signoff
    )
    test_case(muse, "Sleeping hours case", persona, "intro", current_time)
    
    # Test Case 6: Recent hello and signoff (both within 6 hours)
    # Last hello at 9:00 AM, last signoff at 9:00 AM, current time 12:00 PM
    persona = create_test_persona(
        last_hello_time=mktime(reference_time.replace(hour=9, minute=0)),
        last_signoff_time=mktime(reference_time.replace(hour=9, minute=0))
    )
    test_case(muse, "Recent hello and signoff", persona, "reintro", reference_timestamp)
    
    # Test Case 7: Edge case - exactly 6 hours since signoff
    # Last hello at 5:00 AM, last signoff at 6:00 AM, current time 12:00 PM
    persona = create_test_persona(
        last_hello_time=mktime(reference_time.replace(hour=5, minute=0)),
        last_signoff_time=mktime(reference_time.replace(hour=6, minute=0))
    )
    test_case(muse, "Exactly 6 hours since signoff", persona, "reintro", reference_timestamp)
    
    # Test Case 8: Edge case - exactly 1 hour since signoff
    # Last hello at 5:00 AM, last signoff at 11:00 AM, current time 12:00 PM
    persona = create_test_persona(
        last_hello_time=mktime(reference_time.replace(hour=5, minute=0)),
        last_signoff_time=mktime(reference_time.replace(hour=11, minute=0))
    )
    test_case(muse, "Exactly 1 hour since signoff", persona, None, reference_timestamp)
    
    # Generate visualizations for each hour of the day
    base_date = datetime.datetime(2024, 3, 20)  # March 20, 2024
    generate_hourly_visualizations(muse, base_date, hours=24)

if __name__ == "__main__":
    main() 