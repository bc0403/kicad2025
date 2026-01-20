"""
QCMD - Quartz Crystal Microbalance with Dissipation monitoring
Main GUI application for controlling QCMD hardware.

Author: Hao JIN
Date: 2026-01-20
"""

import sys
import os
import time
import math
import serial
import serial.tools.list_ports
import numpy as np
from scipy.interpolate import UnivariateSpline
from scipy.signal import savgol_filter

# PyQt5 imports
from PyQt5 import QtWidgets, QtCore, QtGui
from PyQt5.QtCore import QTimer, pyqtSignal, pyqtSlot
import pyqtgraph as pg
from gui.ui_main import Ui_MainWindow

# Set antialiasing for better plot quality
pg.setConfigOptions(antialias=True)

# Helper function from DAQ.py
def find_idx_nearest_val(array, value):
    """Find index of nearest value in array."""
    idx_sorted = np.argsort(array)
    sorted_array = np.array(array[idx_sorted])
    idx = np.searchsorted(sorted_array, value, side="left")
    if idx >= len(array):
        idx_nearest = idx_sorted[len(array)-1]
    elif idx == 0:
        idx_nearest = idx_sorted[0]
    else:
        if abs(value - sorted_array[idx-1]) < abs(value - sorted_array[idx]):
            idx_nearest = idx_sorted[idx-1]
        else:
            idx_nearest = idx_sorted[idx]
    return idx_nearest

# UI is loaded via compiled ui_main.py module

class MainWindow(QtWidgets.QMainWindow, Ui_MainWindow):
    """
    Main application window for QCMD control and visualization.
    """

    def __init__(self):
        super().__init__()

        # Setup UI from compiled module
        self.setupUi(self)

        # Ensure window maintains designer size
        self.resize(1024, 768)
        self.setMinimumSize(1024, 768)

        # Set default frequency values (match firmware defaults)
        self.lineEdit.setText("40680000")   # 5 MHz
        self.lineEdit_2.setText("40690000") # 5.5 MHz
        self.lineEdit_3.setText("10")   # 10 kHz step
        self.lineEdit_4.setText("")
        self.lineEdit_5.setText("")  # Resonant frequency display
        self.lineEdit_6.setText("")  # Phase monitoring frequency input

        # Current mode tracking
        self.current_mode = 0  # Default to single sweep
        self.phase_monitoring_freq = None  # Frequency for phase monitoring

        # Set window title
        self.setWindowTitle("QCMD Control, v0.2.0-20260120")

        # Initialize serial port
        self.serial_port = None
        self.serial_ports = []

        # Initialize data storage
        self.freq_array = None
        self.data_array = None
        self.t_array = []
        self.fs_array = []
        self.dp_array = []  # Kept for compatibility
        self.phase_at_res_array = []  # Phase at resonance frequency
        self.q_array = []  # Q factor over time
        self.phase_at_fixed_freq_array = []  # Phase at fixed monitoring frequency
        self.phase_fixed_curve = None  # Placeholder for removed plot curve
        self.phase_fixed_plot = None   # Placeholder for removed plot
        self.t_start = time.time()

        # Sweep state variables (from DAQ.py)
        self.sweep_active = False
        self.data_buffer = []
        self.data_position = 0  # Position in gain/phase data arrays
        self.counter = 0
        self.freq_range = None
        self.gain_data = None   # Gain data (mV)
        self.phase_data = None  # Phase data (mV)
        self.length = 0         # Number of frequency points
        self.start_sequence = b'b,'

        # Timer for periodic serial reading
        self.read_timer = QTimer()
        self.read_timer.timeout.connect(self.read_serial_data)
        self.read_timer.start(10)  # 10 ms interval

        # Setup plots
        self.setup_plots()

        # Connect signals and slots
        self.connect_signals()

        # Initial UI updates
        self.update_serial_list()

    def setup_plots(self):
        """Initialize pyqtgraph plots in the UI layouts."""
        # Raw plot with dual Y axes (verticalLayout)
        self.raw_plot_widget = pg.PlotWidget()
        self.gain_viewbox = self.raw_plot_widget.plotItem.vb
        self.raw_plot_widget.setLabel('left', 'Gain', units='mV')
        self.raw_plot_widget.setLabel('bottom', 'Frequency', units='Hz')
        self.raw_plot_widget.setTitle('Raw Spectrum: Gain (left) and Phase (right)')

        # Create second Y axis on the right for phase
        self.raw_plot_widget.showAxis('right')
        self.raw_plot_widget.setLabel('right', 'Phase', units='mV')
        self.raw_plot_widget.getAxis('right').setPen(pg.mkPen('m', width=1))

        # Create separate viewbox for phase axis
        self.phase_viewbox = pg.ViewBox()
        self.raw_plot_widget.scene().addItem(self.phase_viewbox)
        self.raw_plot_widget.getAxis('right').linkToView(self.phase_viewbox)
        self.phase_viewbox.setXLink(self.raw_plot_widget.plotItem.vb)

        # Create curves for gain and phase
        self.gain_curve = self.raw_plot_widget.plot(pen='c', name='Gain')
        self.phase_curve_right = pg.PlotCurveItem(pen='m', name='Phase')
        self.phase_viewbox.addItem(self.phase_curve_right)

        # Ensure auto-ranging is enabled for both axes
        self.gain_viewbox.enableAutoRange(axis='y')
        self.phase_viewbox.enableAutoRange(axis='y')

        # Update view when resized
        def update_views():
            self.phase_viewbox.setGeometry(self.raw_plot_widget.plotItem.vb.sceneBoundingRect())
            self.phase_viewbox.linkedViewChanged(self.raw_plot_widget.plotItem.vb, self.phase_viewbox.XAxis)

        update_views()
        self.raw_plot_widget.plotItem.vb.sigResized.connect(update_views)

        # Add to verticalLayout (groupBox_4)
        self.verticalLayout.addWidget(self.raw_plot_widget)

        # Multi-plot for freq, phase, and Q (verticalLayout_2)
        self.multi_plot_widget = pg.GraphicsLayoutWidget()

        # Create vertical plots that share x-axis
        # Frequency plot (top)
        self.freq_plot = self.multi_plot_widget.addPlot(title='Resonance Frequency', row=0, col=0)
        self.freq_plot.setLabel('left', 'Frequency', units='Hz')
        self.freq_plot.showAxis('bottom', False)  # Hide x-axis for top plot
        self.freq_curve = self.freq_plot.plot(pen='r')

        # Phase plot (second) - shows phase at fixed monitoring frequency
        self.phase_plot = self.multi_plot_widget.addPlot(title='Phase at Fixed Freq', row=1, col=0)
        self.phase_plot.setLabel('left', 'Phase', units='mV')
        self.phase_plot.showAxis('bottom', False)  # Hide x-axis for second plot
        self.phase_curve = self.phase_plot.plot(pen='y')

        # Q factor plot (third)
        self.q_plot = self.multi_plot_widget.addPlot(title='Q Factor at Resonant Freq', row=2, col=0)
        self.q_plot.setLabel('left', 'Q')
        self.q_plot.setLabel('bottom', 'Time', units='s')
        self.q_curve = self.q_plot.plot(pen='b')

        # Link x-axes so they share the same x-range and zoom/pan together
        self.phase_plot.setXLink(self.freq_plot)
        self.q_plot.setXLink(self.freq_plot)

        # Adjust layout spacing
        self.multi_plot_widget.ci.layout.setSpacing(0)

        # Add to verticalLayout_2 (groupBox_5)
        self.verticalLayout_2.addWidget(self.multi_plot_widget)

    def update_phase_y_range(self, phase_data):
        """Update Y range for phase axis based on phase data.

        Args:
            phase_data: numpy array of phase values in mV
        """
        # Allow auto-ranging (do nothing to interfere with pyqtgraph's auto-range)
        pass

    def update_gain_y_range(self, gain_data):
        """Update Y range for gain axis based on gain data.

        Args:
            gain_data: numpy array of gain values in mV
        """
        # Allow auto-ranging (do nothing to interfere with pyqtgraph's auto-range)
        pass

    def connect_signals(self):
        """Connect UI signals to slots."""
        # Serial port detection
        self.pushButton.clicked.connect(self.update_serial_list)

        # Serial open/close
        self.pushButton_2.clicked.connect(self.open_serial)
        self.pushButton_3.clicked.connect(self.close_serial)

        # Command write
        self.pushButton_4.clicked.connect(self.send_command)

        # Line edit return pressed
        self.lineEdit.returnPressed.connect(self.send_command)
        self.lineEdit_2.returnPressed.connect(self.send_command)
        self.lineEdit_3.returnPressed.connect(self.send_command)
        self.lineEdit_4.returnPressed.connect(self.send_custom_command)

        # Keyboard shortcut for saving data (Ctrl+S)
        save_shortcut = QtWidgets.QShortcut(QtGui.QKeySequence("Ctrl+S"), self)
        save_shortcut.activated.connect(lambda: self.save_data())

        # Additional buttons (clear, set phase point, save)
        self.pushButton_5.clicked.connect(lambda: self.clear_data())  # Clear button (use lambda to avoid boolean parameter)
        self.pushButton_6.clicked.connect(lambda: self.set_phase_monitoring_point())  # Set phase monitoring point (use lambda)
        self.pushButton_7.clicked.connect(lambda: self.save_data())  # Save button (use lambda to avoid boolean parameter)

    def update_serial_list(self):
        """Update list of available serial ports."""
        self.serial_ports = list(serial.tools.list_ports.comports())
        self.comboBox.clear()

        if not self.serial_ports:
            self.comboBox.addItem("No serial ports found")
            self.pushButton_2.setEnabled(False)
            self.label_3.setText("No ports")
            self.label_3.setStyleSheet("color: red;")
        else:
            for port in self.serial_ports:
                self.comboBox.addItem(f"{port.device} - {port.description}")
            self.pushButton_2.setEnabled(True)
            self.label_3.setText(f"{len(self.serial_ports)} ports found")
            self.label_3.setStyleSheet("color: green;")

    def open_serial(self):
        """Open selected serial port."""
        if not self.serial_ports:
            self.append_output("No serial ports available")
            return

        selected_index = self.comboBox.currentIndex()
        if selected_index < 0:
            self.append_output("Please select a serial port")
            return

        port_info = self.serial_ports[selected_index]
        port_name = port_info.device

        try:
            # Open serial port at 2M baud (as per QCMD firmware)
            self.serial_port = serial.Serial(
                port=port_name,
                baudrate=115200,
                timeout=1
            )

            self.append_output(f"Serial port {port_name} opened successfully")
            self.pushButton_2.setEnabled(False)
            self.pushButton_3.setEnabled(True)
            self.comboBox.setEnabled(False)
            self.pushButton.setEnabled(False)

        except Exception as e:
            self.append_output(f"Failed to open {port_name}: {str(e)}")

    def close_serial(self):
        """Close serial port."""
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.append_output("Serial port closed")

        self.serial_port = None
        self.pushButton_2.setEnabled(True)
        self.pushButton_3.setEnabled(False)
        self.comboBox.setEnabled(True)
        self.pushButton.setEnabled(True)

    def send_command(self):
        """Send frequency sweep command to device."""
        if not self.serial_port or not self.serial_port.is_open:
            self.append_output("Serial port not open")
            return

        # Get frequency values from line edits
        try:
            freq_start = int(self.lineEdit.text())
            freq_stop = int(self.lineEdit_2.text())
            freq_step = int(self.lineEdit_3.text())
        except ValueError:
            self.append_output("Invalid frequency values")
            return

        # Determine mode from checkbox: 0=single sweep, 1=continuous sweep
        mode = 0 if self.checkBox.isChecked() else 1
        self.current_mode = mode  # Store current mode for processing

        # Format command as per firmware: "freq_start;freq_stop;freq_step;mode"
        command = f"{freq_start};{freq_stop};{freq_step};{mode};\n"

        try:
            # Flush serial input buffer
            self.serial_port.flushInput()

            # Initialize sweep state
            self.freq_range = range(freq_start, freq_stop + freq_step, freq_step)
            self.length = len(self.freq_range)
            self.gain_data = [0] * self.length   # Gain data array
            self.phase_data = [0] * self.length  # Phase data array
            self.data_buffer = []
            self.data_position = 0  # Position in gain/phase arrays
            self.counter = 0
            self.sweep_active = True

            # Send command
            self.serial_port.write(command.encode())
            self.append_output(f"Sent: {command}")

        except Exception as e:
            self.append_output(f"Send failed: {str(e)}")

    def send_custom_command(self):
        """Send custom command from lineEdit_4."""
        if not self.serial_port or not self.serial_port.is_open:
            self.append_output("Serial port not open")
            return

        command = self.lineEdit_4.text().strip()
        if not command:
            return

        try:
            self.serial_port.write(command.encode())
            self.append_output(f"Sent custom: {command}")
            QTimer.singleShot(100, self.read_serial_data)
        except Exception as e:
            self.append_output(f"Send failed: {str(e)}")

    def read_serial_data(self):
        """Read data from serial port and process ASCII sweep data."""
        if not self.serial_port or not self.serial_port.is_open:
            return

        try:
            while self.serial_port.in_waiting:
                # Read a line from serial port
                raw_line = self.serial_port.readline().decode().strip()
                if not raw_line:
                    continue

                if not self.sweep_active:
                    # Not in sweep mode: display all received lines
                    self.append_output(f"Received: {raw_line}")
                    continue

                # During sweep: check if line contains data (comma-separated values)
                if ',' in raw_line:
                    try:
                        # Parse amplitude,phase values (comma-separated)
                        parts = raw_line.split(',')
                        if len(parts) >= 2:
                            amplitude = float(parts[0].strip())
                            phase = float(parts[1].strip())

                            # Store in data arrays at current position
                            if self.data_position < self.length:
                                self.gain_data[self.data_position] = amplitude
                                self.phase_data[self.data_position] = phase
                                self.data_position += 1

                                # Update raw plot in real-time (first plot only)
                                if self.data_position <= len(self.freq_range):
                                    freq_subset = list(self.freq_range)[:self.data_position]
                                    gain_subset = self.gain_data[:self.data_position]
                                    phase_subset = self.phase_data[:self.data_position]
                                    self.gain_curve.setData(freq_subset, gain_subset)
                                    # Phase curve is on separate Y axis
                                    self.phase_curve_right.setData(freq_subset, phase_subset)

                                # Check if sweep is complete
                                if self.data_position >= self.length:
                                    self.append_output("Sweep complete")
                                    self.process_sweep_data()

                                    # Handle continuous sweep mode
                                    if self.current_mode == 1:  # Continuous sweep
                                        # Reset for next sweep
                                        self.data_position = 0
                                        # Clear raw plot for new sweep
                                        self.gain_curve.setData([], [])
                                        self.phase_curve_right.setData([], [])
                                        self.append_output("Starting next sweep...")
                                    else:
                                        # Single sweep mode - stop receiving sweep data
                                        self.sweep_active = False
                            else:
                                # More data points than expected
                                self.append_output(f"Warning: extra data point: {amplitude},{phase}")
                        else:
                            self.append_output(f"Invalid data format: {raw_line}")
                    except ValueError as e:
                        self.append_output(f"Error parsing data '{raw_line}': {e}")
                else:
                    # Line without comma might be debug message during sweep
                    self.append_output(f"[Debug] {raw_line}")

        except Exception as e:
            self.append_output(f"Read error: {str(e)}")

    def process_sweep_data(self):
        """Process completed sweep data and update plots."""
        if self.freq_range is None or self.gain_data is None or self.phase_data is None:
            return

        freq_array = np.array(list(self.freq_range))
        gain_array = np.array(self.gain_data[:len(freq_array)])
        phase_array = np.array(self.phase_data[:len(freq_array)])

        # Update Y ranges based on current data
        self.update_gain_y_range(gain_array)
        self.update_phase_y_range(phase_array)

        # Update raw spectrum plots (final update)
        self.gain_curve.setData(freq_array, gain_array)
        self.phase_curve_right.setData(freq_array, phase_array)

        # Process resonance frequency from gain data
        # Find frequency with maximum gain (simple peak detection)
        if len(gain_array) > 10:
            # Simple peak detection: find index of maximum gain
            peak_idx = np.argmax(gain_array)
            fr = freq_array[peak_idx]  # Resonance frequency
            phase_at_resonance = phase_array[peak_idx]  # Phase at resonance

            # Update resonant frequency display for single sweep mode
            if self.current_mode == 0:  # Single sweep mode
                self.lineEdit_5.setText(f"{fr}")
                self.freq_phase = fr

            # Time value for plot
            current_time = time.time() - self.t_start
            self.t_array.append(current_time)
            self.fs_array.append(fr)

            # Store phase value at resonance
            if not hasattr(self, 'phase_at_res_array'):
                self.phase_at_res_array = []
            self.phase_at_res_array.append(phase_at_resonance)

            # Q factor estimation using formula: Q = -0.5 * fr * d_phase / df
            # where fr is resonance frequency, d_phase is phase difference in radians,
            # and df is frequency difference between two measurement points

            # Calculate frequency difference and phase difference
            df = freq_array[peak_idx + 1] - freq_array[peak_idx - 1]
            d_phase_mV = phase_array[peak_idx + 1] - phase_array[peak_idx - 1]

            # Convert phase difference from mV to radians
            # 10 mV = 1 degree, 180 degrees = π radians
            # So: phase_rad = (phase_mV / 10) * (π / 180)
            d_phase_rad = (d_phase_mV / 10.0) * (math.pi / 180.0)

            # Calculate Q factor using formula Q = -0.5 * fr * d_phase / df
            if abs(df) > 1e-6:  # Avoid division by zero
                q_factor = -0.5 * fr * d_phase_rad / df
                # Ensure Q is positive (take absolute value if needed)
                if q_factor < 0:
                    q_factor = abs(q_factor)
            else:
                q_factor = 0
                self.append_output(f"Warning: df too small ({df:.1f} Hz) for Q calculation")

            # Store Q factor
            self.q_array.append(q_factor)

            # # Log details about Q calculation
            # self.append_output(f"Q calculation: at {fr:.0f} Hz")
            # self.append_output(f"  df = {df:.1f} Hz, d_phase = {d_phase_mV:.2f} mV = {d_phase_rad:.4f} rad")
    

            # Store phase at fixed monitoring frequency (if phase monitoring point is set)
            # Determine target frequency for phase comparison
            # always calculate Q factor at series resonant frequency
            # if self.phase_monitoring_freq is not None:
            #     target_freq = self.phase_monitoring_freq
            #     freq_source = "user-set phase monitoring point"
            # else:
            #     # Default: use frequency 1000 Hz above resonance
            #     target_freq = fr + int(self.lineEdit_3.text())
            #     freq_source = f"default offset (+{int(self.lineEdit_3.text())} Hz)"
            
            

            if self.phase_monitoring_freq is not None:
                target_idx = find_idx_nearest_val(freq_array, self.phase_monitoring_freq)
                phase_at_target = phase_array[target_idx]
                self.phase_at_fixed_freq_array.append(phase_at_target)
                self.append_output(f"Phase at fixed freq {self.phase_monitoring_freq:.0f} Hz: {phase_at_target:.1f} mV")
                # Log results with phase info
                self.append_output(f"Resonance: {fr/1e6:.3f} MHz, Phase at {self.phase_monitoring_freq:.0f} Hz: {phase_at_target:.1f} mV, Q: {q_factor:.0f}")
            else:
                # No fixed monitoring frequency set, store NaN as placeholder
                self.phase_at_fixed_freq_array.append(float('nan'))
                # Log results without phase info
                self.append_output(f"Resonance: {fr/1e6:.3f} MHz, Q: {q_factor:.0f}")


            # Update multi-plot
            self.freq_curve.setData(self.t_array, self.fs_array)
            self.phase_curve.setData(self.t_array, self.phase_at_fixed_freq_array)
            self.q_curve.setData(self.t_array, self.q_array)

        # Optionally save data to CSV
        # self.save_data()

    def save_data(self, filename=None):
        """Save current data to CSV file."""
        # Handle case where a boolean might be passed from button click
        if filename is None or not isinstance(filename, str):
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"qcmd_data_{timestamp}.csv"
        # Ensure filename is string (in case bytes or PathLike object)
        filename = str(filename)

        try:
            # Ensure all arrays have same length (include q_array and phase_at_fixed_freq_array)
            min_len = min(len(self.t_array), len(self.fs_array),
                         len(self.phase_at_res_array), len(self.q_array),
                         len(self.phase_at_fixed_freq_array))
            if min_len == 0:
                self.append_output("No data to save")
                return

            # Create data folder if it doesn't exist
            data_folder = "data"
            if not os.path.exists(data_folder):
                os.makedirs(data_folder)
                self.append_output(f"Created data folder: {data_folder}")

            # Construct full file path
            filepath = os.path.join(data_folder, filename)

            # Prepare data with four columns: time, freq, phase_at_fixed, Q
            data_to_save = np.column_stack((
                np.round(self.t_array[:min_len], 2),
                np.round(self.fs_array[:min_len], 0),
                np.round(self.phase_at_fixed_freq_array[:min_len], 2),
                np.round(self.q_array[:min_len], 0)
            ))

            # Save to CSV with semicolon delimiter
            np.savetxt(filepath, data_to_save, delimiter=';',
                       header='time ; freq ; phase_at_fixed_freq ; Q')
            self.append_output(f"Data saved to {filepath}")

        except Exception as e:
            self.append_output(f"Save error: {str(e)}")

    def center_window(self):
        """Center the window on the screen."""
        frame_geometry = self.frameGeometry()
        center_point = QtWidgets.QApplication.desktop().availableGeometry().center()
        frame_geometry.moveCenter(center_point)
        self.move(frame_geometry.topLeft())

    def append_output(self, message):
        """Append message to text browser with timestamp."""
        timestamp = time.strftime("%H:%M:%S")
        self.textBrowser.append(f"[{timestamp}] {message}")
        # Auto-scroll to bottom
        self.textBrowser.verticalScrollBar().setValue(
            self.textBrowser.verticalScrollBar().maximum()
        )

    def clear_data(self):
        """Clear all data arrays and plots."""
        # Clear data arrays
        self.t_array = []
        self.fs_array = []
        self.phase_at_res_array = []
        self.q_array = []
        self.phase_at_fixed_freq_array = []

        # Reset time baseline for new data
        self.t_start = time.time()

        # Clear raw plot data
        self.gain_curve.setData([], [])
        self.phase_curve_right.setData([], [])

        # Clear multi-plot data
        self.freq_curve.setData([], [])
        self.phase_curve.setData([], [])
        self.q_curve.setData([], [])

        # Clear resonant frequency display
        self.lineEdit_5.setText("")

        # Reset sweep state based on current mode
        if self.sweep_active and self.current_mode == 1:
            # Continuous sweep mode - keep sweep active, don't reset data_position
            # to avoid disrupting current sweep
            pass
        else:
            # Single sweep mode or no active sweep - stop sweep and reset
            self.sweep_active = False
            self.data_position = 0

        # Log action
        self.append_output("All data and plots cleared")

    def set_phase_monitoring_point(self):
        """Set phase monitoring point frequency.

        If lineEdit_5 (resonant frequency) has text, copy it to lineEdit_6.
        Then read frequency from lineEdit_6 and set as phase monitoring point.
        """
        # First, check if lineEdit_5 has resonant frequency text
        resonant_freq_text = self.lineEdit_5.text().strip()
        if resonant_freq_text:
            # Copy resonant frequency to lineEdit_6
            self.lineEdit_6.setText(resonant_freq_text)
            self.append_output(f"Copied resonant frequency {resonant_freq_text} Hz to monitoring field")

        try:
            freq_text = self.lineEdit_6.text().strip()
            if not freq_text:
                self.append_output("Please enter a frequency in lineEdit_6 or detect resonance first")
                return

            freq = float(freq_text)
            # Store the frequency for phase monitoring
            self.phase_monitoring_freq = freq
            self.append_output(f"Phase monitoring point set to {freq:.0f} Hz")

        except ValueError:
            self.append_output(f"Invalid frequency value: {self.lineEdit_6.text()}")

    def closeEvent(self, event):
        """Handle window close event."""
        self.close_serial()
        event.accept()

def main():
    """Main application entry point."""
    # Enable high DPI scaling for Windows
    if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    if hasattr(QtCore.Qt, 'AA_UseHighDpiPixmaps'):
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps, True)

    app = QtWidgets.QApplication(sys.argv)

    # Set application style (optional)
    app.setStyle('Fusion')

    window = MainWindow()
    window.show()
    window.center_window()

    sys.exit(app.exec_())

if __name__ == "__main__":
    main()