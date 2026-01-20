"""
QCMD - Quartz Crystal Microbalance with Dissipation monitoring
Main GUI application for controlling QCMD hardware.

Author: Hao JIN
Date: 2026-01-20
"""

import sys
import os
import time
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

        # Set default frequency values
        self.lineEdit.setText("40600000")
        self.lineEdit_2.setText("40700000")
        self.lineEdit_3.setText("1000")
        self.lineEdit_4.setText("")

        # Set window title
        self.setWindowTitle("QCMD Control, v0.1.0-20260120")

        # Initialize serial port
        self.serial_port = None
        self.serial_ports = []

        # Initialize data storage
        self.freq_array = None
        self.data_array = None
        self.t_array = []
        self.fs_array = []
        self.dp_array = []
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

        # Phase plot (middle)
        self.phase_plot = self.multi_plot_widget.addPlot(title='Phase', row=1, col=0)
        self.phase_plot.setLabel('left', 'Phase', units='mV')
        self.phase_plot.showAxis('bottom', False)  # Hide x-axis for middle plot
        self.phase_curve = self.phase_plot.plot(pen='g')

        # Q factor plot (bottom)
        self.q_plot = self.multi_plot_widget.addPlot(title='Q Factor', row=2, col=0)
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
        save_shortcut.activated.connect(self.save_data)

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
                baudrate=2000000,
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

        # Format command as per firmware: "freq_start;freq_stop;freq_step"
        command = f"{freq_start};{freq_stop};{freq_step};\n"

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
        """Read data from serial port and process binary sweep data."""
        if not self.serial_port or not self.serial_port.is_open:
            return

        if not self.sweep_active:
            # If not in sweep mode, just read any text lines
            try:
                if self.serial_port.in_waiting:
                    raw_data = self.serial_port.readline().decode().strip()
                    if raw_data:
                        self.append_output(f"Received: {raw_data}")
            except Exception as e:
                self.append_output(f"Read error: {str(e)}")
            return

        # Sweep active: process binary data
        try:
            bytes_available = self.serial_port.in_waiting
            if bytes_available > 0:
                a_array = self.serial_port.read(bytes_available)

                # Decode start sequence for first packet
                if self.counter == 0:
                    # Check for start sequence 'b,'
                    if a_array[:2] == self.start_sequence:
                        a_array = a_array[2:]
                    array_pairs = zip(a_array[::2], a_array[1::2])
                else:
                    array_pairs = zip(a_array[::2], a_array[1::2])

                stream = [i[0] << 8 | i[1] for i in array_pairs]
                stream_length = len(stream)

                # Append stream to data buffer (interleaved gain/phase pairs)
                # Process pairs: even indices = gain, odd indices = phase
                pairs_to_process = stream_length // 2
                for i in range(pairs_to_process):
                    if self.data_position + i < self.length:
                        # Gain data (even indices)
                        self.gain_data[self.data_position + i] = stream[i*2] / 10.0
                        # Phase data (odd indices)
                        self.phase_data[self.data_position + i] = stream[i*2 + 1] / 10.0

                self.data_position += pairs_to_process
                self.counter += 1

                # Check if sweep is complete (last gain data point non-zero)
                if self.gain_data[-1] != 0:
                    self.sweep_active = False
                    self.append_output("Sweep complete")
                    self.process_sweep_data()

        except Exception as e:
            self.append_output(f"Read error: {str(e)}")

    def process_sweep_data(self):
        """Process completed sweep data and update plots."""
        if self.freq_range is None or self.data is None:
            return

        freq_array = np.array(self.freq_range)
        data_array = np.array(self.data)

        # Update raw spectrum plot
        self.raw_plot_curve.setData(freq_array, data_array)

        # Process resonance frequency and dissipation (from DAQ.py)
        # Fit univariate spline (skip first and last 50 points)
        if len(freq_array) > 100:
            spl = UnivariateSpline(freq_array[50:-50], data_array[50:-50], k=5, s=8*7200)
            fit_freq_range = np.linspace(np.min(freq_array[50:-50]), np.max(freq_array[50:-50]), 100000)
            y_data = spl(fit_freq_range)

            # Time value for plot
            self.t_array.append(time.time() - self.t_start)

            # Find resonance frequency
            f_max = np.argmax(y_data)
            fr = fit_freq_range[f_max]
            self.fs_array.append(fr)

            # Update frequency plot
            self.freq_curve.setData(self.t_array, self.fs_array)

            # Calculate dissipation (static baseline 1750 as in DAQ.py)
            baseline = 1750
            half_max = (max(y_data) - baseline) / 2 + baseline
            idx_nearest = find_idx_nearest_val(y_data[15:f_max], half_max)
            freq_half = fit_freq_range[idx_nearest]
            dissipation = np.abs(freq_half - fr) * 2 / fr
            self.dp_array.append(dissipation)

            # Update dissipation plot (phase plot reused for dissipation)
            self.phase_curve.setData(self.t_array, self.dp_array)

            # Q factor calculation (simplified)
            q_factor = fr / (2 * np.abs(freq_half - fr))
            # Update Q factor plot
            self.q_curve.setData(self.t_array, [q_factor] * len(self.t_array))

        # Optionally save data to CSV
        # self.save_data()

    def save_data(self, filename=None):
        """Save current data to CSV file."""
        if filename is None:
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            filename = f"qcmd_data_{timestamp}.csv"

        try:
            data_to_save = np.column_stack((
                np.round(self.t_array, 2),
                np.round(self.fs_array, 2),
                self.dp_array
            ))
            np.savetxt(filename, data_to_save, delimiter=';',
                       header='time ; fs ; dp')
            self.append_output(f"Data saved to {filename}")
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