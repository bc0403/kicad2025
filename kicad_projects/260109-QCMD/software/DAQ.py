# -*- coding: utf-8 -*-
"""
Created on Thu Mar 25 11:49:26 2021

@author: Rens
"""

# Loading libraries
from pyqtgraph.Qt import QtGui, QtCore, QtWidgets
import numpy as np
import pyqtgraph as pg
import sys
import time
import matplotlib.pyplot as plt
import pandas as pd
import serial
import csv
from scipy.interpolate import UnivariateSpline
from scipy.signal import savgol_filter
import pickle


total_points = []
class RealtimePlot():
    def __init__(self):
        #Initiate Gui Window
        self.traces = dict()
        self.app = QtWidgets.QApplication(sys.argv)
        self.win = pg.GraphicsLayoutWidget(show=True, title="Signal from serial port")
        self.win.resize(900,700)
        self.win.setWindowTitle('Real time plot')
        
        #Enable anti-aliasing
        pg.setConfigOptions(antialias=True)
        #Add plots to Gui Window
        self.fs = self.win.addPlot(title='Frequency Response', row=1, col=1)
        self.dp = self.win.addPlot(title='Dissipation', row=2, col=1)
        self.spectrum = self.win.addPlot(title='Spectrum', row=3, col=1)
        
        #Define necessary variables
        self.dp_array = []
        self.fs_array = []
        self.t_array = []
        self.data_array = [0]*length
        self.t_start = time.time()
        self.test_array = [0]*50000
    def start(self):
        #Important line of code for Gui Window
        if (sys.flags.interactive != 1) or not hasattr(QtCore,'PYQT_VERSION'):
            QtWidgets.QApplication.instance().exec()
    
    def update_plot(self,name,x_data,y_data):
        if name in self.traces:
            self.traces[name].setData(x_data,y_data)
            QtWidgets.QApplication.processEvents()
        else:
            if name == 'fs':
                self.traces[name] = self.fs.plot(pen='c', width = 3)
                self.fs.setLabel('left', 'Resonance Frequency (Hz)')
                self.fs.setLabel('bottom', 'Time (s)')
            if name == 'spectrum':
                self.traces[name] = self.spectrum.plot(pen='m', width = 3)
                self.spectrum.setLabel('left', 'Magnitude (dB)')
                self.spectrum.setLabel('bottom', 'Frequency (Hz)')
            if name == 'dp':
                self.traces[name] = self.dp.plot(pen='r', width = 3)
                self.dp.setLabel('left', 'a.u.')
                self.dp.setLabel('bottom', 'Time (s)')
        
    def update_data(self,freq_range,data):
        # Plot Admittance Spectrum
        self.data_array = data
        self.freq_array = freq_range
        self.update_plot(name='spectrum', x_data = self.freq_array, y_data = self.data_array)
        
        # Plot resonance frequency as function of time
        # Fit of univariate spline (first and last 50 points are chopped because of poor stability)
        self.spl = UnivariateSpline(freq_range[50:-50],data[50:-50],k=5,s=8*7200)
        # Define array to put into fit results
        self.fit_freq_range = np.linspace(np.min(freq_range[50:-50]),np.max(freq_range[50:-50]),100000)
        self.y_data = self.spl(self.fit_freq_range)
        # Time value for plot
        self.t_array.append(time.time()-self.t_start)
        # Find resonance frequency
        self.f_max = np.argmax(self.y_data)
        self.fr = self.fit_freq_range[self.f_max]
        # Add to fs array for plotting
        self.fs_array.append(self.fr)
        # Send plot command
        self.update_plot(name='fs', x_data = self.t_array, y_data = self.fs_array)
        
        # Plot of dissipation (static)
        # Static dissipation baseline determined for fundamental frequency
        self.baseline = 1750
        # Define FWHM
        self.half_max = (max(self.y_data)-self.baseline)/2+self.baseline        
        # Find the index of the nearest value to it
        self.test3 = find_idx_nearest_val(self.y_data[15:self.f_max],self.half_max)
        # Find the corresponding frequency
        self.test2 = self.fit_freq_range[self.test3]
        # Calculate and append dissipation
        self.dp_array.append(np.abs(self.test2-self.fr)*2/self.fr)
        # Send plot command
        self.update_plot(name='dp', x_data = self.t_array, y_data = self.dp_array)
    
    # Saving the data to a file
    def save_data(self,file_name):
        self.save_t = np.array(self.t_array)
        self.save_fs = np.array(self.fs_array)
        self.save_dp = np.array(self.dp_array)
        np.savetxt(file_name, np.transpose([np.round(self.t_array,2), np.round(self.fs_array,2),
                                            self.dp_array]), delimiter=';', header='time ; fs ; dp')
        
    # Closing everything in the Python kernel that is running.
    def close_all(self):
        ser.close()
        self.spectrum.close()
        self.fs.close()
        self.win.close()
        self.app.quit()

# Function to find the index of the closest value
def find_idx_nearest_val(array, value):
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

# Static function to measure in certain frequency domain. 
# (Next version should include fs and dp tracking.)
if __name__ == '__main__':   
    input_freq_start = '4996000'  #input('Enter starting frequency: ')
    input_freq_stop  = '5006000'  #input('Enter stopping frequency: ')
    input_freq_step  = '10'       #input('Enter frequency stepsize: ')
    # Initialize serial communication
    ser = serial.Serial("COM4",2000000)
    # Flush the serial buffer/cache
    ser.flushInput()
    # Write the sweep command to the EQCM-I
    ser.write((input_freq_start+';'+input_freq_stop+';'+input_freq_step+'\n').encode())
    # Define the frequency range of the measurement and initialize other important variables
    freq_range = range(int(input_freq_start),int(input_freq_stop)+int(input_freq_step),int(input_freq_step))
    length = len(freq_range)
    data = [0]*length
    c=int(0)
    data_position = 0
    # Sweep flag
    Sweep = True
    t0=time.process_time()
    res_freq = []
    
    # Create instance of the RealtimePlot class.
    p = RealtimePlot()
    # Keep sweeping unless interrupted
    try:
        while True:
            if Sweep == False:
                # Write new sweep command and reset all variables.
                ser.write((input_freq_start+';'+input_freq_stop+';'+input_freq_step+'\n').encode())
                Sweep = True
                data[-1] = 0
                c = 0
                data_position = 0
            while Sweep == True:
                # Read the available data from EQCM-I and process them to be read
                bytes_available = ser.in_waiting
                if bytes_available>0:
                    a_array = ser.read(bytes_available)    
                    start_sequence = b'b,'
                    # Decode anything other than start sequence
                    if c>0:
                        array_pairs = zip(a_array[::2], a_array[1::2]) # (sample1, 2), (sample 3, 4)
                        data_position += stream_length
                    # Decode start sequence
                    elif c==0:
                        array_pairs = zip(a_array[len(start_sequence)::2], a_array[len(start_sequence)+1::2]) # (sample1, 2), (sample 3, 4)
                    stream = [i[0] << 8 | i[1] for i in array_pairs]
                    stream_length = len(stream)
                    # Append all data stored in stream to data
                    for i in range(stream_length): 
                        data[i+data_position]=stream[i]/10
                    c+=1
                    # As soon as the final 0 is changed for data the sweep must be complete.
                    if data[-1]!=0:
                        Sweep = False
                        # Send the data to the plot window.
                        p.update_data(freq_range,data)
                        
    # If interrupted save the data and close all operations.                    
    except KeyboardInterrupt:
        p.save_data('test_file.txt')
        p.close_all()
        ser.close()
        print('Interrupted')
