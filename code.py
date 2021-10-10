# Encoder with DM8BA10 Display
# rev 1.0 - shabaz - oct 2021

# imports
import time
import board
import digitalio
import rotaryio
import countio

# variables
forever = True

# board LED on the Pi Pico
boardled = digitalio.DigitalInOut(board.GP25)
boardled.direction = digitalio.Direction.OUTPUT

# rotary encoder
enc = rotaryio.IncrementalEncoder(board.GP7, board.GP6)
enc_last_pos = 0
rotval = 100000
rot_edge = countio.Counter(board.GP9)  # used for determining rotation speed

# push-button for manual speed (stepped) selection
speedbutton = digitalio.DigitalInOut(board.GP8)
speedbutton.direction = digitalio.Direction.INPUT
speedrange = 1  # can be set to (say) 1, 1000, 1000000 for Hz, kHz and MHz

# pins for DM8BA10 LCD module
lcd_data = digitalio.DigitalInOut(board.GP20)
lcd_wr = digitalio.DigitalInOut(board.GP21)
lcd_csn = digitalio.DigitalInOut(board.GP22)
lcd_data.direction = digitalio.Direction.OUTPUT
lcd_wr.direction = digitalio.Direction.OUTPUT
lcd_csn.direction = digitalio.Direction.OUTPUT

# other variables
# Bytes to write for decimal place positions 1-9 from the right
LCD_DPBITS = [0x0100, 0x0200, 0x0400, 0x0001, 0x0002, 0x0004, 0x0100, 0x0200, 0x0400]
# Bytes to write for ASCII character set (partial)
LCD_CHARBITS = [
    0x5C5C,  # *
    0x1448,  # +
    0x0800,  # ,
    0x1008,  # -
    0x0000,  # . (unsupported)
    0x0810,  # /
    0xABB3,  # 0
    0x0032,  # 1
    0x93A9,  # 2
    0x81AB,  # 3
    0x302A,  # 4
    0xB18B,  # 5
    0xB30B,  # 6
    0x80A2,  # 7
    0xB3AB,  # 8
    0xB0AB,  # 9
    0xB2AA,  # A
    0x85EB,  # B
    0xA381,  # C
    0x85E3,  # D
    0xB381,  # E
    0xB280,  # F
    0xA38B,  # G
    0x322A,  # H
    0x85C1,  # I
    0x0323,  # J
    0x3214,  # K
    0x2301,  # L
    0x6232,  # M
    0x6226,  # N
    0xA3A3,  # O
    0xB2A8,  # P
    0xA3A7,  # Q
    0xB2AC,  # R
    0xB18B,  # S
    0x84C0,  # T
    0x2323,  # U
    0x2A10,  # V
    0x2A26,  # W
    0x4814,  # X
    0x3428,  # Y
    0x8991,  # Z
    0x0000,  # space
]

boardled.value = True

# initialize the I/O pins
def io_init():
    lcd_csn.value = True
    lcd_wr.value = False
    lcd_data.value = False

# sends up to 8 bits to the LCD
def lcd_sendbits(value, n):
    for i in range(n - 1, -1, -1):
        lcd_data.value = bool(value & (1 << i))
        lcd_wr.value = True
        lcd_wr.value = False
    lcd_data.value = False

# sends command 100 and then 0 and then 8 bits of command
def lcd_sendcmd(cmd):
    lcd_csn.value = False
    lcd_sendbits(0x08, 4)
    lcd_sendbits(cmd, 8)
    lcd_csn.value = True

# sends command 101 (Write mode) followed by an address and then 4 bits of data
def lcd_writemode(addr, data):
    aval = addr << 2
    for i in range(0, 5):
        dval = (data << (i * 4)) >> 12
        lcd_csn.value = False
        lcd_sendbits(0x05, 3)
        lcd_sendbits(aval + i, 6)
        lcd_sendbits(dval, 4)
        lcd_csn.value = True

def lcd_init():
    lcd_sendcmd(0x02)  # SYS_EN
    lcd_sendcmd(0x30)  # RC_32K
    lcd_sendcmd(0x06)  # LCD_ON

def lcd_off():
    lcd_sendcmd(0x04)  # LCD_OFF

def lcd_on():
    lcd_sendcmd(0x06)  # LCD_ON

def lcd_clear():
    for i in range(0, 12):  # 0-9 are the character locations, 10-11 are decimals
        lcd_writemode(i, 0x0000)

def lcd_allon():
    for i in range(0, 12):
        lcd_writemode(i, 0xFFFF)

# inserts a decimal place
def lcd_dp_insert(i):
    if i < 1:
        pass
    elif i < 4:
        lcd_writemode(11, LCD_DPBITS[i - 1])
    elif i < 10:
        lcd_writemode(10, LCD_DPBITS[i - 1])
    else:
        pass

# deletes decimal places
def lcd_dp_clear():
    lcd_writemode(10, 0x0000)
    lcd_writemode(11, 0x0000)

# display an integer number
def lcd_printint(n):
    lcd_clear()
    s = str(n)
    idx = 0
    for c in reversed(s):
        lcd_writemode(idx, LCD_CHARBITS[ord(c) - ord("*")])
        idx = idx + 1

# display a single character
def lcd_printchar(idx, c):
    if (ord(c) == 32):  # found a space
        lcd_writemode(idx, 0x0000)
    elif (ord(c) <= ord("9")):    # found a number
        lcd_writemode(idx, LCD_CHARBITS[ord(c) - ord("*")])
    else:                       # letter A-Z
        lcd_writemode(idx, LCD_CHARBITS[ord(c) - ord("A") + 16])

# display text
def lcd_printtext(s):
    idx = 10 - len(s)
    for c in reversed(s):
        lcd_printchar(idx, c)
        idx = idx + 1

# update value based on encoder/button input
def update_rotval(curr_pos):
    global enc_last_pos
    global rotval
    diff = curr_pos - enc_last_pos  # amount of rotation
    enc_last_pos = curr_pos
    rotspeed = rot_edge.count  # rotspeed is effectively the speed of rotation
    rot_edge.reset()
    if (rotspeed <= 8):
        mult = 1  # slow speed, multiplier is 1
    elif (rotspeed <= 10):  # adjust all these values to set acceleration
        mult = 50  # also adjust all these values for acceleration too
    elif (rotspeed <= 14):
        mult = 100
    else:
        mult = 500
    diff = diff * mult  # apply acceleration factor based on speed of rotation
    diff = diff * speedrange  # multiply further based on button-selected factor
    rotval = rotval + diff  # update the value
    # set limit/boundaries for the rotation value:
    if (rotval < 0):  # remove these lines if negative values are acceptable
        rotval = 0    #

# handle speedrange button when it is pressed
def update_speedrange():
    global speedrange
    # button is pressed so we need to change the speedrange
    if (speedrange == 1):
        speedrange = 1000
        lcd_printchar(9, "K")  # display K for kHz
    elif (speedrange == 1000):
        speedrange = 1000000
        lcd_printchar(9, "M")  # display M for MHz
    else:
        speedrange = 1
        lcd_printchar(8, "Z")
        lcd_printchar(9, "H")  # display HZ for Hz
    time.sleep(0.1)
    while (speedbutton.value is False):  # wait for button to be unpressed
        time.sleep(0.1)
    # button is no longer pressed, we are done.

# main program
def main():
    global enc_last_pos
    global rotval
    io_init()
    lcd_init()
    lcd_clear()
    heartbeat_toggle = False
    time.sleep(0.1)
    lcd_printtext("HI THERE")  # mainly only uppercase and numerics supported today
    time.sleep(1)
    lcd_printint(rotval)  # display the initial value

    while forever:  # forever loop
        # alternately set the LED on/off during each loop
        heartbeat_toggle = not(heartbeat_toggle)
        boardled.value = heartbeat_toggle  # toggle the LED
        # handle rotary encoder
        enc_pos = enc.position  # read the rotary encoder value
        if (enc_pos != enc_last_pos):  # encoder has been rotated!
            update_rotval(enc_pos)
            lcd_printint(rotval)  # display the value
        # handle manual speed step button
        if (speedbutton.value is False):  # button is pressed!
            update_speedrange()
            lcd_printint(rotval)  # clear the display and print the value
            time.sleep(0.04)  # button unpress debounce period
        # brief pause
        time.sleep(0.04)  # pause briefly then loop back

# run the main program function
main()
