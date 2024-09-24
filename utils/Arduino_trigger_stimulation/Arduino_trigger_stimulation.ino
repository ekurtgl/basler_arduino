#include <TimerOne.h>
#include <SoftwareSerial.h>
// check signal parameters from serial
// if first charakter 'S' start interrupt
// integer following S ist the FPS-setting
// if first charakter 'Q' stop interrupt
// dutycycle is set in dependancy of freq  to be ~ 5ms
// if first charakter 'T' send following string to intan
const byte rxPin = 2;
const byte txPin = 3;
SoftwareSerial mySerial(rxPin, txPin, 1);
const int LedPin = 9;
bool pinStatus = 0;
long fps = 120;
float duration = 5000.0;
int input;
float dutyCycle = 30.0;

// stimulation params
String inputString = ""; //main captured String
char delimiter = ',';             // Delimiter to split the string
int values[10];  // [fres (Hz), duty cycle (percent)]
bool stringComplete = false;
int pulse_interval;
int pulse_dutyCycle;
bool stimulation_status = false;
const int stimulationPin = 10;  // has to be pin 9 or pin 10

void setup(void)
{
  Serial.begin(115200); //9600);
  //mySerial.begin(600);
  digitalWrite(LedPin, LOW);
  digitalWrite(stimulationPin, LOW);
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop(void)
{
  if (Serial.available() > 0)
  {
    input = Serial.read();
    if (input == 'P') // Poll the arduino, expect answer bit '1'
    {
      Serial.print(1);
    }

    if (input == 'Q')
    {
      if (pinStatus == 1)
      {
        Timer1.disablePwm(LedPin);
        Timer1.stop();
        Serial.println(3);
        pinStatus = 0;
      }
    }

    if (input == 'R')  // stimulation start trigger
    {
      start_stimulation();
    }

    if (input == 'V')  // stimulation stop trigger
    {
      stop_stimulation();
    }

    if (input == 'S')
    {
      fps = Serial.parseInt();
      Serial.print("received fps: ");
      Serial.println(fps);
      // Serial.print('\n');
      //duration=(float)Serial.parseInt(); // if we also want to set a duration of pulse
      if (pinStatus == 0)
      {
        Timer1.initialize(1000000 / fps); // 40 us = 25 kHz
        dutyCycle = duration / (1000000 / fps); // calculate duty cycle to have pulse length ~5ms
        // Serial.print(dutyCycle);
        // Serial.print('\n');
        Timer1.pwm(LedPin, (dutyCycle) * 1023);
        pinStatus = 1;
      }
    }
    if (input == 'T')
    {
      String text = Serial.readString();
      mySerial.print(text); //Write the text from Serial port
    }
    delay(100);
  }
}

void start_stimulation(void)
{
  // inputString = "";
  serialEvent();

  Serial.println();
  // Serial.println(Serial.available()); //prints string to serial port out
  Serial.print("captured start String is : "); 
  Serial.println(inputString); //prints string to serial port out

  if (stimulation_status) {
    stop_stimulation();
  }

  if (stringComplete) {
    int numValues = splitString(inputString, delimiter, values, 10); // Parse the string and count values

    // Print the parsed values
    for (int i = 0; i < numValues; i++) {
      Serial.print("Value ");
      Serial.print(i + 1);
      Serial.print(": ");
      Serial.println(values[i]);
    }

    pulse_interval = values[1];
    pulse_dutyCycle = values[2];
    Serial.print("pulse_interval: ");
    Serial.println(pulse_interval);
    Serial.print("pulse_dutyCycle: ");
    Serial.println(pulse_dutyCycle);

    // Clear the inputString and reset the flag
    inputString = "";
    stringComplete = false;

    Timer1.initialize(pulse_interval * 1000); // microsec
    Timer1.pwm(stimulationPin, (pulse_dutyCycle / 100) * 1023);
    stimulation_status = true;
    Serial.println("Stimulation started.");
    // digitalWrite(LED_BUILTIN, HIGH);  // turn the LED on (HIGH is the voltage level)
    // delay(1000);                      // wait for a second
    // digitalWrite(LED_BUILTIN, LOW);   // turn the LED off by making the voltage LOW
    // delay(1000);  
  }

}

void stop_stimulation(void)
{
  // Serial.println();
  // Serial.print("captured stop String is : "); 
  // Serial.println(inputString); //prints string to serial port out

  Timer1.disablePwm(stimulationPin);
  Timer1.stop();
  stimulation_status = false;
  Serial.println("Stimulation stopped.");
}

int splitString(String input, char delimiter, int *outputArray, int arraySize) {
  int startIndex = 0;
  int endIndex = 0;
  int arrayIndex = 0;

  // Iterate through the string and extract values
  while ((endIndex = input.indexOf(delimiter, startIndex)) != -1 && arrayIndex < arraySize) {
    outputArray[arrayIndex++] = input.substring(startIndex, endIndex).toInt();
    startIndex = endIndex + 1;
  }

  // Get the last value (or the only value if no delimiter was found)
  if (arrayIndex < arraySize) {
    outputArray[arrayIndex++] = input.substring(startIndex).toInt();
  }

  return arrayIndex;  // Return the number of parsed values
}

// This function is called when serial data is available
void serialEvent()
{
  while (Serial.available()) {
    char inChar = (char)Serial.read();
    
    // Check if the input string is complete (when newline is received)
    if (inChar == '\n') {
      stringComplete = true;
      break;
    }

    // Add the received character to the inputString
    inputString += inChar;
    
  }
}