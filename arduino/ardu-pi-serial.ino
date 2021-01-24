  #include <DHT.h>

  #define MOISTURE_PIN A0
  #define LIGHT_PIN A1

  #define RELAY_PIN 4
  #define DHT_PIN 8

  #define DHTTYPE DHT11

DHT dht(DHT_PIN, DHTTYPE);

const int AirValue = 620;
const int WaterValue = 240;

int soilMoistureValue = 0;
int soilMoisturePercent = 0;
int lightIntensityValue = 0;
int lightIntensityPercent = 0;
int temp = 0;
int humidity = 0;

char sendBuffer[32];
char ch = 0;

void setup() {
  Serial.begin(9600); // open serial port, set the baud rate to 9600 bps
  pinMode(LED_BUILTIN, OUTPUT);
  digitalWrite(LED_BUILTIN, LOW);
  pinMode(RELAY_PIN, OUTPUT);
}

void loop() {
  if (Serial.available()) {
    ch = Serial.read();
    if (ch== '0') {
      sendTelemetry();
    }

    if (ch == '1') {
      activatePump();
    }

    if (ch == '2') {
      deactivatePump();
    }
  }
}

void activatePump() {
  Serial.println("Activating relay");
  digitalWrite(RELAY_PIN, HIGH);
}

void deactivatePump() {
  Serial.println("Deactivating relay");
  digitalWrite(RELAY_PIN, LOW);
}

void sendTelemetry() {
  digitalWrite(LED_BUILTIN, HIGH);
  
  soilMoistureValue = analogRead(MOISTURE_PIN);  //put Sensor insert into soil
  lightIntensityValue = analogRead(LIGHT_PIN);

  temp = dht.readTemperature();
  humidity = dht.readHumidity();

  // transform raw values in percentage depending on calibration and linear interpolation
  soilMoisturePercent = map(soilMoistureValue, AirValue, WaterValue, 0, 100);
  lightIntensityPercent = map(lightIntensityValue, 1023, 0, 0, 100);
  if(soilMoisturePercent > 100){ 
    soilMoisturePercent = 100;
  }else if(soilMoisturePercent < 0){
    soilMoisturePercent = 0;
  }

  // send as telemetry data
  memset(sendBuffer, 0, sizeof(sendBuffer));
  sprintf(sendBuffer, "S m:%d l:%d t:%d h:%d", soilMoisturePercent, lightIntensityPercent, temp, humidity);
    
  Serial.println(sendBuffer);
  
  digitalWrite(LED_BUILTIN, LOW);
}
