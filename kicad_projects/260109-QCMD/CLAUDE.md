# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Quartz Crystal Microbalance with Dissipation monitoring (QCMD)** measurement system that combines:
- **Hardware**: Custom PCB design using KiCad 9.0
- **Firmware**: Teensy 4.0/3.6 embedded controller (Arduino-compatible)
- **Software**: Python-based data acquisition and visualization GUI

**Primary Application**: Measuring mass changes and viscoelastic properties at surfaces using frequency sweep measurements in the ~5MHz range.

## Architecture

### Hardware Layer (KiCad)
- **Main Schematic**: `260109-QCMD.kicad_sch` (1.6MB, multi-sheet design)
- **PCB Layout**: `260109-QCMD.kicad_pcb`
- **Key Components**:
  - AD9851: Direct Digital Synthesizer for frequency generation
  - AD5252: Digital potentiometer (I2C address 0x2C)
  - AD8007/AD8310: Buffer and logarithmic amplifiers
  - LM2735: DC-DC converter
  - MIC5219: 500mA LDO regulator
  - Crystal oscillators (ASE30M, MC2016K30.0000C16ESH)

### Firmware Layer (Teensy/Arduino)
- **File**: `firmware/firmware.ino`
- **Target**: Teensy 4.0 (pin A7, A8, A6 for AD9851) or Teensy 3.6
- **Key Libraries**: `Wire.h` (I2C), `ADC.h` (Teensy ADC library)
- **Communication**: Serial at 2M baud with Python software
- **Command Format**: `freq_start;freq_stop;freq_step` (e.g., `5000000;5500000;100`)

### Software Layer (Python)
- **Legacy DAQ**: `software/DAQ.py` (original PyQtGraph application)
- **New GUI**: `qcmd.py` (PyQt5-based GUI with integrated plots)
- **Framework**: PyQt5, PyQtGraph for real-time visualization
- **Key Dependencies**: NumPy, SciPy, pandas, PyQt5, PyQtGraph, pyserial
- **Visualization**: Real-time plots in GUI:
  1. Raw Spectrum (Magnitude vs Frequency)
  2. Resonance Frequency vs Time
  3. Dissipation vs Time
  4. Q Factor vs Time

## Common Development Commands

### Hardware Development (KiCad)
```bash
# Open the KiCad project (requires KiCad 9.0+ installed)
kicad 260109-QCMD.kicad_pro

# Generate BOM from schematic
eeschema --bom 260109-QCMD.kicad_sch

# Run ERC (Electrical Rules Check)
eeschema --erc 260109-QCMD.kicad_sch

# Run DRC (Design Rules Check) on PCB
pcbnew --drc 260109-QCMD.kicad_pcb

# Export Gerber files for manufacturing
pcbnew --plot 260109-QCMD.kicad_pcb
```

### Firmware Development
```bash
# Compile and upload to Teensy (using Arduino IDE or PlatformIO)
# Requires Teensyduino addon installed in Arduino IDE

# Common serial monitor commands for testing:
# Send frequency sweep command:
echo "5000000;5500000;100" > COM4  # Windows
echo "5000000;5500000;100" > /dev/ttyACM0  # Linux

# Set serial baud rate to 2000000 for communication
```

### Software Development
```bash
# Install Python dependencies (no requirements.txt exists, install manually):
pip install numpy scipy pandas pyqtgraph pyserial matplotlib PyQt5

# Run the legacy data acquisition software:
cd software
python DAQ.py

# Run the new PyQt5 GUI:
cd software
python qcmd.py

# The software expects serial communication on COM4 at 2M baud
# The GUI automatically detects available serial ports
# Default frequency range: 5 MHz to 5.5 MHz with 100 Hz steps
```

## Key Files Reference

### Hardware Design
- `260109-QCMD.kicad_sch` - Main schematic (multi-sheet)
- `main.kicad_sch` - Core circuit schematic
- `interface.kicad_sch` - Interface circuitry
- `260109-QCMD.kicad_pcb` - PCB layout
- `libs/` - Custom KiCad libraries (symbols, footprints, 3D models)
- `datasheet/` - Organized component datasheets by subsystem

### Firmware
- `firmware/firmware.ino` - Complete Teensy firmware
- **Key Constants**: `REFCLK = 180000000`, `ADDRESS = 0x2C`, `POT_VALUE = 254`
- **ADC Settings**: 12-bit resolution, 2048 samples averaging

### Software
- `software/DAQ.py` - Legacy data acquisition and visualization
- `qcmd.py` - New PyQt5 GUI for QCMD control and visualization
- `software/gui/ui_main.ui` - Qt Designer UI file
- **Data Processing**: Uses SciPy's `UnivariateSpline` and `savgol_filter`
- **Data Output**: Saves to CSV files with timestamp (Ctrl+S in GUI)
- **GUI Features**: Serial port detection, frequency sweep control, real-time plots

### Documentation & Calculations
- `mathcad/LM2735.xmcd` - Mathcad design calculations for DC-DC converter
- `libs/assets/block_diagram.png` - System block diagram

## Development Workflow

### Typical Measurement Session
1. **Hardware**: Power up QCMD PCB with Teensy connected
2. **Firmware**: Upload firmware to Teensy (sets up AD9851, ADC, I2C)
3. **Software**: Run `python qcmd.py` from the software directory (or `python DAQ.py` for legacy)
4. **Control**: Select serial port, set frequency range, send sweep command
5. **Data**: Real-time plots update, data saved to CSV (Ctrl+S)

### Modifying Frequency Range
1. Update firmware constants for new frequency bounds
2. Recompile and upload to Teensy
3. Adjust Python software plotting ranges if needed

### Adding New Measurements
1. Extend firmware to read additional ADC channels
2. Modify Python data processing pipeline
3. Add new plot panels to PyQtGraph GUI

## Environment Setup Notes

### Hardware
- KiCad 9.0+ required for schematic/PCB editing
- Component libraries are in `libs/` (symbols, footprints, 3D models)
- Datasheets organized by subsystem in `datasheet/`

### Firmware
- Arduino IDE with Teensyduino addon
- Teensy 4.0 or 3.6 target
- Key libraries: `ADC.h` (Teensy specific), `Wire.h`

### Software
- Python 3 with scientific stack
- Serial port access permissions (COM4 on Windows, /dev/ttyACM0 on Linux)
- PyQtGraph for real-time visualization

## Project State
- Hardware design appears complete with professional-grade components
- Firmware and software are functional but untracked in git
- No traditional build systems or package management files
- Comprehensive datasheet collection available for all components
- Mathcad calculations document design decisions