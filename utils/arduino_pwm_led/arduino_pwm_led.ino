#include <TimerOne.h>
#include <SoftwareSerial.h>

const byte rxPin = 2;
const byte txPin = 3;
SoftwareSerial mySerial(rxPin, txPin, 1);
const int LedPin = 11; // 9 for timer1, 11 for timer2;
int onTime, offTime; // Variables to hold on and off times
volatile int counter = 0; // Counter to track ISR calls
volatile bool ledState = false; // Current state of the LED
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
  pinMode(LedPin, OUTPUT);
  
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
          trigger_stimulation();
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

void trigger_stimulation(void) {
  stimProfileIndex = 1;
  update_stimParams();
  stimTrigger = true;
  startTime = millis();
  Serial.println("Stimulation trigger received.");
}

void start_stimulation(void) {
  Timer1.initialize(1000 * float(stimPulseDur)); // microsec
  Timer1.pwm(stimulationPin, (float(stimPulseDutyCycle) / 100) * 1023);
  // Timer1.setPwmDuty(stimulationPin, (stimPulseDutyCycle / 100) * 1023);
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
  
  String* parsedValues = parseInputString(inputString, delimiter);
  int valueCount = getValueCount(inputString, delimiter);  // Get the count of parsed values
  // Serial.print("valueCount: ");
  // Serial.println(valueCount);
  // Serial.println("Parsed values:");
  // for (int i = 0; i < valueCount; i++) {
  //   Serial.println(parsedValues[i]);
  // }
  fps = parsedValues[1].toInt();
  // Serial.print("Received fps: ");
  // Serial.println(fps);

  // if (pinStatus == 1) {
  //   stop_frame_trigger();
  // }

  // // if (pinStatus == 0) {
  // Timer1.initialize(1000000 / fps); // 40 us = 25 kHz
  // dutyCycle = duration / (1000000 / fps); // calculate duty cycle to have pulse length ~5ms
  // Serial.print("Duty cycle: ");
  // Serial.println(dutyCycle);
  // Timer1.pwm(LedPin, (dutyCycle) * 1023);

  // setupBlink_Timer2(int(fps), 50);
  setupBlink_Timer2(int(fps) * 100, 100 / 3);  // multiply fps by 100 when using timer2, for 60 fps: duty cycle 30-33%
  // setupBlink_Timer2(int(fps) * 100, 100 / 3 * 2);  // multiply fps by 100 when using timer2, for 120 fps: duty cycle 66%
  // setupBlink_Timer2(2, 50);
  // setupPWM_Timer2(int(fps));

  pinStatus = 1;
  Serial.println("Frame trigger started.");
  // }
}

void setupBlink_Timer2(int FPS, float dutyCycle) {
  // Calculate the timer period in microseconds
  unsigned long period = 1000000 / FPS; // Full period in microseconds

  // Calculate on and off times based on the duty cycle
  onTime = int((period * dutyCycle) / 100); // Time LED stays on in microseconds
  offTime = period - onTime; // Time LED stays off in microseconds

  // Set up Timer2 for CTC mode (Clear Timer on Compare Match)
  TCCR2A = (1 << WGM21);  // CTC mode
  TCCR2B = (1 << CS22) | (1 << CS21) | (1 << CS20);  // Prescaler set to 1024

  // Set the initial compare match value based on the onTime
  OCR2A = ((onTime * 16) / 1024) - 1;  // Convert microseconds to timer counts

  // Enable Timer2 compare interrupt
  TIMSK2 = (1 << OCIE2A);
}

ISR(TIMER2_COMPA_vect) {
  counter++;

  if (ledState && counter * 1024UL / 16 >= onTime) {
    ledState = false;  // Turn LED off
    OCR2A = ((offTime * 16) / 1024) - 1;  // Set next compare to offTime
    counter = 0;
  } else if (!ledState && counter * 1024UL / 16 >= offTime) {
    ledState = true;  // Turn LED on
    OCR2A = ((onTime * 16) / 1024) - 1;  // Set next compare to onTime
    counter = 0;
  }

  digitalWrite(LedPin, ledState); // Update the LED
}

void setupPWM_Timer2(int FPS) {

  // Stop the timer while configuring
  TCCR2A = 0;              // Clear control register A
  TCCR2B = 0;              // Clear control register B
  TCNT2  = 0;              // Initialize counter to 0

  // Set Fast PWM mode with non-inverted output on OC2A (Pin 11)
  TCCR2A |= (1 << WGM21) | (1 << WGM20);  // Fast PWM Mode
  TCCR2A |= (1 << COM2A1);                // Non-inverted PWM

  // Calculate the required PWM frequency
  long pwmFrequency = FPS;

  // Calculate the necessary prescaler based on the desired FPS (f_PWM)
  long baseFrequency = 16000000L; // Arduino clock speed is 16 MHz
  int prescaler = 1;
  if (pwmFrequency < baseFrequency / (256L * 1024)) {
    prescaler = 1024;
    TCCR2B |= (1 << CS22) | (1 << CS21) | (1 << CS20);
  } else if (pwmFrequency < baseFrequency / (256L * 256)) {
    prescaler = 256;
    TCCR2B |= (1 << CS22) | (1 << CS21);
  } else if (pwmFrequency < baseFrequency / (256L * 128)) {
    prescaler = 128;
    TCCR2B |= (1 << CS22) | (1 << CS20);
  } else if (pwmFrequency < baseFrequency / (256L * 64)) {
    prescaler = 64;
    TCCR2B |= (1 << CS22);
  } else if (pwmFrequency < baseFrequency / (256L * 32)) {
    prescaler = 32;
    TCCR2B |= (1 << CS21) | (1 << CS20);
  } else if (pwmFrequency < baseFrequency / (256L * 8)) {
    prescaler = 8;
    TCCR2B |= (1 << CS21);
  } else {
    prescaler = 1;
    TCCR2B |= (1 << CS20);
  }

  // Set OCR2A (duty cycle)
  OCR2A = 128;  // Set duty cycle to 50%

  // Now the PWM frequency is set to approximately the given FPS
  long actualFrequency = baseFrequency / (prescaler * 256L);
  
  Serial.print("Actual PWM Frequency: ");
  Serial.println(actualFrequency);
}

void stop_frame_trigger(void) {
  // Timer1.disablePwm(LedPin);
  // Timer1.stop();

  // Stop the timer and disable PWM by clearing the relevant bits
  TCCR2A = 0;  // Clear the Timer2 control register A (disables PWM)
  TCCR2B = 0;  // Clear the Timer2 control register B (stops the timer)
  TIMSK2 = 0;
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