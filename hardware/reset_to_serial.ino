/* File Name: reset_tfmini_to_uart
 * Developer: Christopher Gill
 Bud R
 * Inception: 05 Nov 2022
 * Description: Runs an I2C search to find a connected TFMini-S. Resets it to Serial mode.
 * Credits: Bud Ryerson, who wrote the original TFMini Arudino library, and whose I2C 
 *          address changing example script is the backbone of thise tool.
 */

#include <Wire.h>     // Arduino standard I2C/Two-Wire Library
#include "printf.h"   // Modified to support Intel based Arduino
                      // devices such as the Galileo. Download from:
                      // https://github.com/spaniakos/AES/blob/master/printf.h

#include <TFMPlus.h>  // Include TFMini Plus Library
TFMPlus tfmP;         // Create a TFMini-Plus Serial object
#include <TFMPI2C.h> // Include the TFMini Plus I2C Library
TFMPI2C tfmPI2C;

#include <SoftwareSerial.h>
SoftwareSerial mySerial(10,11); // Create a Serial interface.

// Declare variables
int I2C_total, I2C_error;
uint8_t oldAddr, newAddr;
bool serial_started = false;

bool scanAddr()
{
    Serial.println();
    Serial.println( "Show all I2C addresses in Decimal and Hex.");
    Serial.println( "Scanning...");
    I2C_total = 0;
    I2C_error = 0;
    oldAddr = 0x10; // default address
    for( uint8_t x = 1; x < 127; x++ )
    {
        Wire.beginTransmission( x);
        // Use return value of Write.endTransmisstion() to
        // see if a device did acknowledge the I2C address.
        I2C_error = Wire.endTransmission();

        if( I2C_error == 0)
        {
            Serial.print( "I2C device found at address ");
            printAddress( x);
            ++I2C_total;   //  Increment for each address returned.
            if( I2C_total == 1) oldAddr = x;
        }
        else if( I2C_error == 4)
        {
            Serial.print( "Unknown I2C error at address ");
            Serial.println( x);
        }
    }
    //  Display results and return boolean value.
    if( I2C_total == 0)
    {
      Serial.println( "No I2C devices found.");
      return false;
    }
    else return true;
}

// Print address in decimal and HEX
void printAddress( uint8_t adr)
{
    Serial.print( adr);
    Serial.print( " (0x");
    Serial.print( adr < 16 ? "0" : ""); 
    Serial.print( adr, HEX);
    Serial.println( " Hex)");
}

void setup()
{
    Wire.begin();            // Initialize two-wire interface
    Serial.begin(115200);   // Initialize terminal serial port
    printf_begin();          // Initialize printf library.
	  delay(20);
    serial_started = false;

    Serial.flush();          // Flush serial write buffer
    while( Serial.available())Serial.read();  // flush serial read buffer
}

void tfserial_setup()
{
  mySerial.begin(115200);
  delay(20);
  tfmP.begin(&mySerial);
    printf( "Firmware version: ");
    if( tfmP.sendCommand( GET_FIRMWARE_VERSION, 0))
    {
        printf( "%1u.", tfmP.version[ 0]); // print three single numbers
        printf( "%1u.", tfmP.version[ 1]); // each separated by a dot
        printf( "%1u\r\n", tfmP.version[ 2]);
    }
    else tfmP.printReply();
    // - - Set the data frame-rate to 20Hz - - - - - - - -
    printf( "Data-Frame rate: ");
    if( tfmP.sendCommand( SET_FRAME_RATE, FRAME_20))
    {
        printf( "%2uHz.\r\n", FRAME_20);
    }
    else tfmP.printReply();
}

// = = = = = = = = = =  MAIN LOOP  = = = = = = = = = =
void loop()
{
     // Scan for I2C addresses, first one found must be the sensor.
    if( scanAddr() )
    {
      Serial.println();
      Serial.print( "I2C address found: ");
      printAddress( oldAddr);
      Serial.println( "Setting sensor to serial mode.");
      if ( tfmPI2C.sendCommand(SET_SERIAL_MODE, 0, oldAddr))
      {
        Serial.println("Mode change successful");
        if ( tfmPI2C.sendCommand(SAVE_SETTINGS, 0, oldAddr))
        {
          Serial.println("Saved settings.");
        }
        else
        {
          Serial.println("Could not save settings.");
        }
      }
      else
      {
        Serial.println("Mode reset failed.");
      }
    }
    else
    {
      Serial.println("No sensor found on I2C. Trying serial.");
      if ( serial_started )
      { 
        int16_t tfDist = 0;    // Distance to object in centimeters
        int16_t tfFlux = 0;    // Strength or quality of return signal
        int16_t tfTemp = 0;    // Internal temperature of Lidar sensor chip
        
        if( tfmP.getData( tfDist, tfFlux, tfTemp)) // Get data from the device.
        {
          printf( "Dist:%04icm ", tfDist);   // display distance,
          printf( "Flux:%05i ",   tfFlux);   // display signal strength/quality,
          printf( "Temp:%2i%s",  tfTemp, "C");   // display temperature,
          printf( "\r\n");                   // end-of-line.
        }
        else                  // If the command fails...
        {
        tfmP.printFrame();  // display the error and HEX dataa
        }
      } 
      else
      {
        Serial.println("Doing TF sensor serial setup...");
        tfserial_setup();
        serial_started = true;
      }
    }

    Serial.println();    
    Serial.println( "Program will restart in 30 seconds.");
    Serial.println( "*****************************");
    delay( 30000);           // And wait for 30 seconds
}
// = = = = = = = = =  End of Main Loop  = = = = = = = = =
