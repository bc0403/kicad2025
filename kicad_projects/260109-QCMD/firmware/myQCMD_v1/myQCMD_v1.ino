/***********************************************************************************************

   LICENSE
   Copyright (C) 2018 openQCM
   This program is free software: you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation, either version 3 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.
   You should have received a copy of the GNU General Public License
   along with this program.  If not, see http://www.gnu.org/licenses/gpl-3.0.txt
  --------------------------------------------------------------------------------
   OPENQCM Q-1 - Quartz Crystal Microbalance with dissipation monitoring
   openQCM is the unique opensource quartz crystal microbalance http://openqcm.com/
   
   ELECTRONICS
     - board and firmware designed for teensy 4.0 development board
       https://www.pjrc.com/store/teensy40.html
     - DDS/DAC Synthesizer AD9851
     - phase comparator AD8302
     - I2C digital potentiometer AD5251+
     - MCP9808 temperature sensor

   version  ver 2.1 T40
   tag      // V2.1_T40
   date     September 2021
   author   openQCM team
   --------------------------------------------------------------------------------

   CHANGES ver 2.1 T40
   - Using ADC library by pedvide 
     https://pedvide.github.io/ADC/
     https://github.com/pedvide/ADC

   
   - changed pot value for compatibility with openQCM Q-1 shield @5VDC   
   - changed ADC delay microseconds > 100 us
   - changed ADC avaeraging sample  > 32 sample
   - changed the type of phase and mag to double
   - changed included library for MCP9808 temperature sensor in skecth directory v1.0

   TODO
   - I2C replace standard i2c library with Teensy i2c custom library i2c_t3.h
   Brian (nox771) New I2C library for Teensy3
   https://github.com/nox771/i2c_t3
   - ADC libraries https://github.com/pedvide/ADC

   CREDIT:
   - based on the work made by Brett Killion on Hackaday
     https://hackaday.io/project/10021-arduino-network-analyzer
   - Teensy 4.0 is  developed by Paul Stoffregen working at PJRC
     https://www.pjrc.com/store/teensy40.html
   - MCP9808 I2c temperature sensor dirver is developed by Adafruit 
   Written by Kevin Townsend/Limor Fried for Adafruit Industries.

 ***********************************************************************************************/

/************************** LIBRARIES **************************/
#include<Wire.h>
// libraries included in /src folder
// # include "src/Adafruit_MCP9808.h"
// V2.1_T40 using ADC library by pedvide 
# include "src/ADC/ADC.h"
# include "src/ADC/ADC_util.h"

/*************************** DEFINE ***************************/
// // potentiometer AD5252 I2C address is 0x2C(44)
// #define ADDRESS 0x2C
// // potentiometer AD5252 default value for compatibility with openQCM Q-1 shield @5VDC 
// #define POT_VALUE 240 //254
// reference clock for AD9851
#define REFCLK 180000000
// safe default frequency for dummy mode (1 MHz)
#define SAFE_FREQ 1000000

// V2.1_T40 ADC averaging and resolution define 
#define AVERAGING   1  // hardware average#
#define RESOLUTION 12

/*************************** VARIABLE DECLARATION ***************************/

// current input frequency
long freq = 0;

// V2.1_T40 DDS Synthesizer AD9851 pin function
int WCLK = A7; //3;
int DATA = A8;  //4;
int FQ_UD = A6;  //2;

// frequency tuning word
long FTW;
float temp_FTW; // temporary variable

/* 
 *  TODO DELETE OLD 
// phase comparator AD8302 pinout
int AD8302_PHASE = 20;
int AD8302_MAG = 37;
//int AD83202_REF = 17;
int AD83202_REF = 34;
*/

// V2.1_T40 T40 pin ADC synchronized pins
const int readPin = A0;  //A9;
const int readPin2 = A1;  //A3;
// init  adc object
ADC *adc = new ADC();
// number of sample for averaging, software average
// 1/600MHz = 1.67 ns; 1.67*2048 = 3.4 us per point;
int AVERAGE_SAMPLE = 2048;
// ADC init variabl
boolean WAIT = true;
// ADC waiting delay microseconds
int WAIT_DELAY_US = 100;
// // ADC averaging
// boolean AVERAGING_BOOL = true;

// // TODO
// double val = 0;

// // Create the MCP9808 temperature sensor object
// Adafruit_MCP9808 tempsensor = Adafruit_MCP9808();
// // init temperature variable
// float temperature = 0;

// // V2.1_T40 LED pin
// int ledPin1 = 6;
// int ledPin2 = 7;

/*
 * TODO DELETE OLD 
// inint number of averaging
int AVERAGE_SAMPLE = 32;
// teensy ADC averaging init
int ADC_RESOLUTION = 13;
*/

// init sweep param
long freq_start = 40680000;
long freq_stop = 40690000;
long freq_step = 1000;

// // init output ad8302 measurement (cast to double)
// double measure_phase = 0;
// double measure_mag = 0;


/*************************** FUNCTION ***************************/

// AD9851 set frequency fucntion
void SetFreq(long frequency)
{
// Transform input frequency to tuning word using 180 MHz internal clock
  // temp_FTW = (frequency * pow(2, 32)) / REFCLK;
  temp_FTW = (double)frequency * 4294967296.0 / REFCLK;  // 2^32 = 4294967296
  FTW = long (temp_FTW);

  long pointer = 1;
  int pointer2 = 0b10000000;

// 32 bit DDS tuning word frequency instructions
  for (int i = 0; i < 32; i++)
  {
    if ((FTW & pointer) > 0) digitalWrite(DATA, HIGH);
    else digitalWrite(DATA, LOW);
    digitalWrite(WCLK, HIGH);
    digitalWrite(WCLK, LOW);
    pointer = pointer << 1;
  }
// 8 bit DDS phase and x6 multiplier refclock
  for (int i = 0; i < 8; i++)
  {
    if (i==0) digitalWrite(DATA, HIGH);  // enable 6x reference clk
    else digitalWrite(DATA, LOW);
    digitalWrite(WCLK, HIGH);
    digitalWrite(WCLK, LOW);
    pointer2 = pointer2 >> 1;
  }
  // Tuning word and phase commands sent.
  digitalWrite(FQ_UD, HIGH);
  digitalWrite(FQ_UD, LOW);
}


/*************************** SETUP ***************************/
void setup()
{
  // // Initialise I2C communication as Master
  // Wire.begin();
  // Initialise serial communication, set baud rate = 9600
  Serial.begin(115200);

  // // set potentiometer value
  // // Start I2C transmission
  // Wire.beginTransmission(ADDRESS);
  // // Send instruction for POT channel-0
  // Wire.write(0x01);
  // // Input resistance value, 0x80(128)
  // Wire.write(POT_VALUE);
  // // Stop I2C transmission
  // Wire.endTransmission();

  // AD9851 set pin mode
  pinMode(WCLK, OUTPUT);
  pinMode(DATA, OUTPUT);
  pinMode(FQ_UD, OUTPUT);

  // AD9851 enter serial mode
  digitalWrite(WCLK, HIGH);
  digitalWrite(WCLK, LOW);
  digitalWrite(FQ_UD, HIGH);
  digitalWrite(FQ_UD, LOW);

  /*
   * TODO DELETE OLD 
  // AD8302 set pin mode
  pinMode(AD8302_PHASE, INPUT);
  pinMode(AD8302_MAG, INPUT);
  pinMode(AD83202_REF, INPUT);
  */ 

  // V2.1_T40 T40 ADC SETTING
  pinMode(readPin, INPUT);
  pinMode(readPin2, INPUT);

  // ADC0
  adc->setAveraging(AVERAGING); // set number of averages
  adc->setResolution(RESOLUTION); // set bits of resolution
  // it can be any of the ADC_CONVERSION_SPEED enum: VERY_LOW_SPEED, LOW_SPEED, MED_SPEED, HIGH_SPEED_16BITS, HIGH_SPEED or VERY_HIGH_SPEED
  // see the documentation for more information
  // additionally the conversion speed can also be ADACK_2_4, ADACK_4_0, ADACK_5_2 and ADACK_6_2,
  // where the numbers are the frequency of the ADC clock in MHz and are independent on the bus speed.
  adc->setConversionSpeed(ADC_CONVERSION_SPEED::HIGH_SPEED); // VER 0.1.4 change the conversion speed to HIGH_SPEED 
  // it can be any of the ADC_MED_SPEED enum: VERY_LOW_SPEED, LOW_SPEED, MED_SPEED, HIGH_SPEED or VERY_HIGH_SPEED
  adc->setSamplingSpeed(ADC_SAMPLING_SPEED::HIGH_SPEED); // VER 0.1.4 change the conversion speed to HIGH_SPEED 

  // ADC1
  adc->setAveraging(AVERAGING, ADC_1); // set number of averages
  adc->setResolution(RESOLUTION, ADC_1); // set bits of resolution
  adc->setConversionSpeed(ADC_CONVERSION_SPEED::HIGH_SPEED, ADC_1); // change the conversion speed to HIGH_SPEED 
  adc->setSamplingSpeed(ADC_SAMPLING_SPEED::HIGH_SPEED, ADC_1); // change the sampling speed to HIGH_SPEED 

  adc->startSynchronizedContinuous(readPin, readPin2);

  /*
   * TODO DELETE OLD 
  // Teensy 3.6 set  adc resolution
  analogReadResolution(ADC_RESOLUTION);
  */

  // // begin temperature sensor
  // tempsensor.begin();

  // // turn on the light
  // pinMode(ledPin1, OUTPUT);
  // pinMode(ledPin2, OUTPUT);
  // digitalWrite(ledPin1, HIGH);
  // digitalWrite(ledPin2, HIGH);
}

int mode = 3;  // 0-single sweep; 1-continous sweep; 2-cw output at start freq; 3-dummy
boolean debug = false;
int prevMode = -1;
// long pre_time = 0;
// long last_time = 0;

int byteAtPort = 0;

char buf[64];
char tempChars[64];

// V2-1_T40 T40 init ADC
double value = 0;
double value2 = 0;
// long time_start = 0;
ADC::Sync_result result;

// Perform a single frequency sweep
// Returns true if sweep completed, false if interrupted by new command
bool performSweep(bool checkForCommand) {
  // Safety check: ensure valid frequency step
  if (freq_step <= 0) {
    digitalWrite(13, HIGH); // LED on
    return true; // Treat as completed
  }

  if (debug) {
    Serial.print("performSweep: check=");
    Serial.print(checkForCommand);
    Serial.print(" start=");
    Serial.print(freq_start);
    Serial.print(" stop=");
    Serial.print(freq_stop);
    Serial.print(" step=");
    Serial.println(freq_step);
  }

  digitalWrite(13, LOW); // LED indicator of sweep
  long count = 0;

  for (count = freq_start; count <= freq_stop; count = count + freq_step) {
    // Check for new command if requested
    if (checkForCommand && Serial.available() > 0) {
      if (debug) Serial.println("Sweep interrupted by command");
      return false; // Sweep interrupted
    }

    if (debug && (count - freq_start) % 100000 == 0) {
      Serial.print("Sweep at freq: ");
      Serial.println(count);
    }

    SetFreq(count);
    if (WAIT) delayMicroseconds(WAIT_DELAY_US);  // 100us*20001 = 2s per sweep

    // ADC measure and averaging
    if (AVERAGING == true) {
      // V2.1_T40 ADC acquisition, averaging and sending data
      for (int i = 0; i < AVERAGE_SAMPLE; i++) {
        result = adc->readSynchronizedContinuous();
        value += (uint16_t)result.result_adc0;
        value2 += (uint16_t)result.result_adc1;
      }
      // averaging (cast to double)
      value2 = 1.0 * value2 / AVERAGE_SAMPLE;
      value = 1.0 * value / AVERAGE_SAMPLE;

      // serial print data bit-amplitude and bit-phase values
      Serial.print(value*3300.0/((1<<RESOLUTION)-1));
      Serial.print(",");
      Serial.print(value2*3300.0/((1<<RESOLUTION)-1));
      Serial.println();

      value = 0.0;
      value2 = 0.0;
    }
  }

  digitalWrite(13, HIGH); // LED indicator of sweep
  delay(500);
  if (debug) Serial.println("Sweep completed successfully");
  return true; // Sweep completed
}

/*************************** LOOP ***************************/
void loop()
{
  if ( (byteAtPort = Serial.available()) > 0) {
    // read message at serial port
    String message_str = Serial.readStringUntil('\n');  // the command should terminated by \n, for example `5000000;6000000;1000;\n`
    //This is required because strtok() works on C strings, not Arduino String
    // char buf[byteAtPort];
    message_str.toCharArray(buf, sizeof(buf));

    // char *p = buf;
    // char *str;
    // int nn = 0;
    // // decode message 
    // while ((str = strtok_r(p, ";", &p)) != NULL) { // delimiter is the semicolon
    //   // frequency start
    //   if (nn == 0) {
    //     freq_start = atol(str);
    //     // Serial.print("FREQ START = ");
    //     // Serial.println(freq_start);
    //     nn = 1;
    //   }
    //   // frequency stop
    //   else if (nn == 1) {
    //     freq_stop = atol(str);
    //     nn = 2;
    //   }
    //   // frequency step
    //   else if (nn == 2) {
    //     freq_step = atol(str);
    //     nn = 0;
    //     message = 1;
    //   }
    
    // strtok destroys data so a copy is made before with strcpy
    strcpy(tempChars, buf);
    // this is used by strtok() as an index
    char * strtokIndx;
    // gets first part of C-string until delimiter and saves to variable
    strtokIndx = strtok(tempChars,";");
    freq_start = atol(strtokIndx);
    // continues where last call left off and saves to variable
    strtokIndx = strtok(NULL,";");
    freq_stop = atol(strtokIndx);
    // ditto ^
    strtokIndx = strtok(NULL,";");
    freq_step = atoi(strtokIndx);
    // mode
    strtokIndx = strtok(NULL,";");
    mode = atoi(strtokIndx);
    if (debug) {
      Serial.print("Command parsed: ");
      Serial.print(freq_start);
      Serial.print(";");
      Serial.print(freq_stop);
      Serial.print(";");
      Serial.print(freq_step);
      Serial.print(";");
      Serial.println(mode);
    }
    // new_command = 2; // Setting to 2 goes into a simple debug mode
  }

  if (debug && mode != prevMode) {
    Serial.print("Mode changed: ");
    Serial.print(prevMode);
    Serial.print(" -> ");
    Serial.print(mode);
    Serial.print(" freq=");
    Serial.print(freq_start);
    Serial.print(",");
    Serial.print(freq_stop);
    Serial.print(",");
    Serial.println(freq_step);
    if (mode == 3) {
      Serial.println("Mode 3: setting safe frequency (1 MHz)");
    }
    prevMode = mode;
  }

  if (mode == 0) {
    // single sweep - runs once then goes to dummy mode
    if (debug) Serial.println("Mode 0: starting single sweep");
    performSweep(false); // don't check for commands during sweep
    mode = 3; // switch to dummy mode after single sweep
    if (debug) Serial.println("Mode 0: sweep done, switching to mode 3");
  }

  if (mode == 1) {
    // continuous sweep - runs until new command received
    while (mode == 1) {
      // Perform one sweep with command checking
      bool completed = performSweep(true);

      // If sweep was interrupted by new command
      if (!completed) {
        digitalWrite(13, HIGH); // Turn LED on before breaking
        break;
      }

      // Check for new command between sweeps
      if (Serial.available() > 0) {
        break; // LED is already HIGH from performSweep
      }

      // Prepare for next sweep - LED already HIGH from performSweep
      // Set LED LOW for next sweep iteration
      digitalWrite(13, LOW);
    }
  }

  if (mode == 2) {
    // CW output at start frequency
    SetFreq(freq_start);
    digitalWrite(13,HIGH);
  }

  if (mode == 3) {
    // dummy mode - output safe frequency (1 MHz), LED off
    SetFreq(SAFE_FREQ);
    digitalWrite(13,LOW);
  }
}
