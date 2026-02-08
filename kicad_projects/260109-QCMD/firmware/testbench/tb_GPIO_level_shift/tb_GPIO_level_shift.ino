#include<Wire.h>
// libraries included in /src folder
// # include "src/Adafruit_MCP9808.h"
// V2.1_T40 using ADC library by pedvide 
# include "src/ADC/ADC.h"
# include "src/ADC/ADC_util.h"

#define REFCLK 180000000
// safe default frequency for dummy mode (1 MHz)
#define SAFE_FREQ 1000000

// V2.1_T40 ADC averaging and resolution define 
#define AVERAGING   1  // hardware average#
#define RESOLUTION 12

// current input frequency
long freq = 0;

// V2.1_T40 DDS Synthesizer AD9851 pin function
int WCLK = A7; //3;
int DATA = A8;  //4;
int FQ_UD = A6;  //2;

// frequency tuning word
long FTW;
float temp_FTW; // temporary variable

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

// init sweep param
long freq_start = 40680000;
long freq_stop = 40690000;
long freq_step = 1000;

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


void setup() {
  // put your setup code here, to run once:
  Serial.begin(115200);

  // AD9851 set pin mode
  pinMode(WCLK, OUTPUT);
  pinMode(DATA, OUTPUT);
  pinMode(FQ_UD, OUTPUT);

  // test 3.3V and 5V control logic level
  digitalWrite(WCLK, HIGH);
  digitalWrite(DATA, HIGH);
  digitalWrite(FQ_UD, HIGH);

  // AD9851 enter serial mode
  // digitalWrite(WCLK, HIGH);
  // digitalWrite(WCLK, LOW);
  // digitalWrite(FQ_UD, HIGH);
  // digitalWrite(FQ_UD, LOW);

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


void loop() {
  // put your main code here, to run repeatedly:
  // SetFreq(1000000);
  digitalWrite(13,HIGH);
}
