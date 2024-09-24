#include <TimerOne.h>
#include <SoftwareSerial.h>

const byte rxPin = 2;
const byte txPin = 3;
SoftwareSerial mySerial(rxPin, txPin, 1);
const int LedPin = 9;
bool pinStatus = 0;
long fps = 120;
float duration = 5000.0;
int input;
float dutyCycle = 30.0;
char firstLetter;

// stimulation params
String inputString = ""; //main captured String
char delimiter = ',';             // Delimiter to split the string
char stimDelim = '-';             // Delimiter to split the string
// int pulse_interval;
// int pulse_dutyCycle;
bool stimulation_status = false;
const int stimulationPin = 10;  // has to be pin 9 or pin 10
const int MAX_VALUES = 100;  // Maximum number of values to parse
// String parsedValues[MAX_VALUES];  // Array to store parsed values
String* stimulations;  // list of stimulation profiles
// String stimParams[4];  // Array to store [turnOn_times (s), stimulation_durations (ms), pulse_intervals (ms), pulse_dutyCycles (percent)]
int stimOnTime;  // sec
int stimDuration;  // ms
int stimPulseDur;  // ms
int stimPulseDutyCycle;  // percent
int stimProfileIndex;
int numStimProfiles;
bool stimTrigger = false;

unsigned long startTime;
unsigned long endTime;

void setup() {
  Serial.begin(115200);
  digitalWrite(LedPin, LOW);
  digitalWrite(stimulationPin, LOW);
  pinMode(LED_BUILTIN, OUTPUT);
  // pinMode(stimulationPin, OUTPUT);
}

void loop() {
  if (Serial.available() > 0) {
    inputString = Serial.readStringUntil('\n');
    
    if (inputString.length() > 0) {
      firstLetter = inputString.charAt(0);

      // Print the received string
      Serial.print("You entered: ");
      Serial.println(inputString);
      Serial.print("The first letter: ");
      Serial.println(firstLetter);

      switch (firstLetter) {
        case 'D':
          decode_stimulation();
          stimProfileIndex = 1;
          update_stimParams();
          break;
        case 'V':
          stop_stimulation();
          break;
        case 'S':
          start_frame_trigger();          
          break;
        case 'Q':
          stop_frame_trigger();
          break;
        case 'T':
          stimProfileIndex = 1;
          update_stimParams();
          stimTrigger = true;
          startTime = millis();
          Serial.println("Stimulation trigger received.");
          break;          
        default:
          Serial.print("Unrecognized first letter: ");
          Serial.println(firstLetter);
          break;
      }

    } else {
      Serial.println("You entered an empty string.");
    }
  }

  endTime = millis();

  if (stimTrigger) {
    // Serial.print("Cur time: ");
    // Serial.println(endTime - startTime);
    if (!stimulation_status) {
      if ((endTime - startTime) > stimOnTime * 1000) {
        start_stimulation();
      }
    } else {
      if ((endTime - startTime) > ((stimOnTime * 1000) + stimDuration)) {
        stop_stimulation();
        stimProfileIndex++;
        if (stimProfileIndex <= numStimProfiles) {
          update_stimParams();
        } else {
          stimTrigger = false;
          Serial.println("Stimulations ended.");
        }
      }
    }
  }
  // delay(100);
}

void decode_stimulation(void) {
  stimulations = parseInputString(inputString, delimiter);
  numStimProfiles = getValueCount(inputString, delimiter);  // Get the count of parsed values
  numStimProfiles--;

  Serial.print("Num. of stimulations: ");
  Serial.println(numStimProfiles);
  Serial.println("Stimulation profiles: [turnOn_times (s), stimulation_durations (ms), pulse_intervals (ms), pulse_dutyCycles (percent)]");
  for (int i = 1; i <= numStimProfiles; i++) {
    Serial.print(i);
    Serial.print(". Stimulation: ");
    Serial.println(stimulations[i]);
  }
}

void update_stimParams(void) {
  String* cur_stimParams = parseInputString(stimulations[stimProfileIndex], stimDelim);
  // int valueCount = getValueCount(stimulations[stimProfileIndex], stimDelim);  // Get the count of parsed values
  
  stimOnTime = cur_stimParams[0].toInt();
  stimDuration = cur_stimParams[1].toInt();
  stimPulseDur = cur_stimParams[2].toInt();
  stimPulseDutyCycle = cur_stimParams[3].toInt();

  Serial.println("\nUpdated stimParams:");
  Serial.print("stimOnTime: ");
  Serial.println(stimOnTime);
  Serial.print("stimDuration: ");
  Serial.println(stimDuration);
  Serial.print("stimPulseDur: ");
  Serial.println(stimPulseDur);
  Serial.print("stimPulseDutyCycle: ");
  Serial.println(stimPulseDutyCycle);
}

void Timer1_ISR(void) {
  digitalWrite(stimulationPin, !digitalRead(stimulationPin));
}

void start_stimulation(void) {
  Timer1.initialize(1000000 / (1000 / stimPulseDur)); // microsec
  // Timer1.initialize(float(1000 * stimPulseDur)); // microsec
  // Timer1.initialize(1000000 / stimPulseDur * 1000); // microsec
  float cur_duty = (float(stimPulseDutyCycle) / 100) * 1023;
  Timer1.pwm(stimulationPin, cur_duty);
  // Timer1.pwm(stimulationPin, float(stimPulseDutyCycle) / 100 * 1023);
  // Timer1.setPwmDuty(stimulationPin, (stimPulseDutyCycle / 100) * 1023);
  // Timer1.pwm(stimulationPin, (stimPulseDutyCycle / 100) * 1023, stimPulseDur * 1000);
  // Timer1.attachInterrupt(Timer1_ISR, stimPulseDur * 10);
  // Timer1.start();
  // Timer1.initialize(1000000 / 10);
  // Timer1.pwm(stimulationPin, 512);
  stimulation_status = true;
  // digitalWrite(stimulationPin, HIGH);
  Serial.println("Stimulation started.");
}

void stop_stimulation(void) {
  Timer1.disablePwm(stimulationPin);
  Timer1.detachInterrupt();
  digitalWrite(stimulationPin, 0);
  Timer1.stop();
  stimulation_status = false;
  // digitalWrite(stimulationPin, LOW);
  Serial.println("Stimulation stopped.");
}

void start_frame_trigger(void) {
  // fps = Serial.parseInt();
  String* parsedValues = parseInputString(inputString, delimiter);
  int valueCount = getValueCount(inputString, delimiter);  // Get the count of parsed values
  // Serial.print("valueCount: ");
  // Serial.println(valueCount);
  // Serial.println("Parsed values:");
  // for (int i = 0; i < valueCount; i++) {
  //   Serial.println(parsedValues[i]);
  // }
  fps = parsedValues[1].toInt();
  Serial.print("Received fps: ");
  Serial.println(fps);

  if (pinStatus == 1) {
    stop_frame_trigger();
  }

  // if (pinStatus == 0) {
  Timer1.initialize(1000000 / fps); // 40 us = 25 kHz
  dutyCycle = duration / (1000000 / fps); // calculate duty cycle to have pulse length ~5ms
  Serial.print("Duty cycle: ");
  Serial.println(dutyCycle);
  Timer1.pwm(LedPin, (dutyCycle) * 1023);
  pinStatus = 1;
  Serial.println("Frame trigger started.");
  // }
}

void stop_frame_trigger(void) {
  Timer1.disablePwm(LedPin);
  Timer1.stop();
  Serial.println("Frame trigger stopped.");
  pinStatus = 0;
}

String* parseInputString(String input_str, char delim) {
  int valueCount = getValueCount(input_str, delim);  // Get the count of parsed values

  // Dynamically allocate memory for the parsedValues array
  String* parsedValues = new String[valueCount];

  int startIndex = 0;
  int endIndex = 0;
  int currentIndex = 0;

  while (endIndex >= 0) {
    endIndex = input_str.indexOf(delim, startIndex); // Find the delimiter
    if (endIndex == -1) {  // If no more delimiter is found, get the last part
      parsedValues[currentIndex] = input_str.substring(startIndex);
    } else {
      parsedValues[currentIndex] = input_str.substring(startIndex, endIndex);
    }
    startIndex = endIndex + 1;  // Move to the next part
    currentIndex++;
  }
  return parsedValues;
}

// Function to count the number of values separated by the delimiter
int getValueCount(String input_str, char delim) {
  int count = 1;  // At least one value is present
  for (int i = 0; i < input_str.length(); i++) {
    if (input_str.charAt(i) == delim) {
      count++;
    }
  }
  return count;
}