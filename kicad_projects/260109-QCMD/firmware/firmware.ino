// Code based on examples by OpenQCM and Brett Killion (Hackaday forum)
// Written and adapted by Rens Horst

#include<Wire.h>
#include <ADC.h>


// Constants Declaration
// potentiometer AD5252 I2C address is 0x2C(44)
#define ADDRESS 0x2C
// Potentiometer value AD5252 (8 bit)
#define POT_VALUE 254
// Reference clock
#define REFCLK 180000000

// Variable Declaration
// DDS Synthesizer AD9851 pin function
int WCLK = A7;
int DATA = A8;
int FQ_UD = A6;

// Frequency Tuning Word
long FTW;
float temp_FTW; // temporary variable

// AD8310 pinout
int AD8310_MAG = 16; //16 for teensy 4.0 and 37 for teensy 3.6

// ADC object creation
ADC *adc = new ADC(); // ADC object

// ADC initialization variables
// ADC waiting delay microseconds
int WAIT_DELAY_US = 10;
// ADC averaging
boolean AVERAGING = true;
// inint number of averaging
int AVERAGE_SAMPLE = 2048;
// teensy ADC averaging init
int ADC_RESOLUTION = 12;

// code variables
long freq_start;
long freq_stop;
int freq_step;
char tempChars[64]; 
int new_command = 0;
/////////////////////////////////////////////////////////////////////////////////////////////////////////


void setup()
{
  // ADC settings
  // ADC 0
  adc->adc0->setAveraging(1); // set number of averages
  adc->adc0->setResolution(12); // set bits of resolution
  adc->adc0->setConversionSpeed(ADC_CONVERSION_SPEED::VERY_HIGH_SPEED);
  adc->adc0->setSamplingSpeed(ADC_SAMPLING_SPEED::VERY_HIGH_SPEED); 
  // ADC 1
  adc->adc1->setAveraging(1); // set number of averages
  adc->adc1->setResolution(12); // set bits of resolution
  adc->adc1->setConversionSpeed(ADC_CONVERSION_SPEED::VERY_HIGH_SPEED);
  adc->adc1->setSamplingSpeed(ADC_SAMPLING_SPEED::VERY_HIGH_SPEED);
  // Start synchronized reading by both ADCs
  adc->startSynchronizedContinuous(AD8310_MAG, AD8310_MAG);
  
  // Initialise I2C communication as Master
  Wire.begin();
  // Initialise serial communication
  Serial1.begin(2000000);
  // Start I2C transmission
  Wire.beginTransmission(ADDRESS);
  // Send instruction for POT channel-0
  Wire.write(0x01);
  // Input resistance value
  Wire.write(POT_VALUE);
  // Stop I2C transmission
  Wire.endTransmission();

  // AD9851 set pin mode
  pinMode(WCLK, OUTPUT);
  pinMode(DATA, OUTPUT);
  pinMode(FQ_UD, OUTPUT);

  // AD9851 enter serial mode, not necessary on our board as it is hardwired for serial mode.
  //digitalWrite(WCLK, HIGH);
  //digitalWrite(WCLK, LOW);
  //digitalWrite(FQ_UD, HIGH);
  //digitalWrite(FQ_UD, LOW);

  // AD8302 set measurement pin mode
  pinMode(AD8310_MAG, INPUT);

  // Initialize LED pins
  pinMode(13, OUTPUT);
  pinMode(14, OUTPUT);
  pinMode(15, OUTPUT);
  digitalWrite(14,HIGH);
  digitalWrite(15,HIGH);
}

/////////////////////////////////////////////////////////////////////////////////////////////////////////

// AD9851 set frequency fucntion
void Set_Frequency(long frequency)
{
// Transform input frequency to tuning word using 180 MHz internal clock
  temp_FTW = (frequency * pow(2, 32)) / REFCLK;
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
    if (i==0) digitalWrite(DATA, HIGH);
    else digitalWrite(DATA, LOW);
    digitalWrite(WCLK, HIGH);
    digitalWrite(WCLK, LOW);
    pointer2 = pointer2 >> 1;
  }
  // Tuning word and phase commands sent.
  digitalWrite(FQ_UD, HIGH);
  digitalWrite(FQ_UD, LOW);
}

/////////////////////////////////////////////////////////////////////////////////////////////////////////

void loop()
{
  if (Serial.available()>0) // Checks for available serial data
  {
    // reads the message sent, delimited by ;.
    String message_str = Serial.readStringUntil('\n');
    // buffer array for storing the message in char form temporarily
    char buffer_array[64];
    //Serial.println(message_str); // debugging line
    // the String format is converted to C-string and stored in the buffer array
    message_str.toCharArray(buffer_array, sizeof(buffer_array));

    // strtok destroys data so a copy is made before with strcpy
    strcpy(tempChars, buffer_array);
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
    new_command = 1; // Setting to 2 goes into a simple debug mode
  }

  if (new_command == 1) // Start of frequency sweep loop
  { 
    digitalWrite(13,LOW); // LED indicator of sweep
    Serial.write("b,"); // Start of data transmission back to Python for 1 full sweep
    for (int i=freq_start; i<=freq_stop; i+= freq_step) // Initialization of sweep for loop
    {
      Set_Frequency(i); // Set the appropriate frequency i
      // Storage variable declaration
      uint16_t reading = 0;
      uint32_t avg_measurement = 0;
      if (AVERAGING == true){
        for (int i=0; i< AVERAGE_SAMPLE; i+=1){
            // Reading of the two ADC measurements
            ADC::Sync_result result = adc->readSynchronizedContinuous();
            // Addition of both measurements
            avg_measurement += result.result_adc0 + result.result_adc1;
          }
          //Averaging over all the measurements for one frequency
          reading = 10*avg_measurement/(2* AVERAGE_SAMPLE);
        }
      // If no averaging is used, this will be activated. Not used often.
      else if(AVERAGING == false){
        ADC::Sync_result result = adc->analogSyncRead(AD8310_MAG, AD8310_MAG);
        reading = (result.result_adc0 + result.result_adc1)/2;
      }
      // Collection and sending of the data of one frequency in the form of two bytes. 
      uint8_t byte_array[2] = {reading >> 8, reading & 0xFF};
      Serial.write(byte_array, 2);
    }
    // End of transmission
    Serial.write("s");
    // End of sweep LED indicator
    digitalWrite(13,HIGH);
    // Resets to wait for serial data command
    new_command = 0;
    
  }
  // Debug part for setting individual frequencies
  if (new_command == 2)
  { 
    Set_Frequency(5000000);
    digitalWrite(13,HIGH);
    new_command = 3;
  }
}
