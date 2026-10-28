# gree-smartir

Generates a complete [SmartIR](https://github.com/smartHomeHub/SmartIR) climate code file for air conditioners that speak the Gree YAW1F infrared protocol, as Broadlink base64 frames. I wrote it for a Whirlpool SPIS412L, which is a rebadged Gree.

SmartIR's existing file for this unit (`1540.json`) covers heat and cool from 18 to 30 °C. Learning every other combination by hand means hundreds of button presses, so this script builds the frames from the protocol instead:

- modes: heat, cool, dry, fan_only (dry locks the fan to low, like the remote)
- 16 to 30 °C
- fan: auto, low, medium, high
- swing: off, auto
- optional display control: `off_screen_on` and `auto_screen_on` set the Gree light bit, so the unit's display is lit. Without it the display stays dark.

## Usage

```sh
python3 gree_gen.py                       # full file with display control (960 frames) -> gree_yaw1f.json
python3 gree_gen.py --no-screen out.json  # swing off/auto only (480 frames)
python3 gree_gen.py --frame cool high off 22   # one frame, for remote.send_command with "b64:<frame>"
python3 gree_gen.py --decode <base64>     # decode a learned Broadlink frame into Gree fields
```

Ready-made files are in [`codes/`](codes/). Copy one to `custom_components/smartir/codes/climate/<number>.json`, set `device_code` in your SmartIR config, and restart Home Assistant.

Before you generate a full file, decode a few frames learned from your own remote with `--decode`. That confirms your unit uses the same layout.

## Protocol notes

- 9.6 / 4.8 ms leader, 32 bits, a `010` footer, a ~21.5 ms gap, then 32 more bits, LSB first.
- 4-bit checksum: 10 + the low nibbles of bytes 0 to 3 + the high nibbles of bytes 4 to 6.
- Byte layout follows `ir_Gree.h` in [IRremoteESP8266](https://github.com/crankyoldgit/IRremoteESP8266). All 76 frames I learned from my remote decode cleanly with it.
- Timings are copied from the learned frames, not the Gree spec values. The off command is a learned frame kept verbatim.
- The DisplayTemp field changes nothing on the SPIS412L, so you can't read the room temperature over IR.

## Tested

On the SPIS412L with a Broadlink RM: cool 22 °C fan high, dry 24 °C, fan_only high with and without the display bit, and off all behave as labelled. Fan levels and swing off were confirmed on the unit. Every generated frame decodes back to its label with a valid checksum.
